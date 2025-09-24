#!/usr/bin/env python3
"""
🚀 Orchestrateur du bot (filters + WebSocket prix) - VERSION REFACTORISÉE

Script pour filtrer les contrats perpétuels par funding ET suivre leurs prix en temps réel.

Architecture modulaire :
- WatchlistManager : Gestion des filtres et sélection de symboles
- WebSocketManager : Gestion des connexions WebSocket publiques  
- VolatilityTracker : Calcul et cache de volatilité
- PriceTracker : Orchestration et affichage

Usage:
    python src/bot.py
"""

import os
import time
import signal
import threading
import atexit
from typing import List, Dict, Tuple
from logging_setup import setup_logging
from config import get_settings
from bybit_client import BybitPublicClient
from instruments import get_perp_symbols
from price_store import get_snapshot, purge_expired
from volatility import get_volatility_cache_key, is_cache_valid
from volatility_tracker import VolatilityTracker
from watchlist_manager import WatchlistManager
from ws_manager import WebSocketManager
from scoring import ScoringEngine
from errors import NoSymbolsError
from constants.constants import LOG_EMOJIS, LOG_MESSAGES
from metrics_monitor import start_metrics_monitoring
from http_client_manager import close_all_http_clients
from utils import compute_spread_with_mid_price, merge_symbol_data


