#!/usr/bin/env python3
"""
Gestionnaire de watchlist dédié pour le bot Bybit.

Cette classe gère uniquement :
- L'application des filtres (funding, volume, spread, volatilité, temps avant funding, etc.)
- Le stockage de la liste des symboles retenus
- Les fonctions utilitaires liées à la sélection et au tri des symboles
"""

import os
import time
import yaml
import httpx
import asyncio
from typing import List, Tuple, Dict, Optional
from concurrent.futures import ThreadPoolExecutor
from logging_setup import setup_logging
from config import get_settings
from bybit_client import BybitPublicClient
from instruments import get_perp_symbols, category_of_symbol
from http_utils import get_rate_limiter
from http_client_manager import get_http_client
from volatility_tracker import VolatilityTracker
from metrics import record_filter_result


class WatchlistManager:
    """
    Gestionnaire de watchlist pour le bot Bybit.
    
    Responsabilités :
    - Chargement et validation de la configuration
    - Application des filtres successifs (funding, spread, volatilité)
    - Récupération des données de marché (funding rates, spreads)
    - Sélection et tri des symboles selon les critères
    - Stockage de la watchlist finale
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
        
        # Client pour les données publiques
        self._client: Optional[BybitPublicClient] = None
    
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
        
        # Lever une erreur si des problèmes ont été détectés
        if errors:
            error_msg = "Configuration invalide détectée:\n" + "\n".join(f"  - {error}" for error in errors)
            raise ValueError(error_msg)
    
    def fetch_funding_map(self, base_url: str, category: str, timeout: int = 10) -> Dict[str, Dict]:
        """
        Récupère les taux de funding pour une catégorie donnée.
        
        Args:
            base_url: URL de base de l'API Bybit
            category: Catégorie (linear ou inverse)
            timeout: Timeout pour les requêtes HTTP
            
        Returns:
            Dict[str, Dict]: Dictionnaire {symbol: {funding, volume, next_funding_time}}
            
        Raises:
            RuntimeError: En cas d'erreur HTTP ou API
        """
        funding_map = {}
        cursor = ""
        page_index = 0
        
        rate_limiter = get_rate_limiter()
        while True:
            # Construire l'URL avec pagination
            url = f"{base_url}/v5/market/tickers"
            params = {
                "category": category,
                "limit": 1000  # Limite maximum supportée par l'API Bybit
            }
            if cursor:
                params["cursor"] = cursor
                
            try:
                page_index += 1
                # Respecter le rate limit avant chaque appel
                rate_limiter.acquire()
                client = get_http_client(timeout=timeout)
                response = client.get(url, params=params)
                
                # Vérifier le statut HTTP
                if response.status_code >= 400:
                    raise RuntimeError(
                        f"Erreur HTTP Bybit GET {url} | category={category} limit={params.get('limit')} "
                        f"cursor={params.get('cursor', '-')} timeout={timeout}s page={page_index} "
                        f"collected={len(funding_map)} | status={response.status_code} "
                        f"detail=\"{response.text[:200]}\""
                    )
                
                data = response.json()
                
                # Vérifier le retCode
                if data.get("retCode") != 0:
                    ret_code = data.get("retCode")
                    ret_msg = data.get("retMsg", "")
                    raise RuntimeError(
                        f"Erreur API Bybit GET {url} | category={category} limit={params.get('limit')} "
                        f"cursor={params.get('cursor', '-')} timeout={timeout}s page={page_index} "
                        f"collected={len(funding_map)} | retCode={ret_code} retMsg=\"{ret_msg}\""
                    )
                
                result = data.get("result", {})
                tickers = result.get("list", [])
                
                # Extraire les funding rates, volumes et temps de funding
                for ticker in tickers:
                    symbol = ticker.get("symbol", "")
                    funding_rate = ticker.get("fundingRate")
                    volume_24h = ticker.get("volume24h")
                    next_funding_time = ticker.get("nextFundingTime")
                    
                    if symbol and funding_rate is not None:
                        try:
                            funding_map[symbol] = {
                                "funding": float(funding_rate),
                                "volume": float(volume_24h) if volume_24h is not None else 0.0,
                                "next_funding_time": next_funding_time
                            }
                        except (ValueError, TypeError):
                            # Ignorer si les données ne sont pas convertibles en float
                            pass
                
                # Vérifier s'il y a une page suivante
                next_page_cursor = result.get("nextPageCursor")
                if not next_page_cursor:
                    break
                cursor = next_page_cursor
                    
            except httpx.RequestError as e:
                raise RuntimeError(
                    f"Erreur réseau Bybit GET {url} | category={category} limit={params.get('limit')} "
                    f"cursor={params.get('cursor', '-')} timeout={timeout}s page={page_index} "
                    f"collected={len(funding_map)} | error={e}"
                )
            except Exception as e:
                if "Erreur" in str(e):
                    raise
                else:
                    raise RuntimeError(
                        f"Erreur inconnue Bybit GET {url} | category={category} limit={params.get('limit')} "
                        f"cursor={params.get('cursor', '-')} timeout={timeout}s page={page_index} "
                        f"collected={len(funding_map)} | error={e}"
                    )
        
        return funding_map
    
    def fetch_spread_data(self, base_url: str, symbols: List[str], timeout: int = 10, category: str = "linear") -> Dict[str, float]:
        """
        Récupère les spreads via /v5/market/tickers paginé, puis filtre localement.
        
        Args:
            base_url: URL de base de l'API Bybit
            symbols: Liste cible des symboles à retourner
            timeout: Timeout HTTP
            category: "linear" ou "inverse"
            
        Returns:
            Dict[str, float]: map {symbol: spread_pct}
        """
        wanted = set(symbols)
        found: Dict[str, float] = {}
        url = f"{base_url}/v5/market/tickers"
        params = {"category": category, "limit": 1000}
        cursor = ""
        page_index = 0
        rate_limiter = get_rate_limiter()
        
        while True:
            page_index += 1
            if cursor:
                params["cursor"] = cursor
            else:
                params.pop("cursor", None)
                
            try:
                rate_limiter.acquire()
                client = get_http_client(timeout=timeout)
                resp = client.get(url, params=params)
                
                if resp.status_code >= 400:
                    raise RuntimeError(
                        f"Erreur HTTP Bybit GET {url} | category={category} page={page_index} "
                        f"limit={params.get('limit')} cursor={params.get('cursor','-')} status={resp.status_code} "
                        f"detail=\"{resp.text[:200]}\""
                    )
                
                data = resp.json()
                if data.get("retCode") != 0:
                    raise RuntimeError(
                        f"Erreur API Bybit GET {url} | category={category} page={page_index} "
                        f"retCode={data.get('retCode')} retMsg=\"{data.get('retMsg','')}\""
                    )
                
                result = data.get("result", {})
                tickers = result.get("list", [])
                
                for t in tickers:
                    sym = t.get("symbol")
                    if sym in wanted:
                        bid1 = t.get("bid1Price")
                        ask1 = t.get("ask1Price")
                        try:
                            if bid1 is not None and ask1 is not None:
                                b = float(bid1)
                                a = float(ask1)
                                if b > 0 and a > 0:
                                    mid = (a + b) / 2
                                    if mid > 0:
                                        found[sym] = (a - b) / mid
                        except (ValueError, TypeError):
                            # Erreur de conversion numérique - ignorer silencieusement
                            pass
                
                # Fin pagination
                next_cursor = result.get("nextPageCursor")
                # Arrêt anticipé si on a tout trouvé
                if len(found) >= len(wanted):
                    break
                if not next_cursor:
                    break
                cursor = next_cursor
                
            except (httpx.RequestError, httpx.TimeoutException, httpx.HTTPStatusError) as e:
                self.logger.error(
                    f"Erreur réseau spread paginé page={page_index} category={category}: {type(e).__name__}: {e}"
                )
                break
            except (ValueError, TypeError, KeyError) as e:
                self.logger.warning(
                    f"Erreur données spread paginé page={page_index} category={category}: {type(e).__name__}: {e}"
                )
                break
            except Exception as e:
                self.logger.error(
                    f"Erreur inattendue spread paginé page={page_index} category={category}: {type(e).__name__}: {e}"
                )
                break
        
        # Fallback unitaire pour les symboles manquants
        missing = [s for s in symbols if s not in found]
        for s in missing:
            try:
                val = self._fetch_single_spread(base_url, s, timeout, category)
                if val is not None:
                    found[s] = val
            except (httpx.RequestError, ValueError, TypeError):
                # Erreurs réseau ou conversion - ignorer silencieusement pour le fallback
                pass
        
        return found
    
    def _fetch_single_spread(self, base_url: str, symbol: str, timeout: int, category: str) -> Optional[float]:
        """
        Récupère le spread pour un seul symbole.
        
        Args:
            base_url: URL de base de l'API Bybit
            symbol: Symbole à analyser
            timeout: Timeout pour les requêtes HTTP
            category: Catégorie des symboles ("linear" ou "inverse")
            
        Returns:
            Spread en pourcentage ou None si erreur
        """
        try:
            url = f"{base_url}/v5/market/tickers"
            params = {"category": category, "symbol": symbol}
            
            rate_limiter = get_rate_limiter()
            rate_limiter.acquire()
            client = get_http_client(timeout=timeout)
            response = client.get(url, params=params)
            
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Erreur HTTP Bybit GET {url} | category={category} symbol={symbol} "
                    f"timeout={timeout}s status={response.status_code} detail=\"{response.text[:200]}\""
                )
            
            data = response.json()
            
            if data.get("retCode") != 0:
                ret_code = data.get("retCode")
                ret_msg = data.get("retMsg", "")
                raise RuntimeError(
                    f"Erreur API Bybit GET {url} | category={category} symbol={symbol} "
                    f"timeout={timeout}s retCode={ret_code} retMsg=\"{ret_msg}\""
                )
            
            result = data.get("result", {})
            tickers = result.get("list", [])
            
            if not tickers:
                return None
            
            ticker = tickers[0]
            bid1_price = ticker.get("bid1Price")
            ask1_price = ticker.get("ask1Price")
            
            if bid1_price is not None and ask1_price is not None:
                try:
                    bid1 = float(bid1_price)
                    ask1 = float(ask1_price)
                    
                    if bid1 > 0 and ask1 > 0:
                        spread_pct = (ask1 - bid1) / ((ask1 + bid1) / 2)
                        return spread_pct
                except (ValueError, TypeError, ZeroDivisionError):
                    pass
            
            return None
            
        except Exception:
            return None
    
    def calculate_funding_time_remaining(self, next_funding_time) -> str:
        """Retourne "Xh Ym Zs" à partir d'un timestamp Bybit (ms) ou ISO."""
        if not next_funding_time:
            return "-"
        try:
            import datetime
            funding_dt = None
            if isinstance(next_funding_time, (int, float)):
                funding_dt = datetime.datetime.fromtimestamp(float(next_funding_time) / 1000, tz=datetime.timezone.utc)
            elif isinstance(next_funding_time, str):
                if next_funding_time.isdigit():
                    funding_dt = datetime.datetime.fromtimestamp(float(next_funding_time) / 1000, tz=datetime.timezone.utc)
                else:
                    funding_dt = datetime.datetime.fromisoformat(next_funding_time.replace('Z', '+00:00'))
                    if funding_dt.tzinfo is None:
                        funding_dt = funding_dt.replace(tzinfo=datetime.timezone.utc)
            if funding_dt is None:
                return "-"
            now = datetime.datetime.now(datetime.timezone.utc)
            delta = (funding_dt - now).total_seconds()
            if delta <= 0:
                return "-"
            total_seconds = int(delta)
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            if hours > 0:
                return f"{hours}h {minutes}m {seconds}s"
            if minutes > 0:
                return f"{minutes}m {seconds}s"
            return f"{seconds}s"
        except Exception as e:
            self.logger.error(f"Erreur calcul temps funding formaté: {type(e).__name__}: {e}")
            return "-"
    
    def calculate_funding_minutes_remaining(self, next_funding_time) -> Optional[float]:
        """Retourne les minutes restantes avant le prochain funding (pour filtrage)."""
        if not next_funding_time:
            return None
        try:
            import datetime
            funding_dt = None
            if isinstance(next_funding_time, (int, float)):
                funding_dt = datetime.datetime.fromtimestamp(float(next_funding_time) / 1000, tz=datetime.timezone.utc)
            elif isinstance(next_funding_time, str):
                if next_funding_time.isdigit():
                    funding_dt = datetime.datetime.fromtimestamp(float(next_funding_time) / 1000, tz=datetime.timezone.utc)
                else:
                    funding_dt = datetime.datetime.fromisoformat(next_funding_time.replace('Z', '+00:00'))
                    if funding_dt.tzinfo is None:
                        funding_dt = funding_dt.replace(tzinfo=datetime.timezone.utc)
            if funding_dt is None:
                return None
            now = datetime.datetime.now(datetime.timezone.utc)
            delta_sec = (funding_dt - now).total_seconds()
            if delta_sec <= 0:
                return None
            return delta_sec / 60.0  # Convertir en minutes
        except Exception as e:
            self.logger.error(f"Erreur calcul minutes funding: {type(e).__name__}: {e}")
            return None
    
    def filter_by_funding(
        self, 
        perp_data: Dict, 
        funding_map: Dict, 
        funding_min: Optional[float], 
        funding_max: Optional[float], 
        volume_min: Optional[float], 
        volume_min_millions: Optional[float], 
        limite: Optional[int], 
        funding_time_min_minutes: Optional[int] = None, 
        funding_time_max_minutes: Optional[int] = None
    ) -> List[Tuple[str, float, float, str]]:
        """
        Filtre les symboles par funding, volume et fenêtre temporelle avant funding.
        
        Args:
            perp_data: Données des perpétuels (linear, inverse, total)
            funding_map: Dictionnaire des funding rates, volumes et temps de funding
            funding_min: Funding minimum en valeur absolue
            funding_max: Funding maximum en valeur absolue
            volume_min: Volume minimum (ancien format)
            volume_min_millions: Volume minimum en millions (nouveau format)
            limite: Limite du nombre d'éléments
            funding_time_min_minutes: Temps minimum en minutes avant prochain funding
            funding_time_max_minutes: Temps maximum en minutes avant prochain funding
            
        Returns:
            Liste des (symbol, funding, volume, funding_time_remaining) triés
        """
        # Récupérer tous les symboles perpétuels
        all_symbols = list(set(perp_data["linear"] + perp_data["inverse"]))
        
        # Déterminer le volume minimum à utiliser (priorité : volume_min_millions > volume_min)
        effective_volume_min = None
        if volume_min_millions is not None:
            effective_volume_min = volume_min_millions * 1_000_000  # Convertir en valeur brute
        elif volume_min is not None:
            effective_volume_min = volume_min
        
        # Filtrer par funding, volume et fenêtre temporelle
        filtered_symbols = []
        for symbol in all_symbols:
            if symbol in funding_map:
                data = funding_map[symbol]
                funding = data["funding"]
                volume = data["volume"]
                next_funding_time = data.get("next_funding_time")
                
                # Appliquer les bornes funding/volume (utiliser valeur absolue pour funding)
                if funding_min is not None and abs(funding) < funding_min:
                    continue
                if funding_max is not None and abs(funding) > funding_max:
                    continue
                if effective_volume_min is not None and volume < effective_volume_min:
                    continue
                
                # Appliquer le filtre temporel si demandé
                if funding_time_min_minutes is not None or funding_time_max_minutes is not None:
                    # Utiliser la fonction centralisée pour calculer les minutes restantes
                    minutes_remaining = self.calculate_funding_minutes_remaining(next_funding_time)
                    
                    # Si pas de temps valide alors qu'on filtre, rejeter
                    if minutes_remaining is None:
                        continue
                    if (funding_time_min_minutes is not None and 
                        minutes_remaining < float(funding_time_min_minutes)):
                        continue
                    if (funding_time_max_minutes is not None and 
                        minutes_remaining > float(funding_time_max_minutes)):
                        continue
                
                # Calculer le temps restant avant le prochain funding (formaté)
                funding_time_remaining = self.calculate_funding_time_remaining(next_funding_time)
                
                filtered_symbols.append((symbol, funding, volume, funding_time_remaining))
        
        # Trier par |funding| décroissant
        filtered_symbols.sort(key=lambda x: abs(x[1]), reverse=True)
        
        # Appliquer la limite
        if limite is not None:
            filtered_symbols = filtered_symbols[:limite]
        
        return filtered_symbols
    
    def filter_by_spread(
        self, 
        symbols_data: List[Tuple[str, float, float, str]], 
        spread_data: Dict[str, float], 
        spread_max: Optional[float]
    ) -> List[Tuple[str, float, float, str, float]]:
        """
        Filtre les symboles par spread maximum.
        
        Args:
            symbols_data: Liste des (symbol, funding, volume, funding_time_remaining)
            spread_data: Dictionnaire des spreads {symbol: spread_pct}
            spread_max: Spread maximum autorisé
            
        Returns:
            Liste des (symbol, funding, volume, funding_time_remaining, spread_pct) filtrés
        """
        if spread_max is None:
            # Pas de filtre de spread, ajouter 0.0 comme spread par défaut
            return [(symbol, funding, volume, funding_time_remaining, 0.0) 
                    for symbol, funding, volume, funding_time_remaining in symbols_data]
        
        filtered_symbols = []
        for symbol, funding, volume, funding_time_remaining in symbols_data:
            if symbol in spread_data:
                spread_pct = spread_data[symbol]
                if spread_pct <= spread_max:
                    filtered_symbols.append((symbol, funding, volume, funding_time_remaining, spread_pct))
        
        return filtered_symbols
    
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
            self.logger.info("📡 Récupération des funding rates pour linear (optimisé)…")
            funding_map = self.fetch_funding_map(base_url, "linear", 10)
        elif categorie == "inverse":
            self.logger.info("📡 Récupération des funding rates pour inverse (optimisé)…")
            funding_map = self.fetch_funding_map(base_url, "inverse", 10)
        else:  # "both"
            self.logger.info("📡 Récupération des funding rates pour linear+inverse (optimisé: parallèle)…")
            # Paralléliser les requêtes linear et inverse
            with ThreadPoolExecutor(max_workers=2) as executor:
                # Lancer les deux requêtes en parallèle
                linear_future = executor.submit(self.fetch_funding_map, base_url, "linear", 10)
                inverse_future = executor.submit(self.fetch_funding_map, base_url, "inverse", 10)
                
                # Attendre les résultats
                linear_funding = linear_future.result()
                inverse_funding = inverse_future.result()
            
            funding_map = {**linear_funding, **inverse_funding}  # Merger (priorité au dernier)
        
        if not funding_map:
            self.logger.warning("⚠️ Aucun funding disponible pour la catégorie sélectionnée")
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
        filtered_symbols = self.filter_by_funding(
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
            self.logger.info(f"🔎 Évaluation du spread (REST tickers) pour {len(symbols_to_check)} symboles…")
            
            try:
                spread_data = {}
                
                # Séparer les symboles par catégorie pour les requêtes spread
                linear_symbols_for_spread = [s for s in symbols_to_check if category_of_symbol(s, self.symbol_categories) == "linear"]
                inverse_symbols_for_spread = [s for s in symbols_to_check if category_of_symbol(s, self.symbol_categories) == "inverse"]
                
                # Paralléliser les requêtes de spreads pour linear et inverse
                if linear_symbols_for_spread or inverse_symbols_for_spread:
                    self.logger.info(f"🔎 Récupération spreads (optimisé: batch=200, parallèle) - linear: {len(linear_symbols_for_spread)}, inverse: {len(inverse_symbols_for_spread)}…")
                    
                    with ThreadPoolExecutor(max_workers=2) as executor:
                        futures = {}
                        
                        # Lancer les requêtes en parallèle si nécessaire
                        if linear_symbols_for_spread:
                            futures['linear'] = executor.submit(self.fetch_spread_data, base_url, linear_symbols_for_spread, 10, "linear")
                        
                        if inverse_symbols_for_spread:
                            futures['inverse'] = executor.submit(self.fetch_spread_data, base_url, inverse_symbols_for_spread, 10, "inverse")
                        
                        # Récupérer les résultats
                        if 'linear' in futures:
                            linear_spread_data = futures['linear'].result()
                            spread_data.update(linear_spread_data)
                        
                        if 'inverse' in futures:
                            inverse_spread_data = futures['inverse'].result()
                            spread_data.update(inverse_spread_data)
                
                final_symbols = self.filter_by_spread(filtered_symbols, spread_data, spread_max)
                n2 = len(final_symbols)
                
                # Log des résultats du filtre spread
                rejected = n1 - n2
                spread_pct_display = spread_max * 100
                self.logger.info(f"✅ Filtre spread : gardés={n2} | rejetés={rejected} (seuil {spread_pct_display:.2f}%)")
                
            except Exception as e:
                self.logger.warning(f"⚠️ Erreur lors de la récupération des spreads : {e}")
                # Continuer sans le filtre de spread
                final_symbols = [(symbol, funding, volume, funding_time_remaining, 0.0) 
                               for symbol, funding, volume, funding_time_remaining in filtered_symbols]
        
        # Calculer la volatilité pour tous les symboles (même sans filtre)
        n_before_volatility = len(final_symbols) if final_symbols else 0
        if final_symbols:
            try:
                self.logger.info("🔎 Évaluation de la volatilité 5m pour tous les symboles…")
                final_symbols = volatility_tracker.filter_by_volatility(
                    final_symbols,
                    volatility_min,
                    volatility_max
                )
                n_after_volatility = len(final_symbols)
            except Exception as e:
                self.logger.warning(f"⚠️ Erreur lors du calcul de la volatilité : {e}")
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
        self.logger.info(f"🧮 Comptes | avant filtres = {n0} | après funding/volume/temps = {n1} | après spread = {n2} | après volatilité = {n_after_volatility} | après tri+limit = {n3}")
        
        if not final_symbols:
            self.logger.warning("⚠️ Aucun symbole ne correspond aux critères de filtrage")
            raise RuntimeError("Aucun symbole ne correspond aux critères de filtrage")
        
        # Séparer les symboles par catégorie
        if len(final_symbols[0]) == 6:
            linear_symbols = [
                symbol for symbol, _, _, _, _, _ in final_symbols 
                if category_of_symbol(symbol, self.symbol_categories) == "linear"
            ]
            inverse_symbols = [
                symbol for symbol, _, _, _, _, _ in final_symbols 
                if category_of_symbol(symbol, self.symbol_categories) == "inverse"
            ]
        elif len(final_symbols[0]) == 5:
            linear_symbols = [
                symbol for symbol, _, _, _, _ in final_symbols 
                if category_of_symbol(symbol, self.symbol_categories) == "linear"
            ]
            inverse_symbols = [
                symbol for symbol, _, _, _, _ in final_symbols 
                if category_of_symbol(symbol, self.symbol_categories) == "inverse"
            ]
        elif len(final_symbols[0]) == 4:
            linear_symbols = [
                symbol for symbol, _, _, _ in final_symbols 
                if category_of_symbol(symbol, self.symbol_categories) == "linear"
            ]
            inverse_symbols = [
                symbol for symbol, _, _, _ in final_symbols 
                if category_of_symbol(symbol, self.symbol_categories) == "inverse"
            ]
        else:
            linear_symbols = [
                symbol for symbol, _, _ in final_symbols 
                if category_of_symbol(symbol, self.symbol_categories) == "linear"
            ]
            inverse_symbols = [
                symbol for symbol, _, _ in final_symbols 
                if category_of_symbol(symbol, self.symbol_categories) == "inverse"
            ]
        
        # Construire funding_data avec les bonnes données
        funding_data = {}
        if len(final_symbols[0]) == 6:
            # Format: (symbol, funding, volume, funding_time_remaining, spread_pct, volatility_pct)
            funding_data = {
                symbol: (funding, volume, funding_time_remaining, spread_pct, volatility_pct) 
                for symbol, funding, volume, funding_time_remaining, spread_pct, volatility_pct in final_symbols
            }
        elif len(final_symbols[0]) == 5:
            # Format: (symbol, funding, volume, funding_time_remaining, spread_pct)
            funding_data = {
                symbol: (funding, volume, funding_time_remaining, spread_pct, None) 
                for symbol, funding, volume, funding_time_remaining, spread_pct in final_symbols
            }
        elif len(final_symbols[0]) == 4:
            # Format: (symbol, funding, volume, funding_time_remaining)
            funding_data = {
                symbol: (funding, volume, funding_time_remaining, 0.0, None) 
                for symbol, funding, volume, funding_time_remaining in final_symbols
            }
        else:
            # Format: (symbol, funding, volume)
            funding_data = {
                symbol: (funding, volume, "-", 0.0, None) 
                for symbol, funding, volume in final_symbols
            }
        
        # Stocker les résultats
        self.selected_symbols = list(funding_data.keys())
        self.funding_data = funding_data
        
        # Log des symboles retenus
        self.logger.info(f"🧭 Symboles retenus (Top {n3}) : {self.selected_symbols}")
        self.logger.info(f"📊 Symboles linear: {len(linear_symbols)}, inverse: {len(inverse_symbols)}")
        
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
