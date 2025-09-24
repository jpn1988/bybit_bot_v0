#!/usr/bin/env python3
"""
Gestionnaire de watchlist dédié pour le bot Bybit.

Cette classe orchestre la construction de la watchlist :
- Charge et valide la configuration
- Coordonne la récupération de données (via WatchlistDataFetcher)
- Applique les filtres (via WatchlistFilters)
- Stocke et expose les résultats finaux
"""

import os
import yaml
import time
import threading
from typing import List, Tuple, Dict, Optional, Callable
from concurrent.futures import ThreadPoolExecutor
from logging_setup import setup_logging
from config import get_settings
from bybit_client import BybitPublicClient
from instruments import get_perp_symbols, category_of_symbol
from volatility_tracker import VolatilityTracker
from metrics import record_filter_result
from watchlist_data_fetcher import WatchlistDataFetcher
from watchlist_filters import WatchlistFilters
from constants.constants import LOG_EMOJIS, LOG_MESSAGES


class WatchlistManager:
    """
    Gestionnaire de watchlist pour le bot Bybit.
    
    Responsabilités :
    - Chargement et validation de la configuration
    - Orchestration de la récupération de données (via WatchlistDataFetcher)
    - Application des filtres (via WatchlistFilters)
    - Stockage et exposition des résultats finaux
    """
    
    def __init__(self, testnet: bool = True, logger=None):
        """
        Initialise le gestionnaire de watchlist.
        
        Args:
            testnet (bool): Utiliser le testnet (True) ou le marché réel (False)
            logger: Logger pour les messages (optionnel)
        """
        self.testnet = testnet
        self.logger = logger or setup_logging()
        
        # Configuration
        self.config = {}
        self.symbol_categories = {}
        
        # Données de la watchlist
        self.selected_symbols = []
        self.funding_data = {}
        self.original_funding_data = {}
        
        # Modules spécialisés
        self.data_fetcher = WatchlistDataFetcher(self.logger)
        self.filters = WatchlistFilters(self.logger)
        
        # Client pour les données publiques
        self._client: Optional[BybitPublicClient] = None
        
        # Gestion du rafraîchissement périodique
        self._refresh_thread: Optional[threading.Thread] = None
        self._refresh_running = False
        self._refresh_callback: Optional[Callable] = None
        self._base_url: Optional[str] = None
        self._perp_data: Optional[Dict] = None
        self._volatility_tracker: Optional[VolatilityTracker] = None
    
    def load_and_validate_config(self) -> Dict:
        """
        Charge et valide la configuration depuis le fichier YAML.
        
        Returns:
            Dict: Configuration validée
            
        Raises:
            ValueError: Si la configuration est invalide
        """
        config_path = "src/parameters.yaml"
        
        # Valeurs par défaut
        default_config = {
            "categorie": "linear",
            "funding_min": None,
            "funding_max": None,
            "volume_min": None,
            "volume_min_millions": None,
            "spread_max": None,
            "volatility_min": None,
            "volatility_max": None,
            "limite": 10,
            "volatility_ttl_sec": 120,
            # Nouveaux paramètres temporels
            "funding_time_min_minutes": None,
            "funding_time_max_minutes": None,
            # Paramètre de rafraîchissement périodique
            "refresh_watchlist_interval": 0,
            # Configuration du classement des paires
            "scoring": {
                "weight_spread": 200,
                "weight_volatility": 50,
                "top_n": 1,
            },
        }
        
        # Charger depuis le fichier si disponible
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                file_config = yaml.safe_load(f)
            if file_config:
                default_config.update(file_config)
        except FileNotFoundError:
            pass  # Utiliser les valeurs par défaut
        
        # Récupérer les variables d'environnement (priorité maximale)
        settings = get_settings()
        env_mappings = {
            "spread_max": "spread_max",
            "volume_min_millions": "volume_min_millions", 
            "volatility_min": "volatility_min",
            "volatility_max": "volatility_max",
            "funding_min": "funding_min",
            "funding_max": "funding_max",
            "category": "categorie",
            "limit": "limite",
            "volatility_ttl_sec": "volatility_ttl_sec",
            "funding_time_min_minutes": "funding_time_min_minutes",
            "funding_time_max_minutes": "funding_time_max_minutes",
            "refresh_watchlist_interval": "refresh_watchlist_interval",
        }
        
        # Appliquer les variables d'environnement si présentes
        for env_key, config_key in env_mappings.items():
            env_value = settings.get(env_key)
            if env_value is not None:
                default_config[config_key] = env_value
        
        # Valider la configuration finale
        self._validate_config(default_config)
        
        self.config = default_config
        return default_config
    
    def _validate_config(self, config: Dict) -> None:
        """
        Valide la cohérence des paramètres de configuration.
        
        Args:
            config: Configuration à valider
            
        Raises:
            ValueError: Si des paramètres sont incohérents ou invalides
        """
        errors = []
        
        # Validation des bornes de funding
        funding_min = config.get("funding_min")
        funding_max = config.get("funding_max")
        
        if funding_min is not None and funding_max is not None:
            if funding_min > funding_max:
                errors.append(f"funding_min ({funding_min}) ne peut pas être supérieur à funding_max ({funding_max})")
        
        # Validation des bornes de volatilité
        volatility_min = config.get("volatility_min")
        volatility_max = config.get("volatility_max")
        
        if volatility_min is not None and volatility_max is not None:
            if volatility_min > volatility_max:
                errors.append(f"volatility_min ({volatility_min}) ne peut pas être supérieur à volatility_max ({volatility_max})")
        
        # Validation des valeurs négatives
        for param in ["funding_min", "funding_max", "volatility_min", "volatility_max"]:
            value = config.get(param)
            if value is not None and value < 0:
                errors.append(f"{param} ne peut pas être négatif ({value})")
        
        # Validation du spread
        spread_max = config.get("spread_max")
        if spread_max is not None:
            if spread_max < 0:
                errors.append(f"spread_max ne peut pas être négatif ({spread_max})")
            if spread_max > 1.0:  # 100% de spread maximum
                errors.append(f"spread_max trop élevé ({spread_max}), maximum recommandé: 1.0 (100%)")
        
        # Validation des volumes
        for param in ["volume_min", "volume_min_millions"]:
            value = config.get(param)
            if value is not None and value < 0:
                errors.append(f"{param} ne peut pas être négatif ({value})")
        
        # Validation des paramètres temporels de funding
        ft_min = config.get("funding_time_min_minutes")
        ft_max = config.get("funding_time_max_minutes")
        
        for param, value in [("funding_time_min_minutes", ft_min), ("funding_time_max_minutes", ft_max)]:
            if value is not None:
                if value < 0:
                    errors.append(f"{param} ne peut pas être négatif ({value})")
                if value > 1440:  # 24 heures maximum
                    errors.append(f"{param} trop élevé ({value}), maximum: 1440 (24h)")
        
        if ft_min is not None and ft_max is not None:
            if ft_min > ft_max:
                errors.append(f"funding_time_min_minutes ({ft_min}) ne peut pas être supérieur à funding_time_max_minutes ({ft_max})")
        
        # Validation de la catégorie
        categorie = config.get("categorie")
        if categorie not in ["linear", "inverse", "both"]:
            errors.append(f"categorie invalide ({categorie}), valeurs autorisées: linear, inverse, both")
        
        # Validation de la limite
        limite = config.get("limite")
        if limite is not None:
            if limite < 1:
                errors.append(f"limite doit être positive ({limite})")
            if limite > 1000:
                errors.append(f"limite trop élevée ({limite}), maximum recommandé: 1000")
        
        # Validation du TTL de volatilité
        vol_ttl = config.get("volatility_ttl_sec")
        if vol_ttl is not None:
            if vol_ttl < 10:
                errors.append(f"volatility_ttl_sec trop faible ({vol_ttl}), minimum: 10 secondes")
            if vol_ttl > 3600:
                errors.append(f"volatility_ttl_sec trop élevé ({vol_ttl}), maximum: 3600 secondes (1h)")
        
        # Validation de l'intervalle de rafraîchissement
        refresh_interval = config.get("refresh_watchlist_interval")
        if refresh_interval is not None:
            if refresh_interval < 0:
                errors.append(f"refresh_watchlist_interval ne peut pas être négatif ({refresh_interval})")
            if refresh_interval > 0 and refresh_interval < 60:
                errors.append(f"refresh_watchlist_interval trop faible ({refresh_interval}), minimum recommandé: 60 secondes")
            if refresh_interval > 86400:  # 24 heures
                errors.append(f"refresh_watchlist_interval trop élevé ({refresh_interval}), maximum: 86400 secondes (24h)")
        
        # Lever une erreur si des problèmes ont été détectés
        if errors:
            error_msg = "Configuration invalide détectée:\n" + "\n".join(f"  - {error}" for error in errors)
            raise ValueError(error_msg)
    
    
    
    
    
    
    
    
    def build_watchlist(
        self,
        base_url: str,
        perp_data: Dict,
        volatility_tracker: VolatilityTracker
    ) -> Tuple[List[str], List[str], Dict]:
        """
        Construit la watchlist complète en appliquant tous les filtres.
        
        Args:
            base_url: URL de base de l'API Bybit
            perp_data: Données des perpétuels
            volatility_tracker: Tracker de volatilité pour le filtrage
            
        Returns:
            Tuple[linear_symbols, inverse_symbols, funding_data]
        """
        config = self.config
        
        # Extraire les paramètres de configuration
        categorie = config.get("categorie", "both")
        funding_min = config.get("funding_min")
        funding_max = config.get("funding_max")
        volume_min = config.get("volume_min")
        volume_min_millions = config.get("volume_min_millions")
        spread_max = config.get("spread_max")
        volatility_min = config.get("volatility_min")
        volatility_max = config.get("volatility_max")
        limite = config.get("limite")
        funding_time_min_minutes = config.get("funding_time_min_minutes")
        funding_time_max_minutes = config.get("funding_time_max_minutes")
        
        # Récupérer les funding rates selon la catégorie
        funding_map = {}
        if categorie == "linear":
            self.logger.info(f"{LOG_EMOJIS['api']} {LOG_MESSAGES['funding_rates_linear']}")
            funding_map = self.data_fetcher.fetch_funding_map(base_url, "linear", 10)
        elif categorie == "inverse":
            self.logger.info(f"{LOG_EMOJIS['api']} {LOG_MESSAGES['funding_rates_inverse']}")
            funding_map = self.data_fetcher.fetch_funding_map(base_url, "inverse", 10)
        else:  # "both"
            self.logger.info(f"{LOG_EMOJIS['api']} {LOG_MESSAGES['funding_rates_both']}")
            # Paralléliser les requêtes linear et inverse
            with ThreadPoolExecutor(max_workers=2) as executor:
                # Lancer les deux requêtes en parallèle
                linear_future = executor.submit(self.data_fetcher.fetch_funding_map, base_url, "linear", 10)
                inverse_future = executor.submit(self.data_fetcher.fetch_funding_map, base_url, "inverse", 10)
                
                # Attendre les résultats
                linear_funding = linear_future.result()
                inverse_funding = inverse_future.result()
            
            funding_map = {**linear_funding, **inverse_funding}  # Merger (priorité au dernier)
        
        if not funding_map:
            self.logger.warning(f"{LOG_EMOJIS['warn']} {LOG_MESSAGES['no_funding_available']}")
            raise RuntimeError("Aucun funding disponible pour la catégorie sélectionnée")
        
        # Stocker les next_funding_time originaux pour fallback (REST)
        self.original_funding_data = {}
        for _sym, _data in funding_map.items():
            try:
                nft = _data.get("next_funding_time")
                if nft:
                    self.original_funding_data[_sym] = nft
            except Exception:
                continue
        
        # Compter les symboles avant filtrage
        all_symbols = list(set(perp_data["linear"] + perp_data["inverse"]))
        n0 = len([s for s in all_symbols if s in funding_map])
        
        # Filtrer par funding, volume et temps avant funding
        filtered_symbols = self.filters.filter_by_funding(
            perp_data,
            funding_map,
            funding_min,
            funding_max,
            volume_min,
            volume_min_millions,
            limite,
            funding_time_min_minutes=funding_time_min_minutes,
            funding_time_max_minutes=funding_time_max_minutes,
        )
        n1 = len(filtered_symbols)
        
        # Appliquer le filtre de spread si nécessaire
        final_symbols = filtered_symbols
        n2 = n1
        
        if spread_max is not None and filtered_symbols:
            # Récupérer les données de spread pour les symboles restants
            symbols_to_check = [symbol for symbol, _, _, _ in filtered_symbols]
            self.logger.info(f"{LOG_EMOJIS['search']} {LOG_MESSAGES['spread_evaluation'].format(count=len(symbols_to_check))}")
            
            try:
                spread_data = {}
                
                # Séparer les symboles par catégorie pour les requêtes spread
                linear_symbols_for_spread = [s for s in symbols_to_check if category_of_symbol(s, self.symbol_categories) == "linear"]
                inverse_symbols_for_spread = [s for s in symbols_to_check if category_of_symbol(s, self.symbol_categories) == "inverse"]
                
                # Paralléliser les requêtes de spreads pour linear et inverse
                if linear_symbols_for_spread or inverse_symbols_for_spread:
                    self.logger.info(f"{LOG_EMOJIS['search']} {LOG_MESSAGES['spread_retrieval'].format(linear_count=len(linear_symbols_for_spread), inverse_count=len(inverse_symbols_for_spread))}")
                    
                    with ThreadPoolExecutor(max_workers=2) as executor:
                        futures = {}
                        
                        # Lancer les requêtes en parallèle si nécessaire
                        if linear_symbols_for_spread:
                            futures['linear'] = executor.submit(self.data_fetcher.fetch_spread_data, base_url, linear_symbols_for_spread, 10, "linear")
                        
                        if inverse_symbols_for_spread:
                            futures['inverse'] = executor.submit(self.data_fetcher.fetch_spread_data, base_url, inverse_symbols_for_spread, 10, "inverse")
                        
                        # Récupérer les résultats
                        if 'linear' in futures:
                            linear_spread_data = futures['linear'].result()
                            spread_data.update(linear_spread_data)
                        
                        if 'inverse' in futures:
                            inverse_spread_data = futures['inverse'].result()
                            spread_data.update(inverse_spread_data)
                
                final_symbols = self.filters.filter_by_spread(filtered_symbols, spread_data, spread_max)
                n2 = len(final_symbols)
                
                # Log des résultats du filtre spread
                rejected = n1 - n2
                spread_pct_display = spread_max * 100
                self.logger.info(f"{LOG_EMOJIS['ok']} {LOG_MESSAGES['spread_filter_success'].format(kept=n2, rejected=rejected, threshold=spread_pct_display)}")
                
            except Exception as e:
                self.logger.warning(f"{LOG_EMOJIS['warn']} {LOG_MESSAGES['spread_filter_error'].format(error=e)}")
                # Continuer sans le filtre de spread
                final_symbols = [(symbol, funding, volume, funding_time_remaining, 0.0) 
                               for symbol, funding, volume, funding_time_remaining in filtered_symbols]
        
        # Calculer la volatilité pour tous les symboles (même sans filtre)
        n_before_volatility = len(final_symbols) if final_symbols else 0
        if final_symbols:
            try:
                self.logger.info(f"{LOG_EMOJIS['search']} {LOG_MESSAGES['volatility_evaluation']}")
                final_symbols = self.filters.apply_volatility_filter(
                    final_symbols,
                    volatility_tracker,
                    volatility_min,
                    volatility_max
                )
                n_after_volatility = len(final_symbols)
            except Exception as e:
                self.logger.warning(f"{LOG_EMOJIS['warn']} {LOG_MESSAGES['volatility_filter_error'].format(error=e)}")
                n_after_volatility = n_before_volatility
                # Continuer sans le filtre de volatilité
        else:
            n_after_volatility = 0
        
        # Stocker les paires filtrées avant l'application de la limite finale
        # (pour le classement par score)
        self._filtered_candidates = final_symbols.copy()
        
        # Appliquer la limite finale
        if limite is not None and len(final_symbols) > limite:
            final_symbols = final_symbols[:limite]
        n3 = len(final_symbols)
        
        # Enregistrer les métriques des filtres
        record_filter_result("funding_volume_time", n1, n0 - n1)
        if spread_max is not None:
            record_filter_result("spread", n2, n1 - n2)
        record_filter_result("volatility", n_after_volatility, n_before_volatility - n_after_volatility)
        record_filter_result("final_limit", n3, n_after_volatility - n3)
        
        # Log des comptes
        self.logger.info(f"{LOG_EMOJIS['count']} {LOG_MESSAGES['filter_counts'].format(before=n0, after_funding=n1, after_spread=n2, after_volatility=n_after_volatility, final=n3)}")
        
        if not final_symbols:
            self.logger.warning(f"{LOG_EMOJIS['warn']} {LOG_MESSAGES['no_symbols_match_criteria']}")
            raise RuntimeError("Aucun symbole ne correspond aux critères de filtrage")
        
        # Séparer les symboles par catégorie
        linear_symbols, inverse_symbols = self.filters.separate_symbols_by_category(
            final_symbols, self.symbol_categories
        )
        
        # Construire funding_data avec les bonnes données
        funding_data = self.filters.build_funding_data_dict(final_symbols)
        
        # Stocker les résultats
        self.selected_symbols = list(funding_data.keys())
        self.funding_data = funding_data
        self.linear_symbols = linear_symbols
        self.inverse_symbols = inverse_symbols
        
        # Log des symboles retenus
        self.logger.info(f"{LOG_EMOJIS['watchlist']} {LOG_MESSAGES['symbols_retained'].format(count=n3, symbols=self.selected_symbols)}")
        self.logger.info(f"{LOG_EMOJIS['data']} {LOG_MESSAGES['symbols_linear_inverse'].format(linear_count=len(linear_symbols), inverse_count=len(inverse_symbols))}")
        
        return linear_symbols, inverse_symbols, funding_data
    
    def get_filtered_candidates(self) -> List[Tuple]:
        """
        Retourne les paires filtrées avant le classement par score.
        
        Returns:
            Liste des paires filtrées sous forme de tuples
        """
        return getattr(self, '_filtered_candidates', [])
    
    def get_selected_symbols(self) -> List[str]:
        """
        Retourne la liste des symboles sélectionnés.
        
        Returns:
            Liste des symboles de la watchlist
        """
        return self.selected_symbols.copy()
    
    def get_funding_data(self) -> Dict:
        """
        Retourne les données de funding de la watchlist.
        
        Returns:
            Dictionnaire des données de funding
        """
        return self.funding_data.copy()
    
    def get_original_funding_data(self) -> Dict:
        """
        Retourne les données de funding originales (next_funding_time).
        
        Returns:
            Dictionnaire des next_funding_time originaux
        """
        return self.original_funding_data.copy()
    
    def calculate_funding_time_remaining(self, next_funding_time) -> str:
        """
        Retourne "Xh Ym Zs" à partir d'un timestamp Bybit (ms) ou ISO.
        Méthode exposée pour utilisation externe.
        
        Args:
            next_funding_time: Timestamp du prochain funding
            
        Returns:
            String formatée du temps restant ou "-" si erreur
        """
        return self.filters.calculate_funding_time_remaining(next_funding_time)
    
    def set_refresh_callback(self, callback: Callable[[List[str], List[str], Dict], None]):
        """
        Définit le callback à appeler lors du rafraîchissement de la watchlist.
        
        Args:
            callback: Fonction à appeler avec (linear_symbols, inverse_symbols, funding_data)
        """
        self._refresh_callback = callback
    
    def start_periodic_refresh(self, base_url: str, perp_data: Dict, volatility_tracker: VolatilityTracker):
        """
        Démarre le rafraîchissement périodique de la watchlist si configuré.
        
        Args:
            base_url: URL de base de l'API Bybit
            perp_data: Données des perpétuels
            volatility_tracker: Tracker de volatilité
        """
        refresh_interval = self.config.get("refresh_watchlist_interval", 0)
        
        if refresh_interval <= 0:
            self.logger.info(f"🔄 Rafraîchissement périodique désactivé (refresh_watchlist_interval={refresh_interval})")
            return
        
        if self._refresh_running:
            self.logger.warning("⚠️ Rafraîchissement périodique déjà en cours")
            return
        
        # Stocker les paramètres nécessaires
        self._base_url = base_url
        self._perp_data = perp_data
        self._volatility_tracker = volatility_tracker
        
        # Démarrer le thread de rafraîchissement
        self._refresh_running = True
        self._refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._refresh_thread.start()
        
        self.logger.info(f"🔄 Rafraîchissement périodique de la watchlist activé (interval: {refresh_interval}s)")
    
    def stop_periodic_refresh(self):
        """
        Arrête le rafraîchissement périodique de la watchlist.
        """
        if not self._refresh_running:
            return
        
        self.logger.info("🧹 Arrêt du rafraîchissement périodique de la watchlist...")
        self._refresh_running = False
        
        if self._refresh_thread and self._refresh_thread.is_alive():
            self._refresh_thread.join(timeout=5)
        
        self._refresh_thread = None
        self.logger.info("✅ Rafraîchissement périodique arrêté")
    
    def _refresh_loop(self):
        """
        Boucle principale du rafraîchissement périodique.
        """
        refresh_interval = self.config.get("refresh_watchlist_interval", 0)
        
        while self._refresh_running:
            try:
                # Attendre l'intervalle configuré
                for _ in range(refresh_interval):
                    if not self._refresh_running:
                        return
                    time.sleep(1)
                
                if not self._refresh_running:
                    return
                
                # Effectuer le rafraîchissement
                self._perform_refresh()
                
            except Exception as e:
                self.logger.error(f"❌ Erreur dans la boucle de rafraîchissement: {e}")
                # Continuer la boucle même en cas d'erreur
    
    def _perform_refresh(self):
        """
        Effectue le rafraîchissement de la watchlist.
        """
        try:
            self.logger.info(f"🔄 Rafraîchissement périodique de la watchlist (config interval: {self.config.get('refresh_watchlist_interval', 0)}s)")
            
            # Sauvegarder l'ancienne watchlist
            old_linear_symbols = self.linear_symbols.copy() if hasattr(self, 'linear_symbols') else []
            old_inverse_symbols = self.inverse_symbols.copy() if hasattr(self, 'inverse_symbols') else []
            old_selected_symbols = self.selected_symbols.copy()
            
            # Reconstruire la watchlist
            new_linear_symbols, new_inverse_symbols, new_funding_data = self.build_watchlist(
                self._base_url, self._perp_data, self._volatility_tracker
            )
            
            # Comparer les listes
            old_all_symbols = set(old_linear_symbols + old_inverse_symbols)
            new_all_symbols = set(new_linear_symbols + new_inverse_symbols)
            
            if old_all_symbols != new_all_symbols:
                # Changements détectés
                removed_symbols = old_all_symbols - new_all_symbols
                added_symbols = new_all_symbols - old_all_symbols
                
                if removed_symbols or added_symbols:
                    self.logger.warning(f"⚠️ Paires remplacées : {', '.join(sorted(removed_symbols))} -> {', '.join(sorted(added_symbols))}")
                
                # Appeler le callback si défini
                if self._refresh_callback:
                    try:
                        self._refresh_callback(new_linear_symbols, new_inverse_symbols, new_funding_data)
                    except Exception as e:
                        self.logger.error(f"❌ Erreur dans le callback de rafraîchissement: {e}")
                
                self.logger.info(f"✅ Watchlist mise à jour avec {len(new_all_symbols)} paires")
            else:
                self.logger.info("✅ Watchlist inchangée")
                
        except Exception as e:
            self.logger.error(f"❌ Erreur lors du rafraîchissement de la watchlist: {e}")