class PriceTracker:
    """Suivi des prix en temps réel via WebSocket avec filtrage par funding."""
    
    def __init__(self):
        self.logger = setup_logging()
        self.running = True
        
        # S'assurer que les clients HTTP sont fermés à l'arrêt
        atexit.register(close_all_http_clients)
        self.display_thread = None
        self.symbols = []
        self.funding_data = {}
        self.original_funding_data = {}  # Données de funding originales avec next_funding_time
        # self.start_time supprimé: on s'appuie uniquement sur nextFundingTime côté Bybit
        self.realtime_data = {}  # Données en temps réel via WebSocket {symbol: {funding_rate, volume24h, bid1, ask1, next_funding_time, ...}}
        self._realtime_lock = threading.Lock()  # Verrou pour protéger realtime_data
        self._first_display = True  # Indicateur pour la première exécution de l'affichage
        self.symbol_categories: dict[str, str] = {}
        
        # Configuration
        settings = get_settings()
        self.testnet = settings['testnet']
        
        # Gestionnaire WebSocket dédié
        self.ws_manager = WebSocketManager(testnet=self.testnet, logger=self.logger)
        self.ws_manager.set_ticker_callback(self._update_realtime_data_from_ticker)
        
        # Gestionnaire de volatilité dédié
        self.volatility_tracker = VolatilityTracker(testnet=self.testnet, logger=self.logger)
        self.volatility_tracker.set_active_symbols_callback(self._get_active_symbols)
        
        # Gestionnaire de watchlist dédié
        self.watchlist_manager = WatchlistManager(testnet=self.testnet, logger=self.logger)
        # Configurer le callback pour les changements de watchlist
        self.watchlist_manager.set_refresh_callback(self._on_watchlist_refresh)
        
        # Moteur de scoring (sera initialisé avec la config)
        self.scoring_engine = None
        
        # Suivi de la sélection précédente pour détecter les changements
        self.previous_top_symbols = []
        
        # Configuration du signal handler pour Ctrl+C
        signal.signal(signal.SIGINT, self._signal_handler)
        
        self.logger.info(f"{LOG_EMOJIS['start']} Orchestrateur du bot (filters + WebSocket prix)")
        self.logger.info(f"{LOG_EMOJIS['config']} {LOG_MESSAGES['config_loaded']}")
        
        # Démarrer le monitoring des métriques
        start_metrics_monitoring(interval_minutes=5)
    
    def _signal_handler(self, signum, frame):
        """Gestionnaire de signal pour Ctrl+C."""
        self.logger.info(f"{LOG_EMOJIS['stop']} Arrêt demandé, fermeture de la WebSocket…")
        self.running = False
        # Arrêter le gestionnaire WebSocket
        try:
            self.ws_manager.stop()
        except Exception:
            pass
        # Arrêter le tracker de volatilité
        try:
            self.volatility_tracker.stop_refresh_task()
        except Exception:
            pass
        # Arrêter le rafraîchissement périodique de la watchlist
        try:
            self.watchlist_manager.stop_periodic_refresh()
        except Exception:
            pass
        # Arrêter le monitoring des métriques
        try:
            from metrics_monitor import stop_metrics_monitoring
            stop_metrics_monitoring()
        except Exception:
            pass
        return
    
    def get_price(self, symbol: str) -> dict:
        """
        Récupère les données de prix d'un symbole de manière sécurisée.
        
        Args:
            symbol (str): Le symbole à récupérer
            
        Returns:
            dict: Les données de prix du symbole ou un dictionnaire vide
        """
        with self._realtime_lock:
            return self.realtime_data.get(symbol, {}).copy()
    
    def get_all_prices(self) -> dict:
        """
        Récupère une copie de toutes les données de prix de manière sécurisée.
        
        Returns:
            dict: Une copie de toutes les données realtime_data
        """
        with self._realtime_lock:
            return {symbol: data.copy() for symbol, data in self.realtime_data.items()}
    
    def _update_realtime_data_from_ticker(self, ticker_data: dict):
        """
        Met à jour les données en temps réel à partir des données ticker WebSocket.
        Callback appelé par WebSocketManager.
        
        Args:
            ticker_data (dict): Données du ticker reçues via WebSocket
        """
        try:
            symbol = ticker_data.get("symbol", "")
            if not symbol:
                return
                
            # Construire un diff et fusionner avec l'état précédent pour ne pas écraser des valeurs valides par None
            now_ts = time.time()
            incoming = {
                'funding_rate': ticker_data.get('fundingRate'),
                'volume24h': ticker_data.get('volume24h'),
                'bid1_price': ticker_data.get('bid1Price'),
                'ask1_price': ticker_data.get('ask1Price'),
                'next_funding_time': ticker_data.get('nextFundingTime'),
                'mark_price': ticker_data.get('markPrice'),
                'last_price': ticker_data.get('lastPrice'),
            }
            # Vérifier si des données importantes sont présentes
            important_keys = ['funding_rate', 'volume24h', 'bid1_price', 'ask1_price', 'next_funding_time']
            if any(incoming[key] is not None for key in important_keys):
                with self._realtime_lock:
                    current = self.realtime_data.get(symbol, {})
                    merged = dict(current) if current else {}
                    for k, v in incoming.items():
                        if v is not None:
                            merged[k] = v
                    merged['timestamp'] = now_ts
                    self.realtime_data[symbol] = merged
        except Exception as e:
            self.logger.warning(f"{LOG_EMOJIS['warn']} Erreur mise à jour données temps réel pour {symbol}: {e}")
    
    def _recalculate_funding_time(self, symbol: str) -> str:
        """Retourne le temps restant basé uniquement sur nextFundingTime (WS puis REST)."""
        try:
            realtime_info = self.get_price(symbol)
            ws_ts = realtime_info.get('next_funding_time')
            if ws_ts:
                return self.watchlist_manager.calculate_funding_time_remaining(ws_ts)
            
            # Utiliser les données originales du WatchlistManager
            original_funding_data = self.watchlist_manager.get_original_funding_data()
            rest_ts = original_funding_data.get(symbol)
            if rest_ts:
                return self.watchlist_manager.calculate_funding_time_remaining(rest_ts)
            return "-"
        except Exception:
            return "-"
    
    def _refresh_filtering_and_scoring(self):
        """
        Rafraîchit le filtrage et le scoring avec les données actuelles.
        Cette méthode est appelée périodiquement pour mettre à jour la sélection des paires.
        """
        try:
            # Récupérer les paires filtrées actuelles depuis le WatchlistManager
            filtered_candidates = self.watchlist_manager.get_filtered_candidates()
            
            if filtered_candidates and self.scoring_engine:
                # Mettre à jour les candidats avec les données en temps réel
                updated_candidates = self._update_candidates_with_realtime_data(filtered_candidates)
                
                # Appliquer le classement par score avec les données actuelles
                self.logger.info(f"{LOG_EMOJIS['refresh']} {LOG_MESSAGES['scoring_refresh']}")
                top_candidates = self.scoring_engine.rank_candidates(updated_candidates)
                
                # Extraire les symboles de la nouvelle sélection
                new_top_symbols = [candidate[0] for candidate in top_candidates]
                
                # Comparer avec la sélection précédente
                if self.previous_top_symbols:
                    if new_top_symbols != self.previous_top_symbols:
                        # Changement détecté
                        old_symbols_str = ", ".join(self.previous_top_symbols)
                        new_symbols_str = ", ".join(new_top_symbols)
                        self.logger.warning(f"{LOG_EMOJIS['warn']} {LOG_MESSAGES['new_top_detected']}")
                        self.logger.warning(f"   Ancien : {old_symbols_str}")
                        self.logger.warning(f"   Nouveau : {new_symbols_str}")
                    else:
                        # Pas de changement
                        self.logger.info(f"{LOG_EMOJIS['ok']} {LOG_MESSAGES['no_change_top']}")
                else:
                    # Première exécution
                    self.logger.info(f"{LOG_EMOJIS['target']} {LOG_MESSAGES['initial_selection'].format(symbols=', '.join(new_top_symbols))}")
                
                # Mettre à jour la sélection précédente
                self.previous_top_symbols = new_top_symbols.copy()
                
                # Reconstruire la watchlist avec les paires sélectionnées
                self._rebuild_watchlist_from_scored_candidates(top_candidates)
                
                # Mettre à jour les données de funding pour l'affichage
                self._update_funding_data_from_candidates(top_candidates)
                
        except Exception as e:
            self.logger.warning(f"{LOG_EMOJIS['warn']} {LOG_MESSAGES['error_scoring_refresh'].format(error=e)}")
    
    def _update_candidates_with_realtime_data(self, candidates):
        """
        Met à jour les candidats avec les données en temps réel disponibles.
        
        Args:
            candidates: Liste des paires filtrées initiales
            
        Returns:
            Liste des candidats mis à jour avec les données en temps réel
        """
        updated_candidates = []
        
        for candidate in candidates:
            symbol = candidate[0]
            original_funding = candidate[1]
            original_volume = candidate[2]
            original_spread = candidate[4] if len(candidate) > 4 else 0.0
            original_volatility = candidate[5] if len(candidate) > 5 else 0.0
            
            # Récupérer le funding time depuis les données originales du WatchlistManager
            original_funding_data = self.watchlist_manager.get_original_funding_data()
            original_timestamp = original_funding_data.get(symbol)
            if original_timestamp:
                original_funding_time = self.watchlist_manager.calculate_funding_time_remaining(original_timestamp)
            else:
                original_funding_time = candidate[3] if len(candidate) > 3 else "-"
            
            # Récupérer les données en temps réel si disponibles
            realtime_info = self.get_price(symbol)
            
            # Préparer les données REST
            rest_data = {
                'funding': original_funding,
                'volume': original_volume,
                'spread': original_spread,
                'volatility': original_volatility,
                'funding_time': original_funding_time
            }
            
            # Fusionner les données REST et WebSocket
            merged_data = merge_symbol_data(
                symbol=symbol,
                rest_data=rest_data,
                ws_data=realtime_info,
                volatility_tracker=self.volatility_tracker
            )
            
            # Recalculer le temps de funding (priorité WS, fallback REST)
            funding_time = self._recalculate_funding_time(symbol)
            if funding_time == "-":
                # Utiliser le funding time déjà calculé depuis les données originales
                funding_time = original_funding_time
            
            # Créer le candidat mis à jour
            updated_candidate = (
                merged_data['symbol'],
                merged_data['funding'],
                merged_data['volume'],
                funding_time,
                merged_data['spread'],
                merged_data['volatility']
            )
            updated_candidates.append(updated_candidate)
        
        return updated_candidates
    
    def _update_funding_data_from_candidates(self, candidates):
        """
        Met à jour self.funding_data avec les données des candidats sélectionnés.
        
        Args:
            candidates: Liste des paires sélectionnées avec leur score
        """
        self.funding_data = {}
        for candidate in candidates:
            symbol = candidate[0]
            funding = candidate[1]
            volume = candidate[2]
            funding_time_remaining = candidate[3] if len(candidate) > 3 else "-"
            spread_pct = candidate[4] if len(candidate) > 4 else 0.0
            volatility_pct = candidate[5] if len(candidate) > 5 else None
            
            self.funding_data[symbol] = (funding, volume, funding_time_remaining, spread_pct, volatility_pct)
    
    def _print_price_table(self):
        """Affiche le tableau des prix aligné avec funding, volume en millions, spread et volatilité."""
        # Purger les données de prix trop anciennes et récupérer un snapshot
        try:
            purge_expired(ttl_seconds=getattr(self, "price_ttl_sec", 120))
        except Exception:
            pass
        snapshot = get_snapshot()
        
        if not snapshot:
            if self._first_display:
                self.logger.info(f"{LOG_EMOJIS['wait']} {LOG_MESSAGES['waiting_first_ws_data']}")
                self._first_display = False  # Ne plus afficher ce message
            return
        
        # Calculer les largeurs de colonnes
        all_symbols = list(self.funding_data.keys())
        max_symbol_len = max(len("Symbole"), max(len(s) for s in all_symbols)) if all_symbols else len("Symbole")
        symbol_w = max(8, max_symbol_len)
        funding_w = 12  # Largeur pour le funding
        volume_w = 10  # Largeur pour le volume en millions
        spread_w = 10  # Largeur pour le spread
        volatility_w = 12  # Largeur pour la volatilité
        funding_time_w = 15  # Largeur pour le temps de funding (avec secondes)
        
        # En-tête
        header = (
            f"{'Symbole':<{symbol_w}} | {'Funding %':>{funding_w}} | "
            f"{'Volume (M)':>{volume_w}} | {'Spread %':>{spread_w}} | "
            f"{'Volatilité %':>{volatility_w}} | {'Funding T':>{funding_time_w}}"
        )
        sep = (
            f"{'-'*symbol_w}-+-{'-'*funding_w}-+-{'-'*volume_w}-+-"
            f"{'-'*spread_w}-+-{'-'*volatility_w}-+-{'-'*funding_time_w}"
        )
        
        print("\n" + header)
        print(sep)
        
        # Données
        for symbol, data in self.funding_data.items():
            # Récupérer les données en temps réel si disponibles
            realtime_info = self.get_price(symbol)
            
            # Récupérer les valeurs initiales (REST) comme fallbacks
            # data format: (funding, volume, funding_time_remaining, spread_pct, volatility_pct)
            try:
                original_funding = data[0]
                original_volume = data[1]
                original_funding_time = data[2]
                original_spread_pct = data[3] if len(data) > 3 else None
                original_volatility_pct = data[4] if len(data) > 4 else None
            except Exception:
                original_funding = None
                original_volume = None
                original_funding_time = "-"
                original_spread_pct = None
                original_volatility_pct = None
            
            # Préparer les données REST
            rest_data = {
                'funding': original_funding,
                'volume': original_volume,
                'spread': original_spread_pct,
                'volatility': original_volatility_pct,
                'funding_time': original_funding_time
            }
            
            # Fusionner les données REST et WebSocket
            merged_data = merge_symbol_data(
                symbol=symbol,
                rest_data=rest_data,
                ws_data=realtime_info,
                volatility_tracker=self.volatility_tracker
            )
            
            # Extraire les données fusionnées
            funding = merged_data['funding']
            volume = merged_data['volume']
            spread_pct = merged_data['spread']
            volatility_pct = merged_data['volatility']
            funding_time_remaining = merged_data['funding_time']
            
            # Recalculer le temps de funding (priorité WS, fallback REST)
            current_funding_time = self._recalculate_funding_time(symbol)
            if current_funding_time is None:
                current_funding_time = "-"
            
            # Gérer l'affichage des valeurs null
            if funding is not None:
                funding_pct = funding * 100.0
                funding_str = f"{funding_pct:+{funding_w-1}.4f}%"
            else:
                funding_str = "null"
            
            if volume is not None and volume > 0:
                volume_millions = volume / 1_000_000
                volume_str = f"{volume_millions:,.1f}"
            else:
                volume_str = "null"
            
            if spread_pct is not None:
                spread_pct_display = spread_pct * 100.0
                spread_str = f"{spread_pct_display:+.3f}%"
            else:
                spread_str = "null"
            
            # Formatage de la volatilité
            if volatility_pct is not None:
                volatility_pct_display = volatility_pct * 100.0
                volatility_str = f"{volatility_pct_display:+.3f}%"
            else:
                volatility_str = "-"
            
            line = (
                f"{symbol:<{symbol_w}} | {funding_str:>{funding_w}} | "
                f"{volume_str:>{volume_w}} | {spread_str:>{spread_w}} | "
                f"{volatility_str:>{volatility_w}} | {current_funding_time:>{funding_time_w}}"
            )
            print(line)
        
        print()  # Ligne vide après le tableau
    
    def _display_loop(self):
        """Boucle d'affichage toutes les 15 secondes."""
        while self.running:
            # Rafraîchir le filtrage et le scoring avant l'affichage
            self._refresh_filtering_and_scoring()
            
            # Afficher le tableau des prix
            self._print_price_table()
            
            # Attendre 15 secondes
            for _ in range(150):  # 150 * 0.1s = 15s
                if not self.running:
                    break
                time.sleep(0.1)
    
    def start(self):
        """Démarre le suivi des prix avec filtrage par funding."""
        # Charger et valider la configuration via le watchlist manager
        try:
            config = self.watchlist_manager.load_and_validate_config()
        except ValueError as e:
            self.logger.error(f"{LOG_EMOJIS['error']} {LOG_MESSAGES['error_config'].format(error=e)}")
            self.logger.error("💡 Corrigez les paramètres dans src/parameters.yaml ou les variables d'environnement")
            return  # Arrêt propre sans sys.exit
        
        # Initialiser le moteur de scoring avec la configuration
        self.scoring_engine = ScoringEngine(config, logger=self.logger)
        
        # Afficher la configuration du scoring
        scoring_config = self.scoring_engine.get_scoring_config()
        self.logger.info(f"[Scoring Config] funding={scoring_config['weight_funding']} | "
                        f"volume={scoring_config['weight_volume']} | "
                        f"spread={scoring_config['weight_spread']} | "
                        f"vol={scoring_config['weight_volatility']} | "
                        f"top_n={scoring_config['top_n']}")
        
        # Vérifier si le fichier de config existe
        config_path = "src/parameters.yaml"
        if not os.path.exists(config_path):
            self.logger.info(f"{LOG_EMOJIS['info']} {LOG_MESSAGES['config_not_found']}")
        else:
            self.logger.info(f"{LOG_EMOJIS['info']} {LOG_MESSAGES['config_loaded_from_file']}")
        
        # Créer un client PUBLIC pour récupérer l'URL publique (aucune clé requise)
        client = BybitPublicClient(
            testnet=self.testnet,
            timeout=10,
        )
        
        base_url = client.public_base_url()
        
        # Récupérer l'univers perp
        perp_data = get_perp_symbols(base_url, timeout=10)
        self.logger.info(f"{LOG_EMOJIS['map']} {LOG_MESSAGES['perp_universe_retrieved']} : linear={len(perp_data['linear'])} | inverse={len(perp_data['inverse'])} | total={perp_data['total']}")
        # Stocker le mapping officiel des catégories
        try:
            self.symbol_categories = perp_data.get("categories", {}) or {}
        except Exception:
            self.symbol_categories = {}
        
        # Configurer les gestionnaires avec les catégories
        self.volatility_tracker.set_symbol_categories(self.symbol_categories)
        self.watchlist_manager.symbol_categories = self.symbol_categories
        
        # Configurer le tracker de volatilité
        volatility_ttl_sec = int(config.get("volatility_ttl_sec", 120) or 120)
        self.volatility_tracker.ttl_seconds = volatility_ttl_sec
        self.price_ttl_sec = 120
        
        # Afficher les filtres (délégué au watchlist manager)
        self._log_filter_config(config, volatility_ttl_sec)
        
        # Construire la watchlist via le gestionnaire dédié
        try:
            self.linear_symbols, self.inverse_symbols, self.funding_data = self.watchlist_manager.build_watchlist(
                base_url, perp_data, self.volatility_tracker
            )
            # Récupérer les données originales de funding
            self.original_funding_data = self.watchlist_manager.get_original_funding_data()
        except Exception as e:
            if "Aucun symbole" in str(e) or "Aucun funding" in str(e):
                # Convertir en exceptions spécifiques
                if "Aucun symbole" in str(e):
                    raise NoSymbolsError(str(e))
                else:
                    from errors import FundingUnavailableError
                    raise FundingUnavailableError(str(e))
            else:
                raise
        
        # Appliquer le classement par score pour sélectionner les meilleures paires
        filtered_candidates = self.watchlist_manager.get_filtered_candidates()
        if filtered_candidates:
            self.logger.info(f"{LOG_EMOJIS['target']} {LOG_MESSAGES['scoring_applied']}")
            top_candidates = self.scoring_engine.rank_candidates(filtered_candidates)
            
            # Reconstruire les listes de symboles et funding_data avec les paires sélectionnées
            self._rebuild_watchlist_from_scored_candidates(top_candidates)
        else:
            self.logger.warning(f"{LOG_EMOJIS['warn']} {LOG_MESSAGES['no_filtered_pairs']}")
        
        self.logger.info(f"{LOG_EMOJIS['data']} {LOG_MESSAGES['symbols_linear_inverse'].format(linear_count=len(self.linear_symbols), inverse_count=len(self.inverse_symbols))}")
        
        # Démarrer le tracker de volatilité (arrière-plan) AVANT les WS bloquantes
        self.volatility_tracker.start_refresh_task()
        
        # Démarrer le rafraîchissement périodique de la watchlist si configuré
        self.watchlist_manager.start_periodic_refresh(base_url, perp_data, self.volatility_tracker)
        
        # Démarrer l'affichage
        self.display_thread = threading.Thread(target=self._display_loop)
        self.display_thread.daemon = True
        self.display_thread.start()

        # Démarrer les connexions WebSocket via le gestionnaire dédié
        if self.linear_symbols or self.inverse_symbols:
            self.ws_manager.start_connections(self.linear_symbols, self.inverse_symbols)
        else:
            self.logger.warning(f"{LOG_EMOJIS['warn']} {LOG_MESSAGES['no_valid_symbols']}")
            raise NoSymbolsError("Aucun symbole valide trouvé")
    
    def _get_active_symbols(self) -> List[str]:
        """Retourne la liste des symboles actuellement actifs."""
        return list(self.funding_data.keys())
    
    def _on_watchlist_refresh(self, new_linear_symbols: List[str], new_inverse_symbols: List[str], new_funding_data: Dict):
        """
        Callback appelé lors du rafraîchissement de la watchlist.
        
        Args:
            new_linear_symbols: Nouveaux symboles linear
            new_inverse_symbols: Nouveaux symboles inverse
            new_funding_data: Nouvelles données de funding
        """
        try:
            self.logger.info("🔄 Mise à jour des connexions WebSocket suite au rafraîchissement de la watchlist")
            
            # Arrêter les connexions WebSocket actuelles
            self.ws_manager.stop()
            
            # Mettre à jour les données internes
            self.linear_symbols = new_linear_symbols
            self.inverse_symbols = new_inverse_symbols
            self.funding_data = new_funding_data
            self.selected_symbols = list(new_funding_data.keys())
            
            # Redémarrer les connexions WebSocket avec les nouveaux symboles
            if self.linear_symbols or self.inverse_symbols:
                self.ws_manager.start_connections(self.linear_symbols, self.inverse_symbols)
                self.logger.info(f"✅ Connexions WebSocket mises à jour : {len(self.linear_symbols)} linear, {len(self.inverse_symbols)} inverse")
            else:
                self.logger.warning("⚠️ Aucun symbole valide après rafraîchissement")
                
        except Exception as e:
            self.logger.error(f"❌ Erreur lors de la mise à jour des connexions WebSocket: {e}")
    
    def _rebuild_watchlist_from_scored_candidates(self, top_candidates: List[Tuple]):
        """
        Reconstruit les listes de symboles et funding_data à partir des paires sélectionnées par le scoring.
        
        Args:
            top_candidates: Liste des paires sélectionnées avec leur score
        """
        from instruments import category_of_symbol
        
        # Réinitialiser les listes
        self.linear_symbols = []
        self.inverse_symbols = []
        self.funding_data = {}
        
        # Reconstruire à partir des paires sélectionnées
        for candidate in top_candidates:
            symbol = candidate[0]
            funding = candidate[1]
            volume = candidate[2]
            funding_time_remaining = candidate[3] if len(candidate) > 3 else "-"
            spread_pct = candidate[4] if len(candidate) > 4 else 0.0
            volatility_pct = candidate[5] if len(candidate) > 5 else None
            
            # Déterminer la catégorie du symbole
            category = category_of_symbol(symbol, self.symbol_categories)
            
            # Ajouter à la liste appropriée
            if category == "linear":
                self.linear_symbols.append(symbol)
            elif category == "inverse":
                self.inverse_symbols.append(symbol)
            
            # Ajouter aux données de funding
            self.funding_data[symbol] = (funding, volume, funding_time_remaining, spread_pct, volatility_pct)
        
        self.logger.info(f"{LOG_EMOJIS['refresh']} {LOG_MESSAGES['watchlist_rebuilt'].format(count=len(top_candidates))}")
    
    def _log_filter_config(self, config: Dict, volatility_ttl_sec: int):
        """Affiche la configuration des filtres."""
        # Extraire les paramètres pour l'affichage
        categorie = config.get("categorie", "both")
        funding_min = config.get("funding_min")
        funding_max = config.get("funding_max")
        volume_min_millions = config.get("volume_min_millions")
        spread_max = config.get("spread_max")
        volatility_min = config.get("volatility_min")
        volatility_max = config.get("volatility_max")
        limite = config.get("limite")
        funding_time_min_minutes = config.get("funding_time_min_minutes")
        funding_time_max_minutes = config.get("funding_time_max_minutes")
        
        # Formater pour l'affichage
        min_display = f"{funding_min:.6f}" if funding_min is not None else "none"
        max_display = f"{funding_max:.6f}" if funding_max is not None else "none"
        volume_display = f"{volume_min_millions:.1f}" if volume_min_millions is not None else "none"
        spread_display = f"{spread_max:.4f}" if spread_max is not None else "none"
        volatility_min_display = f"{volatility_min:.3f}" if volatility_min is not None else "none"
        volatility_max_display = f"{volatility_max:.3f}" if volatility_max is not None else "none"
        limite_display = str(limite) if limite is not None else "none"
        ft_min_display = str(funding_time_min_minutes) if funding_time_min_minutes is not None else "none"
        ft_max_display = str(funding_time_max_minutes) if funding_time_max_minutes is not None else "none"
        
        self.logger.info(
            f"{LOG_EMOJIS['filters']} Filtres | catégorie={categorie} | funding_min={min_display} | "
            f"funding_max={max_display} | volume_min_millions={volume_display} | "
            f"spread_max={spread_display} | volatility_min={volatility_min_display} | "
            f"volatility_max={volatility_max_display} | ft_min(min)={ft_min_display} | "
            f"ft_max(min)={ft_max_display} | limite={limite_display} | vol_ttl={volatility_ttl_sec}s"
        )


def main():
    """Fonction principale."""
    tracker = PriceTracker()
    try:
        tracker.start()
    except Exception as e:
        tracker.logger.error(f"{LOG_EMOJIS['error']} Erreur : {e}")
        tracker.running = False
        # Arrêter le monitoring des métriques en cas d'erreur
        try:
            from metrics_monitor import stop_metrics_monitoring
            stop_metrics_monitoring()
        except Exception:
            pass
        # Laisser le code appelant décider (ne pas sys.exit ici)


if __name__ == "__main__":
    main()