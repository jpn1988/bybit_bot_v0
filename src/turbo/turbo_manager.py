#!/usr/bin/env python3
"""
🚀 TurboManager - Gestion du mode turbo sur un set de symboles

Gère le mode turbo pour les paires sélectionnées :
- Start/stop par symbole
- Boucle rapide (thread) par symbole
- Placement d'ordres à entry_seconds
- Vérif filtres / sortie
"""

import time
import threading
from typing import Dict, Any, Optional, List
from utils import normalize_next_funding_to_epoch_seconds
from http_client_manager import get_http_client
from bybit_client import BybitPublicClient
from instruments import category_of_symbol
from logging import Logger


class TurboManager:
    """
    Gère le mode turbo sur un set de symboles :
    - Start/stop par symbole
    - Boucle rapide (thread) par symbole
    - Placement d'ordres à entry_seconds
    - Vérif filtres / sortie
    """
    
    def __init__(self, config: Dict[str, Any], data_fetcher, order_client, filters, scorer, volatility_tracker: Any, logger: Logger):
        """
        Initialise le TurboManager.
        
        Args:
            config: Configuration du bot (incluant turbo, positions, risk)
            data_fetcher: Client pour récupérer les données
            order_client: Client pour passer les ordres
            filters: Système de filtrage
            scorer: Moteur de scoring
            volatility_tracker: Tracker de volatilité
            logger: Logger pour les messages
        """
        self.cfg = config
        self.fetcher = data_fetcher
        self.order = order_client
        self.filters = filters
        self.scorer = scorer
        self.vol_tracker = volatility_tracker
        self.log = logger
        
        # État des threads actifs par symbole
        self.active: Dict[str, dict] = {}  # {symbol: {'thread': Thread, 'stop_flag': bool, 'meta': dict, 'state': dict}}
        
        # Cooldown par symbole (timestamp d'éligibilité)
        self.cooldown_until: Dict[str, float] = {}
        
        # Watchlist turbo pour suivre les symboles en turbo
        self.turbo_watchlist: set = set()
        
        # Flags pour marquer quand les données WS sont reçues par symbole
        self.ws_ready: Dict[str, bool] = {}
        
        # Flags pour marquer quand les premières données WS sont reçues par symbole
        self.has_ws_data: Dict[str, bool] = {}
        
        # Timeouts pour l'attente des données WS
        self.ws_timeout_seconds = self.cfg.get('turbo', {}).get('ws_timeout_seconds', 30)
        
        # Liste des symboles actifs pour le turbo
        self.symbols: List[str] = []
        
        # Métriques et observabilité
        self.metrics = {
            'turbo_entries': 0,
            'turbo_exits': 0,
            'turbo_miss': 0,
            'turbo_filter_break': 0,
            'turbo_errors': 0,
            'turbo_skips': 0
        }
        
        # Configuration turbo
        self.turbo_config = config.get('turbo', {})
        self.enabled = self.turbo_config.get('enabled', False)
        self.trigger_seconds = self.turbo_config.get('trigger_seconds', 70)
        self.entry_seconds = self.turbo_config.get('entry_seconds', 60)
        self.refresh_ms = self.turbo_config.get('refresh_ms', 1000)
        self.max_parallel_pairs = self.turbo_config.get('max_parallel_pairs', 2)
        self.tick_logging = self.turbo_config.get('tick_logging', True)
        self.cooldown_s = self.turbo_config.get('cooldown_s', 120)
        self.cancel_on_filter_break = self.turbo_config.get('cancel_on_filter_break', True)
        self.miss_order_timeout_s = self.turbo_config.get('miss_order_timeout_s', 10)
        self.allow_midcycle_topn_switch = self.turbo_config.get('allow_midcycle_topn_switch', False)
        # Flag debug applicatif
        self.debug_logs = bool(config.get('debug_logs', False))
        
        # Log de configuration turbo (concise)
        self.log.info(f"[Turbo] Config: trigger={self.trigger_seconds}s | entry={self.entry_seconds}s | enabled={self.enabled}")
        
        # Vérification de la configuration
        if self.trigger_seconds <= 0:
            self.log.warning(f"⚠️ [Turbo Config] trigger_seconds={self.trigger_seconds}s est invalide, utilisation de 70s par défaut")
            self.trigger_seconds = 70
        
        # Configuration positions
        self.positions_config = config.get('positions', {})
        self.leverage = self.positions_config.get('leverage', 5)
        self.capital_fraction = self.positions_config.get('capital_fraction', 0.2)
        self.post_only = self.positions_config.get('post_only', True)
        self.close_at_funding = self.positions_config.get('close_at_funding', True)
        self.reduce_only_on_exit = self.positions_config.get('reduce_only_on_exit', True)
        self.exit_order_type = self.positions_config.get('exit_order_type', 'limit_post_only')
        self.price_policy = self.positions_config.get('price_policy', 'best_bid')
        self.maker_offset_bps = self.positions_config.get('maker_offset_bps', 0)
        self.min_notional_usd = self.positions_config.get('min_notional_usd', 10)
        
        # Configuration risque
        self.risk_config = config.get('risk', {})
        self.max_open_positions = self.risk_config.get('max_open_positions', 2)
        self.max_trades_per_day = self.risk_config.get('max_trades_per_day', 50)
        
        self.log.info(f"🚀 TurboManager initialisé - enabled={self.enabled}")
        
        # Tests internes désactivés par défaut (trop verbeux)
        if self.debug_logs:
            try:
                self.test_funding_time_calculation()
            except Exception:
                pass
    
    def start_for_symbol(self, symbol: str, meta: dict) -> bool:
        """
        Démarre la boucle turbo pour un symbole si non déjà actif et pas en cooldown.
        
        Args:
            symbol: Symbole à démarrer en turbo
            meta: Métadonnées du symbole (funding, volume, etc.)
            
        Returns:
            bool: True si démarré avec succès, False sinon
        """
        if not self.enabled:
            self.log.debug(f"Mode turbo désactivé, ignoré pour {symbol}")
            return False
            
        if symbol in self.active:
            self.log.debug(f"Turbo déjà actif pour {symbol}")
            return False
            
        # Vérifier l'éligibilité (cooldown)
        if not self.is_eligible(symbol):
            if symbol in self.cooldown_until:
                now = time.time()
                remaining = int(self.cooldown_until[symbol] - now)
                self.log.debug(f"Cooldown actif pour {symbol}, {remaining}s restantes")
            return False
            
        # Vérifier le nombre max de paires parallèles
        if len(self.active) >= self.max_parallel_pairs:
            self.metrics['turbo_skips'] += 1
            self.log.info(f"🚫 [Turbo SKIP] {symbol} | capacity reached ({len(self.active)}/{self.max_parallel_pairs})")
            return False
            
        try:
            # Vérifier si les données WebSocket sont déjà disponibles
            if self.has_ws_data.get(symbol, False):
                self.log.info(f"[Turbo] Données WS prêtes pour {symbol} → démarrage")
            else:
                # Attendre les premières données WebSocket avec timeout
                self.log.info(f"[Turbo] En attente des données WS pour {symbol}…")
                wait_start = time.time()
                
                while time.time() - wait_start < self.ws_timeout_seconds:
                    if self.has_ws_data.get(symbol, False):
                        self.log.info(f"✅ [Turbo READY] {symbol} -> premières données WS reçues, boucle turbo démarrée")
                        break
                    
                    # Vérifier le timeout
                    elapsed = time.time() - wait_start
                    if elapsed >= self.ws_timeout_seconds:
                        self.log.warning(f"[Turbo] Aucune donnée WS après {self.ws_timeout_seconds}s pour {symbol}")
                        self.metrics['turbo_skips'] += 1
                        return False
                    
                    time.sleep(0.5)
                
                # Double vérification après la boucle
                if not self.has_ws_data.get(symbol, False):
                    self.log.warning(f"[Turbo] Timeout données WS pour {symbol}")
                    self.metrics['turbo_skips'] += 1
                    return False
            # Créer le stop flag pour ce symbole
            stop_flag = threading.Event()
            
            # Démarrer le thread turbo pour ce symbole
            thread = threading.Thread(
                target=self._run_turbo_loop,
                args=(symbol, stop_flag, meta),
                name=f"turbo-{symbol}",
                daemon=True
            )
            thread.start()
            
            # Stocker les informations du thread
            self.active[symbol] = {
                'thread': thread,
                'stop_flag': stop_flag,
                'meta': meta.copy(),
                'state': {
                    'entry_sent': False,
                    'order_id': None,
                    'entry_attempts': 0,
                    'position_open': False,
                    'entry_price': None,
                    'entry_qty': None,
                    'entry_side': None
                }
            }
            
            self.log.info(f"🚀 [Turbo] ON {symbol}")
            return True
            
        except Exception as e:
            self.log.error(f"Erreur démarrage turbo pour {symbol}: {e}")
            return False

    def _init_rest_ticker_if_missing(self, symbol: str) -> bool:
        """Initialise les données du symbole via REST si absentes. Retourne True si des données ont été injectées."""
        try:
            # Si des données existent déjà, ne rien faire
            try:
                ws_data = self.fetcher.get_price(symbol) if hasattr(self.fetcher, 'get_price') else {}
            except Exception:
                ws_data = {}
            if ws_data and ws_data.get('timestamp'):
                return True

            # Déterminer l'URL publique
            testnet = getattr(self.fetcher, 'testnet', True)
            base_url = BybitPublicClient(testnet=testnet, timeout=10).public_base_url()

            # Déterminer la catégorie du symbole
            symbol_categories = getattr(self.fetcher, 'symbol_categories', {})
            category = category_of_symbol(symbol, symbol_categories)

            # Appeler l'endpoint public tickers
            url = f"{base_url}/v5/market/tickers"
            params = {"category": category, "symbol": symbol}
            client = get_http_client(timeout=10)
            resp = client.get(url, params=params)
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code} {resp.text[:120]}")
            data = resp.json()
            if data.get("retCode") != 0:
                rc = data.get("retCode")
                rm = data.get("retMsg", "")
                raise RuntimeError(f"retCode={rc} retMsg=\"{rm}\"")
            result = (data.get("result") or {}).get("list") or []
            if not result:
                return False
            t = result[0]

            # Construire un ticker compatible avec le callback WS du fetcher
            ticker_data = {
                "symbol": symbol,
                "fundingRate": t.get("fundingRate"),
                "volume24h": t.get("turnover24h") or t.get("volume24h"),
                "bid1Price": t.get("bid1Price"),
                "ask1Price": t.get("ask1Price"),
                "nextFundingTime": t.get("nextFundingTime"),
                "markPrice": t.get("markPrice"),
                "lastPrice": t.get("lastPrice"),
            }

            # Injecter via le callback du fetcher pour remplir realtime_data + timestamp
            if hasattr(self.fetcher, "_update_realtime_data_from_ticker"):
                try:
                    self.fetcher._update_realtime_data_from_ticker(ticker_data)
                except Exception:
                    # Si l'injection via callback échoue, continuer silencieusement
                    pass

            # Vérifier si des données sont désormais disponibles
            try:
                ws_data2 = self.fetcher.get_price(symbol) if hasattr(self.fetcher, 'get_price') else {}
            except Exception:
                ws_data2 = {}
            return bool(ws_data2 and ws_data2.get('timestamp'))
        except Exception:
            raise
    
    def stop_for_symbol(self, symbol: str, reason: str = "Arrêt demandé"):
        """
        Stoppe la boucle turbo et nettoie l'état.
        
        Args:
            symbol: Symbole à arrêter
            reason: Raison de l'arrêt
        """
        if symbol not in self.active:
            self.log.debug(f"Turbo non actif pour {symbol}")
            return
            
        try:
            # Arrêter le thread via le stop flag
            if 'stop_flag' in self.active[symbol]:
                self.active[symbol]['stop_flag'].set()
            
            # Attendre que le thread se termine (avec timeout)
            if 'thread' in self.active[symbol]:
                thread = self.active[symbol]['thread']
                # Ne pas essayer de joindre le thread depuis lui-même
                if threading.current_thread() != thread:
                    thread.join(timeout=2.0)  # Timeout de 2 secondes
                    if thread.is_alive():
                        self.log.warning(f"Thread turbo pour {symbol} n'a pas pu être arrêté proprement")
            
            # Nettoyer l'état
            del self.active[symbol]
            
            # Mettre en cooldown si nécessaire
            if self.cooldown_s > 0:
                self.cooldown_until[symbol] = time.time() + self.cooldown_s
                self.log.info(f"⏰ Cooldown {self.cooldown_s}s pour {symbol}")
            
            # Incrémenter les métriques selon la raison
            if reason == "filter_break":
                self.metrics['turbo_filter_break'] += 1
            elif reason in ["funding_done", "miss", "fatal_error"]:
                self.metrics['turbo_exits'] += 1
            
            # Log de cleanup
            self.log.info(f"🛑 [Turbo OFF] {symbol} | reason={reason} | cooldown={self.cooldown_s}s")
            
        except Exception as e:
            self.log.error(f"Erreur arrêt turbo pour {symbol}: {e}")
    
    def is_active(self, symbol: str) -> bool:
        """
        Vérifie si le turbo est actif pour un symbole.
        
        Args:
            symbol: Symbole à vérifier
            
        Returns:
            bool: True si actif, False sinon
        """
        return symbol in self.active
    
    def is_eligible(self, symbol: str) -> bool:
        """
        Vérifie si un symbole est éligible pour le turbo (pas en cooldown).
        
        Args:
            symbol: Symbole à vérifier
            
        Returns:
            bool: True si éligible, False sinon
        """
        if symbol in self.cooldown_until:
            now = time.time()
            cooldown_until = self.cooldown_until[symbol]
            if now < cooldown_until:
                return False
            else:
                # Cooldown expiré, nettoyer
                del self.cooldown_until[symbol]
        
        return True
    
    def tick_once_for_tests(self, symbol: str) -> dict:
        """
        Point d'entrée testable pour un tick turbo unique (sans thread).
        
        Args:
            symbol: Symbole à traiter
            
        Returns:
            dict: Résultat du tick (pour les tests)
        """
        try:
            # Simulation d'un tick turbo
            result = {
                'symbol': symbol,
                'timestamp': time.time(),
                'status': 'processed',
                'funding_time_remaining': None,
                'should_enter': False,
                'should_exit': False
            }
            
            # Log du tick si activé
            if self.tick_logging:
                self.log.debug(f"🔍 Tick turbo test pour {symbol}")
            
            return result
            
        except Exception as e:
            self.log.error(f"Erreur tick turbo test pour {symbol}: {e}")
            return {
                'symbol': symbol,
                'timestamp': time.time(),
                'status': 'error',
                'error': str(e)
            }
    
    def _run_turbo_loop(self, symbol: str, stop_flag: threading.Event, meta: dict):
        """
        Boucle principale du mode turbo pour un symbole avec surveillance 1s.
        
        Args:
            symbol: Symbole à traiter
            stop_flag: Event pour arrêter le thread
            meta: Métadonnées du symbole
        """
        self.log.info(f"🔄 Boucle turbo démarrée pour {symbol}")
        
        try:
            while not stop_flag.is_set():
                try:
                    # Rafraîchir les données temps réel
                    data = self._get_realtime_snapshot(symbol)
                    
                    if data:
                        # Optionnel : recalculer le score pour diagnostic
                        if self.scorer and hasattr(self.scorer, 'recompute_for_symbol'):
                            try:
                                score = self.scorer.recompute_for_symbol(symbol, data)
                                data['score'] = score
                            except Exception as e:
                                # Réduire bruit en production
                                pass
                        
                        # Log des valeurs si activé
                        if self.tick_logging and self.debug_logs:
                            self._log_turbo_tick(symbol, data)
                        
                        # Vérifier si on doit placer un ordre d'entrée
                        self._check_and_place_entry_order(symbol, data)
                        
                        # Vérifier l'exécution de l'ordre
                        self._check_order_execution(symbol, data)
                        
                        # Vérifier la sortie au funding
                        if self._check_funding_exit(symbol, data):
                            # Position fermée au funding, arrêter le turbo
                            break
                        
                        # Vérifier les filtres de sécurité
                        if self._check_turbo_filters(symbol, data):
                            # Filtres cassés, arrêter le turbo
                            break
                        
                        # Vérifier si le symbole est toujours éligible
                        if not self._is_symbol_eligible_from_data(symbol, data):
                            self.log.info(f"📉 {symbol} n'est plus éligible, arrêt du turbo")
                            break
                    else:
                        # Données non disponibles → limiter le spam en INFO et non à chaque tick
                        self.log.info(f"[Turbo] En attente du timing… ({symbol})")
                    
                except Exception as e:
                    # Gestion des erreurs réseau/API
                    error_str = str(e)
                    
                    # Erreurs transitoires (retry au tick suivant)
                    if any(keyword in error_str.lower() for keyword in ['timeout', 'connection', 'network', 'temporary']):
                        self.log.warning(f"[Turbo] Erreur transitoire {symbol}, retry")
                        self.metrics['turbo_errors'] += 1
                    else:
                        # Erreur critique, arrêter le turbo
                        self.log.error(f"[Turbo] Erreur critique {symbol}: {e}")
                        self.metrics['turbo_errors'] += 1
                        self.stop_for_symbol(symbol, "fatal_error")
                        break
                
                # Attendre le prochain refresh
                stop_flag.wait(self.refresh_ms / 1000.0)
                
        except Exception as e:
            self.log.error(f"[Turbo] Erreur boucle {symbol}: {e}")
            self.metrics['turbo_errors'] += 1
        finally:
            self.log.info(f"🏁 Boucle turbo terminée pour {symbol}")
    
    def _get_realtime_snapshot(self, symbol: str) -> dict:
        """
        Récupère un snapshot des données temps réel pour un symbole.
        Fusionne les données REST et WebSocket si possible.
        Thread-safe avec _realtime_lock.
        
        Args:
            symbol: Symbole à récupérer
            
        Returns:
            dict: Données temps réel ou None si erreur
        """
        try:
            # Utiliser les données WS stockées en priorité
            if hasattr(self, 'ws_data') and symbol in self.ws_data:
                ws_data = self.ws_data[symbol]['data']
                self.log.debug(f"Utilisation des données WS stockées pour {symbol}")
            elif hasattr(self.fetcher, 'get_price'):
                # Fallback: utiliser le data_fetcher (PriceTracker) pour récupérer les données
                ws_data = self.fetcher.get_price(symbol)
                self.log.debug(f"Utilisation des données fetcher pour {symbol}")
            else:
                ws_data = {}
            
            # Récupérer les données REST depuis le watchlist manager
            rest_data = {}
            if hasattr(self.fetcher, 'watchlist_manager'):
                original_funding_data = self.fetcher.watchlist_manager.get_original_funding_data()
                rest_ts = original_funding_data.get(symbol)
                if rest_ts:
                    now = time.time()
                    rest_data['funding_time_s'] = max(0, int(rest_ts - now))
                
                # Fusionner les données
                snapshot = {
                    'symbol': symbol,
                    'timestamp': time.time(),
                    'funding_time_s': None,  # Calculé séparément
                    'funding_rate': ws_data.get('funding_rate'),
                    'volume_usd_24h': ws_data.get('volume24h'),
                    'spread_pct': None,  # Calculé séparément
                    'vol_pct': None,     # Récupéré depuis volatility_tracker
                }
                
                # Calculer le funding_time_s depuis next_funding_time
                next_funding_time = ws_data.get('next_funding_time')
                if next_funding_time:
                    now = time.time()
                    ts_sec = normalize_next_funding_to_epoch_seconds(next_funding_time)
                    if ts_sec is not None:
                        remaining = int(ts_sec - now)
                        snapshot['funding_time_s'] = max(0, remaining)
                        if self.debug_logs:
                            self.log.info(f"[Turbo DBG] {symbol} t={remaining}s")
                
                # Calculer le spread si possible
                if ws_data.get('bid1_price') and ws_data.get('ask1_price'):
                    bid = float(ws_data['bid1_price'])
                    ask = float(ws_data['ask1_price'])
                    if bid > 0 and ask > 0:
                        snapshot['spread_pct'] = (ask - bid) / bid
                
                # Récupérer la volatilité depuis le tracker (thread-safe)
                if self.vol_tracker and hasattr(self.vol_tracker, 'get_volatility'):
                    try:
                        vol_pct = self.vol_tracker.get_volatility(symbol)
                        snapshot['vol_pct'] = vol_pct
                    except Exception:
                        pass
                
                # Utiliser les données REST comme fallback pour funding_time
                if snapshot['funding_time_s'] is None and 'funding_time_s' in rest_data:
                    snapshot['funding_time_s'] = rest_data['funding_time_s']
                
                return snapshot
                
        except Exception as e:
            self.log.debug(f"Erreur récupération snapshot pour {symbol}: {e}")
            return None
    
    def _log_turbo_tick(self, symbol: str, data: dict):
        """
        Log les valeurs du tick turbo.
        
        Args:
            symbol: Symbole
            data: Données du tick
        """
        try:
            funding_time = data.get('funding_time_s', 'N/A')
            funding_rate = data.get('funding_rate', 'N/A')
            volume = data.get('volume_usd_24h', 'N/A')
            spread = data.get('spread_pct', 'N/A')
            vol = data.get('vol_pct', 'N/A')
            score = data.get('score', 'N/A')
            
            # Formater les valeurs
            if isinstance(funding_time, (int, float)):
                funding_time = f"{funding_time}s"
            if isinstance(funding_rate, (int, float)):
                funding_rate = f"{funding_rate*100:.4f}%"
            if isinstance(volume, (int, float)):
                volume = f"{volume/1_000_000:.1f}M"
            if isinstance(spread, (int, float)):
                spread = f"{spread*100:.3f}%"
            if isinstance(vol, (int, float)):
                vol = f"{vol*100:.3f}%"
            if isinstance(score, (int, float)):
                score = f"{score:.1f}"
            
            self.log.info(f"[Turbo DBG] {symbol} t={funding_time} f={funding_rate} v={volume} s={spread} vol={vol} score={score}")
            
        except Exception as e:
            self.log.debug(f"Erreur log tick pour {symbol}: {e}")
    
    def _is_symbol_eligible_from_data(self, symbol: str, data: dict) -> bool:
        """
        Vérifie si un symbole est encore éligible pour le turbo basé sur les données.
        
        Args:
            symbol: Symbole à vérifier
            data: Données temps réel
            
        Returns:
            bool: True si éligible, False sinon
        """
        try:
            funding_time_s = data.get('funding_time_s')
            if funding_time_s is None:
                return False
                
            # Vérifier si on est dans la fenêtre turbo
            is_eligible = funding_time_s <= self.trigger_seconds
            return is_eligible
            
        except Exception as e:
            self.log.debug(f"Erreur vérification éligibilité {symbol}: {e}")
            return False
    
    def _check_and_place_entry_order(self, symbol: str, data: dict):
        """
        Vérifie si on doit placer un ordre d'entrée et le place si nécessaire.
        
        Args:
            symbol: Symbole
            data: Données temps réel
        """
        try:
            # Vérifier si l'ordre a déjà été envoyé
            if symbol not in self.active or self.active[symbol]['state']['entry_sent']:
                return
            
            # Vérifier si on est dans la fenêtre d'entrée
            funding_time_s = data.get('funding_time_s')
            if funding_time_s is None or funding_time_s > self.entry_seconds:
                return
            
            # Placer l'ordre d'entrée
            self._place_entry_order(symbol, data)
            
        except Exception as e:
            self.log.error(f"Erreur vérification entry order pour {symbol}: {e}")
    
    def _place_entry_order(self, symbol: str, data: dict):
        """
        Place un ordre d'entrée maker.
        
        Args:
            symbol: Symbole
            data: Données temps réel
        """
        try:
            # Calculer la quantité
            quantity = self._calculate_entry_quantity(symbol, data)
            if quantity is None:
                return
            
            # Déterminer le prix
            price = self._calculate_entry_price(symbol, data)
            if price is None:
                return
            
            # Déterminer le côté (buy/sell) basé sur le funding rate
            side = self._determine_entry_side(symbol, data)
            if side is None:
                return
            
            # Construire l'ordre
            order_data = {
                'symbol': symbol,
                'side': side,
                'order_type': 'LIMIT',
                'qty': str(quantity),
                'price': str(price),
                'time_in_force': 'PostOnly' if self.post_only else 'GTC',
                'reduce_only': False
            }
            
            # Envoyer l'ordre via le client d'ordres
            if self.order and hasattr(self.order, 'place_order'):
                try:
                    response = self.order.place_order(order_data)
                    order_id = response.get('orderId') if response else None
                    
                    if order_id:
                        # Mémoriser l'ordre
                        self.active[symbol]['state']['entry_sent'] = True
                        self.active[symbol]['state']['order_id'] = order_id
                        self.active[symbol]['state']['entry_send_ts'] = time.time()
                        
                        # Incrémenter les métriques
                        self.metrics['turbo_entries'] += 1
                        
                        # Log de l'entrée
                        funding_rate = data.get('funding_rate', 0)
                        funding_pct = funding_rate * 100 if funding_rate else 0
                        self.log.info(f"🚀 [Turbo ENTRY] {symbol} | side={side} | price={price} | qty={quantity} | funding={funding_pct:.4f}% | t={data.get('funding_time_s', 'N/A')}s")
                        
                    else:
                        self.log.error(f"❌ Échec placement ordre pour {symbol}: {response}")
                        
                except Exception as e:
                    self.log.error(f"❌ Erreur placement ordre pour {symbol}: {e}")
                    # Gérer les erreurs Bybit spécifiques
                    self._handle_order_error(symbol, e)
            else:
                self.log.warning(f"⚠️ Client d'ordres non disponible pour {symbol}")
                
        except Exception as e:
            self.log.error(f"Erreur placement entry order pour {symbol}: {e}")
    
    def _calculate_entry_quantity(self, symbol: str, data: dict) -> float:
        """
        Calcule la quantité pour l'ordre d'entrée.
        
        Args:
            symbol: Symbole
            data: Données temps réel
            
        Returns:
            float: Quantité calculée ou None si erreur
        """
        try:
            # Récupérer le prix actuel
            last_price = self._get_current_price(symbol, data)
            if last_price is None:
                return None
            
            # Calculer le notionnel
            # Note: account_equity devrait être récupéré depuis le client d'ordres
            # Pour l'instant, on utilise une valeur par défaut
            account_equity = 10000.0  # TODO: Récupérer depuis le client d'ordres
            notionnel = account_equity * self.capital_fraction
            
            # Calculer la quantité
            quantity = (notionnel * self.leverage) / last_price
            
            # Vérifier le minimum notional
            min_notional = self.min_notional_usd
            if notionnel < min_notional:
                self.log.warning(f"⚠️ Notionnel {notionnel:.2f} < min {min_notional} pour {symbol}")
                return None
            
            # Arrondir la quantité selon les règles du symbole
            # TODO: Utiliser les règles de précision du symbole
            quantity = round(quantity, 3)
            
            return quantity
            
        except Exception as e:
            self.log.error(f"Erreur calcul quantité pour {symbol}: {e}")
            return None
    
    def _calculate_entry_price(self, symbol: str, data: dict) -> float:
        """
        Calcule le prix pour l'ordre d'entrée selon la politique de prix.
        
        Args:
            symbol: Symbole
            data: Données temps réel
            
        Returns:
            float: Prix calculé ou None si erreur
        """
        try:
            # Récupérer les prix bid/ask
            bid_price = self._get_bid_price(symbol, data)
            ask_price = self._get_ask_price(symbol, data)
            
            if bid_price is None or ask_price is None:
                return None
            
            # Appliquer la politique de prix
            if self.price_policy == 'best_bid':
                price = bid_price * (1 + self.maker_offset_bps / 10000)
            elif self.price_policy == 'best_ask':
                price = ask_price * (1 - self.maker_offset_bps / 10000)
            elif self.price_policy == 'mid':
                price = (bid_price + ask_price) / 2
                # Ajuster pour rester maker
                if self.maker_offset_bps > 0:
                    price = price * (1 + self.maker_offset_bps / 10000)
            else:
                self.log.warning(f"⚠️ Politique de prix inconnue: {self.price_policy}")
                return None
            
            # Arrondir le prix selon les règles du symbole
            # TODO: Utiliser les règles de précision du symbole
            price = round(price, 2)
            
            return price
            
        except Exception as e:
            self.log.error(f"Erreur calcul prix pour {symbol}: {e}")
            return None
    
    def _determine_entry_side(self, symbol: str, data: dict) -> str:
        """
        Détermine le côté de l'ordre (buy/sell) basé sur le funding rate.
        
        Args:
            symbol: Symbole
            data: Données temps réel
            
        Returns:
            str: 'Buy' ou 'Sell' ou None si erreur
        """
        try:
            funding_rate = data.get('funding_rate', 0)
            
            # Si funding positif, on veut être long (buy)
            # Si funding négatif, on veut être short (sell)
            if funding_rate > 0:
                return 'Buy'
            elif funding_rate < 0:
                return 'Sell'
            else:
                # Funding neutre, utiliser le score ou une heuristique
                score = data.get('score', 0)
                return 'Buy' if score > 0 else 'Sell'
                
        except Exception as e:
            self.log.error(f"Erreur détermination côté pour {symbol}: {e}")
            return None
    
    def _get_current_price(self, symbol: str, data: dict) -> float:
        """Récupère le prix actuel du symbole."""
        try:
            # Essayer d'abord les données temps réel
            if hasattr(self.fetcher, 'get_price'):
                ws_data = self.fetcher.get_price(symbol)
                last_price = ws_data.get('last_price')
                if last_price:
                    return float(last_price)
            
            # Fallback sur les données fournies
            bid_price = self._get_bid_price(symbol, data)
            ask_price = self._get_ask_price(symbol, data)
            
            if bid_price and ask_price:
                return (bid_price + ask_price) / 2
            
            return None
            
        except Exception as e:
            self.log.debug(f"Erreur récupération prix pour {symbol}: {e}")
            return None
    
    def _get_bid_price(self, symbol: str, data: dict) -> float:
        """Récupère le prix bid."""
        try:
            if hasattr(self.fetcher, 'get_price'):
                ws_data = self.fetcher.get_price(symbol)
                bid_price = ws_data.get('bid1_price')
                if bid_price:
                    return float(bid_price)
            return None
        except Exception:
            return None
    
    def _get_ask_price(self, symbol: str, data: dict) -> float:
        """Récupère le prix ask."""
        try:
            if hasattr(self.fetcher, 'get_price'):
                ws_data = self.fetcher.get_price(symbol)
                ask_price = ws_data.get('ask1_price')
                if ask_price:
                    return float(ask_price)
            return None
        except Exception:
            return None
    
    def _handle_order_error(self, symbol: str, error: Exception):
        """
        Gère les erreurs de placement d'ordre.
        
        Args:
            symbol: Symbole
            error: Exception
        """
        try:
            error_str = str(error)
            
            # Gérer les erreurs Bybit spécifiques
            if '10006' in error_str or '10002' in error_str:
                self.log.warning(f"⚠️ Erreur Bybit {error_str} pour {symbol}, retry possible")
                
                # Incrémenter le compteur de tentatives
                if symbol in self.active:
                    self.active[symbol]['state']['entry_attempts'] += 1
                    
                    # Retry une seule fois
                    if self.active[symbol]['state']['entry_attempts'] <= 1:
                        self.log.info(f"🔄 Retry entry order pour {symbol}")
                        # TODO: Implémenter le retry avec backoff
                    else:
                        self.log.error(f"❌ Max tentatives atteint pour {symbol}")
            else:
                self.log.error(f"❌ Erreur placement ordre pour {symbol}: {error_str}")
                
        except Exception as e:
            self.log.error(f"Erreur gestion erreur ordre pour {symbol}: {e}")
    
    def _check_turbo_filters(self, symbol: str, data: dict) -> bool:
        """
        Vérifie les filtres de sécurité en mode turbo.
        
        Args:
            symbol: Symbole à vérifier
            data: Données temps réel
            
        Returns:
            bool: True si les filtres sont cassés (arrêt nécessaire), False sinon
        """
        try:
            # Récupérer les seuils de filtres depuis la config
            funding_min = self.cfg.get('funding_min')
            funding_max = self.cfg.get('funding_max')
            volume_min_millions = self.cfg.get('volume_min_millions')
            spread_max = self.cfg.get('spread_max')
            volatility_max = self.cfg.get('volatility_max')
            
            # Vérifier le funding
            funding_rate = data.get('funding_rate', 0)
            if funding_min is not None and funding_rate < funding_min:
                self._handle_filter_break(symbol, f"funding {funding_rate:.6f} < min {funding_min:.6f}")
                return True
            if funding_max is not None and funding_rate > funding_max:
                self._handle_filter_break(symbol, f"funding {funding_rate:.6f} > max {funding_max:.6f}")
                return True
            
            # Vérifier le volume
            volume_usd = data.get('volume_usd_24h', 0)
            if volume_min_millions is not None:
                volume_millions = volume_usd / 1_000_000
                if volume_millions < volume_min_millions:
                    self._handle_filter_break(symbol, f"volume {volume_millions:.1f}M < min {volume_min_millions:.1f}M")
                    return True
            
            # Vérifier le spread
            spread_pct = data.get('spread_pct', 0)
            if spread_max is not None and spread_pct > spread_max:
                self._handle_filter_break(symbol, f"spread {spread_pct:.4f} > max {spread_max:.4f}")
                return True
            
            # Vérifier la volatilité
            vol_pct = data.get('vol_pct', 0)
            if volatility_max is not None and vol_pct > volatility_max:
                self._handle_filter_break(symbol, f"volatility {vol_pct:.4f} > max {volatility_max:.4f}")
                return True
            
            # Vérifier le timeout de l'ordre (MISS)
            if self._check_order_timeout(symbol, data):
                return True
            
            return False
            
        except Exception as e:
            self.log.error(f"Erreur vérification filtres pour {symbol}: {e}")
            return False
    
    def _handle_filter_break(self, symbol: str, reason: str):
        """
        Gère la casse d'un filtre en mode turbo.
        
        Args:
            symbol: Symbole concerné
            reason: Raison de la casse du filtre
        """
        try:
            if not self.cancel_on_filter_break:
                self.log.warning(f"⚠️ Filtre cassé pour {symbol}: {reason} (cancel_on_filter_break=false)")
                return
            
            # Vérifier s'il y a un ordre en attente
            if symbol in self.active and self.active[symbol]['state']['order_id']:
                order_id = self.active[symbol]['state']['order_id']
                
                # Annuler l'ordre
                if self.order and hasattr(self.order, 'cancel_order'):
                    try:
                        self.order.cancel_order(order_id)
                        self.log.info(f"🚫 [Turbo EXIT] {symbol} | reason=filter_break | order_cancelled={order_id}")
                    except Exception as e:
                        self.log.error(f"❌ Erreur annulation ordre {order_id} pour {symbol}: {e}")
                else:
                    self.log.warning(f"⚠️ Client d'ordres non disponible pour annuler {order_id}")
            
            # Arrêter le turbo pour ce symbole
            self.stop_for_symbol(symbol, "filter_break")
            
        except Exception as e:
            self.log.error(f"Erreur gestion filter break pour {symbol}: {e}")
    
    def _check_order_timeout(self, symbol: str, data: dict) -> bool:
        """
        Vérifie si l'ordre a expiré (MISS).
        
        Args:
            symbol: Symbole concerné
            data: Données temps réel
            
        Returns:
            bool: True si timeout détecté, False sinon
        """
        try:
            if symbol not in self.active:
                return False
            
            state = self.active[symbol]['state']
            
            # Vérifier si un ordre a été envoyé
            if not state['entry_sent'] or not state['order_id']:
                return False
            
            # Vérifier si on est après le funding (funding_time_s <= 0)
            funding_time_s = data.get('funding_time_s', 0)
            if funding_time_s <= 0:
                self._handle_order_miss(symbol, "not filled before funding")
                return True
            
            # Vérifier le timeout spécifique
            if 'entry_send_ts' in state:
                now = time.time()
                entry_send_ts = state['entry_send_ts']
                timeout_seconds = self.miss_order_timeout_s
                
                if now - entry_send_ts > timeout_seconds:
                    self._handle_order_miss(symbol, f"timeout {timeout_seconds}s")
                    return True
            
            return False
            
        except Exception as e:
            self.log.error(f"Erreur vérification timeout pour {symbol}: {e}")
            return False
    
    def _handle_order_miss(self, symbol: str, reason: str):
        """
        Gère un ordre manqué (MISS).
        
        Args:
            symbol: Symbole concerné
            reason: Raison du MISS
        """
        try:
            if symbol not in self.active:
                return
            
            state = self.active[symbol]['state']
            order_id = state.get('order_id')
            
            # Annuler l'ordre s'il existe
            if order_id and self.order and hasattr(self.order, 'cancel_order'):
                try:
                    self.order.cancel_order(order_id)
                    self.log.info(f"🚫 Ordre {order_id} annulé pour {symbol}")
                except Exception as e:
                    self.log.debug(f"Erreur annulation ordre {order_id}: {e}")
            
            # Incrémenter les métriques
            self.metrics['turbo_miss'] += 1
            
            # Log du MISS
            self.log.warning(f"❌ [Turbo MISS] {symbol} | reason={reason}")
            
            # Arrêter le turbo
            self.stop_for_symbol(symbol, "miss")
            
        except Exception as e:
            self.log.error(f"Erreur gestion MISS pour {symbol}: {e}")
    
    def _check_order_execution(self, symbol: str, data: dict):
        """
        Vérifie si l'ordre d'entrée a été exécuté.
        
        Args:
            symbol: Symbole concerné
            data: Données temps réel
        """
        try:
            if symbol not in self.active:
                return
            
            state = self.active[symbol]['state']
            
            # Vérifier si un ordre a été envoyé
            if not state['entry_sent'] or not state['order_id']:
                return
            
            # Vérifier si la position est déjà ouverte
            if state['position_open']:
                return
            
            # Vérifier l'état de l'ordre via le client d'ordres
            if self.order and hasattr(self.order, 'get_order_status'):
                try:
                    order_status = self.order.get_order_status(state['order_id'])
                    
                    if order_status and order_status.get('status') == 'FILLED':
                        # Ordre exécuté, ouvrir la position
                        self._open_position(symbol, data)
                        
                except Exception as e:
                    self.log.debug(f"Erreur vérification statut ordre pour {symbol}: {e}")
            else:
                # Simulation: considérer l'ordre comme exécuté après un délai
                if 'entry_send_ts' in state:
                    now = time.time()
                    entry_send_ts = state['entry_send_ts']
                    
                    # Simuler l'exécution après 1 seconde
                    if now - entry_send_ts > 1.0 and not state['position_open']:
                        self._open_position(symbol, data)
            
        except Exception as e:
            self.log.error(f"Erreur vérification exécution pour {symbol}: {e}")
    
    def _open_position(self, symbol: str, data: dict):
        """
        Ouvre une position après exécution de l'ordre.
        
        Args:
            symbol: Symbole concerné
            data: Données temps réel
        """
        try:
            if symbol not in self.active:
                return
            
            state = self.active[symbol]['state']
            
            # Marquer la position comme ouverte
            state['position_open'] = True
            
            # Récupérer les données d'entrée depuis l'ordre placé
            # Note: En réalité, ces données devraient venir de l'ordre exécuté
            # Pour l'instant, on utilise des valeurs par défaut
            state['entry_price'] = data.get('last_price', 50000.0)
            state['entry_qty'] = 0.2  # Valeur par défaut
            state['entry_side'] = 'Buy'  # Valeur par défaut
            
            # Log de l'ouverture de position
            self.log.info(f"[Turbo] Position ouverte {symbol} side={state['entry_side']} price={state['entry_price']} qty={state['entry_qty']}")
            
        except Exception as e:
            self.log.error(f"Erreur ouverture position pour {symbol}: {e}")
    
    def _check_funding_exit(self, symbol: str, data: dict) -> bool:
        """
        Vérifie si on doit fermer la position au funding.
        
        Args:
            symbol: Symbole concerné
            data: Données temps réel
            
        Returns:
            bool: True si la position doit être fermée, False sinon
        """
        try:
            if symbol not in self.active:
                return False
            
            state = self.active[symbol]['state']
            
            # Vérifier si la position est ouverte
            if not state['position_open']:
                return False
            
            # Vérifier si on doit fermer au funding
            if not self.close_at_funding:
                return False
            
            # Vérifier si on est au funding (funding_time_s <= 0)
            funding_time_s = data.get('funding_time_s', 0)
            if funding_time_s > 0:
                return False
            
            # Fermer la position
            self._close_position_at_funding(symbol, data)
            return True
            
        except Exception as e:
            self.log.error(f"Erreur vérification sortie funding pour {symbol}: {e}")
            return False
    
    def _close_position_at_funding(self, symbol: str, data: dict):
        """
        Ferme la position au funding.
        
        Args:
            symbol: Symbole concerné
            data: Données temps réel
        """
        try:
            if symbol not in self.active:
                return
            
            state = self.active[symbol]['state']
            
            # Déterminer le côté de sortie (opposé à l'entrée)
            entry_side = state.get('entry_side', 'Buy')
            exit_side = 'Sell' if entry_side == 'Buy' else 'Buy'
            
            # Calculer le prix de sortie
            exit_price = self._calculate_exit_price(symbol, data, exit_side)
            if exit_price is None:
                self.log.error(f"❌ Impossible de calculer le prix de sortie pour {symbol}")
                return
            
            # Construire l'ordre de sortie
            exit_order_data = {
                'symbol': symbol,
                'side': exit_side,
                'order_type': 'MARKET' if self.exit_order_type == 'market' else 'LIMIT',
                'qty': str(state['entry_qty']),
                'reduce_only': True,
                'time_in_force': 'IOC' if self.exit_order_type == 'market' else 'PostOnly'
            }
            
            # Ajouter le prix pour les ordres LIMIT
            if self.exit_order_type == 'limit_post_only':
                exit_order_data['price'] = str(exit_price)
            
            # Envoyer l'ordre de sortie
            if self.order and hasattr(self.order, 'place_order'):
                try:
                    response = self.order.place_order(exit_order_data)
                    exit_order_id = response.get('orderId') if response else None
                    
                    if exit_order_id:
                        # Calculer le PnL et slippage
                        pnl = self._calculate_pnl(symbol, state, exit_price)
                        slippage = self._calculate_slippage(symbol, state, exit_price)
                        
                        # Incrémenter les métriques
                        self.metrics['turbo_exits'] += 1
                        
                        # Log de la sortie
                        self.log.info(f"[Turbo] Funding capturé {symbol} pnl={pnl:.2f} slippage={slippage:.4f}")
                        
                        # Arrêter le turbo
                        self.stop_for_symbol(symbol, "funding_done")
                        
                    else:
                        self.log.error(f"❌ Échec placement ordre de sortie pour {symbol}: {response}")
                        
                except Exception as e:
                    self.log.error(f"❌ Erreur placement ordre de sortie pour {symbol}: {e}")
            else:
                self.log.warning(f"⚠️ Client d'ordres non disponible pour {symbol}")
                
        except Exception as e:
            self.log.error(f"Erreur fermeture position pour {symbol}: {e}")
    
    def _calculate_exit_price(self, symbol: str, data: dict, exit_side: str) -> float:
        """
        Calcule le prix de sortie selon la politique de prix.
        
        Args:
            symbol: Symbole concerné
            data: Données temps réel
            exit_side: Côté de sortie (Buy/Sell)
            
        Returns:
            float: Prix de sortie calculé ou None si erreur
        """
        try:
            # Récupérer les prix bid/ask
            bid_price = self._get_bid_price(symbol, data)
            ask_price = self._get_ask_price(symbol, data)
            
            if bid_price is None or ask_price is None:
                return None
            
            # Appliquer la politique de prix
            if self.price_policy == 'best_bid':
                price = bid_price * (1 + self.maker_offset_bps / 10000)
            elif self.price_policy == 'best_ask':
                price = ask_price * (1 - self.maker_offset_bps / 10000)
            elif self.price_policy == 'mid':
                price = (bid_price + ask_price) / 2
                # Ajuster pour rester maker
                if self.maker_offset_bps > 0:
                    price = price * (1 + self.maker_offset_bps / 10000)
            else:
                self.log.warning(f"⚠️ Politique de prix inconnue: {self.price_policy}")
                return None
            
            # Arrondir le prix selon les règles du symbole
            price = round(price, 2)
            
            return price
            
        except Exception as e:
            self.log.error(f"Erreur calcul prix de sortie pour {symbol}: {e}")
            return None
    
    def _calculate_pnl(self, symbol: str, state: dict, exit_price: float) -> float:
        """
        Calcule le PnL de la position.
        
        Args:
            symbol: Symbole concerné
            state: État de la position
            exit_price: Prix de sortie
            
        Returns:
            float: PnL calculé
        """
        try:
            entry_price = state.get('entry_price', 0)
            entry_qty = state.get('entry_qty', 0)
            entry_side = state.get('entry_side', 'Buy')
            
            if entry_price <= 0 or entry_qty <= 0:
                return 0.0
            
            # Calculer le PnL selon le côté
            if entry_side == 'Buy':
                # Position longue : PnL = (exit_price - entry_price) * qty
                pnl = (exit_price - entry_price) * entry_qty
            else:
                # Position courte : PnL = (entry_price - exit_price) * qty
                pnl = (entry_price - exit_price) * entry_qty
            
            return pnl
            
        except Exception as e:
            self.log.error(f"Erreur calcul PnL pour {symbol}: {e}")
            return 0.0
    
    def _calculate_slippage(self, symbol: str, state: dict, exit_price: float) -> float:
        """
        Calcule le slippage de la position.
        
        Args:
            symbol: Symbole concerné
            state: État de la position
            exit_price: Prix de sortie
            
        Returns:
            float: Slippage en pourcentage
        """
        try:
            entry_price = state.get('entry_price', 0)
            
            if entry_price <= 0:
                return 0.0
            
            # Calculer le slippage en pourcentage
            slippage = abs(exit_price - entry_price) / entry_price
            
            return slippage
            
        except Exception as e:
            self.log.error(f"Erreur calcul slippage pour {symbol}: {e}")
            return 0.0
    
    def get_status(self) -> dict:
        """
        Retourne le statut du TurboManager.
        
        Returns:
            dict: Statut actuel
        """
        return {
            'enabled': self.enabled,
            'active_symbols': list(self.active.keys()),
            'active_count': len(self.active),
            'max_parallel_pairs': self.max_parallel_pairs,
            'cooldown_symbols': list(self.cooldown_until.keys()),
            'refresh_ms': self.refresh_ms,
            'tick_logging': self.tick_logging,
            'metrics': self.metrics.copy()
        }
    
    def get_metrics_summary(self) -> str:
        """
        Retourne un résumé des métriques turbo.
        
        Returns:
            str: Résumé formaté des métriques
        """
        active_count = len(self.active)
        cooldown_count = len(self.cooldown_until)
        
        summary = f"📊 [Turbo Metrics] Active: {active_count}/{self.max_parallel_pairs} | Cooldown: {cooldown_count}"
        summary += f" | Entries: {self.metrics['turbo_entries']} | Exits: {self.metrics['turbo_exits']}"
        summary += f" | Miss: {self.metrics['turbo_miss']} | FilterBreak: {self.metrics['turbo_filter_break']}"
        summary += f" | Errors: {self.metrics['turbo_errors']} | Skips: {self.metrics['turbo_skips']}"
        
        return summary
    
    def log_metrics_summary(self):
        """
        Log un résumé des métriques turbo.
        """
        self.log.info(self.get_metrics_summary())
    
    def check_candidates(self, pairs):
        """
        Vérifie les candidats pour le déclenchement turbo.
        
        Args:
            pairs: Liste des paires sélectionnées avec leurs données
        """
        if not self.enabled:
            return
            
        for p in pairs:
            # Extraire les données de la paire
            if isinstance(p, (list, tuple)) and len(p) >= 4:
                # Format: (symbol, funding, volume, funding_time_str, spread, volatility, score)
                symbol = p[0]
                funding_time_str = p[3] if len(p) > 3 else None
                
                # Debug: tracer la source des données (désactivé par défaut)
                if self.debug_logs:
                    self.log.info(f"[Turbo DBG] {symbol} raw={p} ft='{funding_time_str}'")
                
                # Parser le funding_time en secondes
                ft_seconds = self._parse_funding_time_to_seconds(funding_time_str, symbol)
            else:
                continue
                
            if ft_seconds is None:
                if self.debug_logs:
                    self.log.debug(f"[Turbo DBG] parsing_failed {symbol} ft='{funding_time_str}'")
                continue

            # CORRECTION: Calculer le temps restant dans le cycle actuel (8h = 28800s)
            # Si ft_seconds = 6298s (1h44m), alors temps_écoulé = 28800 - 6298 = 22502s
            # Temps restant dans le cycle = 28800 - (28800 - ft_seconds) = ft_seconds
            # Mais on veut le temps restant AVANT la fin du cycle, pas le temps jusqu'au prochain funding
            
            # Le temps restant dans le cycle actuel = ft_seconds (temps jusqu'au prochain funding)
            # Mais pour le turbo, on veut savoir si on est dans les dernières X secondes du cycle
            # Si le prochain funding est dans ft_seconds, alors le cycle actuel se termine dans ft_seconds
            # Donc le temps restant dans le cycle actuel = ft_seconds
            
            time_remaining_in_cycle = ft_seconds
            condition_met = time_remaining_in_cycle <= self.trigger_seconds
            
            if self.debug_logs:
                self.log.info(f"[Turbo DBG] {symbol} t={time_remaining_in_cycle}s trigger={self.trigger_seconds}s cond={condition_met}")

            # Déclenchement Turbo - SEULEMENT si funding_time_remaining <= trigger_seconds
            if condition_met and symbol not in self.turbo_watchlist:
                self.log.info(f"[Turbo] Condition OK (symbol={symbol})")
                # Marquer pour tentative d'entrée turbo
                self.turbo_watchlist.add(symbol)
            elif not condition_met:
                continue  # IMPORTANT: arrêter ici si la condition n'est pas remplie
            
            # Si on arrive ici, c'est que condition_met=True
            # Vérifier la connexion WebSocket avant d'activer le turbo
            if not self.has_ws_data.get(symbol, False):
                self.log.info(f"[Turbo] En attente des données WS pour {symbol}…")
                # Info explicite s'il n'y a aucun tick reçu avant timeout côté start_for_symbol
                # Garder dans la watchlist pour réessayer au prochain tick
                continue
            
            # Vérifier si on a des données WS récentes pour ce symbole
            if hasattr(self, 'ws_data') and symbol in self.ws_data:
                ws_data = self.ws_data[symbol]
                # Vérifier que les données ne sont pas trop anciennes (max 5 secondes)
                if time.time() - ws_data['last_update'] > 5:
                    self.log.info(f"⏳ [Turbo WAIT] {symbol} -> données WS trop anciennes, en attente de nouveaux ticks...")
                    continue
            
            # Souscrire aux topics WebSocket avec retry (les logs de souscription sont gérés par ws_public)
            ws_subscription_success = self._subscribe_ws_with_retry(symbol)
            if not ws_subscription_success:
                self.log.error(f"[WS ERROR] Impossible de souscrire après 3 essais (symbole={symbol})")
                self.turbo_watchlist.discard(symbol)
                continue
            
            # Démarrer le turbo pour ce symbole
            meta = {
                "funding_time": ft_seconds,
                "score": p[6] if len(p) > 6 else 0.0,
                    "funding_rate": p[1] if len(p) > 1 else 0.0,
                    "volume": p[2] if len(p) > 2 else 0.0,
                    "spread": p[4] if len(p) > 4 else 0.0,
                    "volatility": p[5] if len(p) > 5 else 0.0
                }
            
            # Démarrer le turbo
            success = self.start_for_symbol(symbol, meta)
            if not success:
                # Retirer de la watchlist si échec
                self.turbo_watchlist.discard(symbol)
            else:
                self.log.info(f"[Turbo] Entrée en Turbo sur {symbol} (t={ft_seconds}s)")
    
    def _check_ws_connection(self) -> bool:
        """
        Vérifie si la connexion WebSocket est active.
        
        Returns:
            bool: True si la WS est connectée, False sinon
        """
        try:
            if not hasattr(self.fetcher, 'ws_manager') or not self.fetcher.ws_manager:
                return False
            
            ws_manager = self.fetcher.ws_manager
            if not hasattr(ws_manager, '_ws_conns') or not ws_manager._ws_conns:
                return False
            
            # Vérifier qu'au moins une connexion est active
            for conn in ws_manager._ws_conns:
                if hasattr(conn, 'ws') and conn.ws and hasattr(conn, 'running') and conn.running:
                    return True
            
            return False
        except Exception:
            return False
    
    def _subscribe_ws_with_retry(self, symbol: str, max_retries: int = 3) -> bool:
        """
        Souscrit aux topics WebSocket avec retry automatique.
        
        Args:
            symbol: Symbole à souscrire
            max_retries: Nombre maximum de tentatives
            
        Returns:
            bool: True si la souscription réussit, False sinon
        """
        for attempt in range(1, max_retries + 1):
            try:
                if hasattr(self.fetcher, 'ws_manager') and self.fetcher.ws_manager:
                    success = self.fetcher.ws_manager.subscribe_turbo_symbol(symbol)
                    if success:
                        return True
                    else:
                        if attempt < max_retries:
                            self.log.warning(f"[WS RETRY] Nouvelle tentative de souscription (symbole={symbol}, essai={attempt}/{max_retries})")
                            time.sleep(2)  # Attendre 2 secondes avant le retry
                        else:
                            self.log.error(f"[WS ERROR] Échec souscription après {attempt} tentatives (symbole={symbol})")
                else:
                    self.log.warning(f"[WS RETRY] WS Manager non disponible (symbole={symbol}, essai={attempt}/{max_retries})")
                    if attempt < max_retries:
                        time.sleep(2)
            except Exception as e:
                if attempt < max_retries:
                    self.log.warning(f"[WS RETRY] Erreur souscription (symbole={symbol}, essai={attempt}/{max_retries}): {e}")
                    time.sleep(2)
                else:
                    self.log.error(f"[WS ERROR] Erreur souscription après {attempt} tentatives (symbole={symbol}): {e}")
        
        return False
    
    def mark_ws_ready(self, symbol: str):
        """
        Marque qu'un symbole a reçu ses premières données WebSocket.
        
        Args:
            symbol: Symbole qui a reçu des données WS
        """
        if symbol not in self.ws_ready:
            self.ws_ready[symbol] = True
            self.log.info(f"[Turbo] Données WS prêtes {symbol}")
    
    def mark_ws_data_received(self, symbol: str):
        """
        Marque qu'un symbole a reçu ses premières données WebSocket (orderbook ou trade).
        
        Args:
            symbol: Symbole qui a reçu des données WS
        """
        if symbol not in self.has_ws_data:
            self.has_ws_data[symbol] = True
            self.log.info(f"[Turbo] WS données prêtes (symbol={symbol})")
    
    def on_ws_tick(self, symbol: str, data: dict):
        """
        Traite un tick WebSocket reçu pour un symbole.
        
        Args:
            symbol: Symbole qui a reçu le tick
            data: Données du tick (orderbook, trade, etc.)
        """
        try:
            # Log de debug pour confirmer la réception
            self.log.debug(f"📡 [Turbo WS] Tick reçu pour {symbol}: {type(data).__name__}")
            
            # Marquer que les données WS sont disponibles
            if symbol not in self.has_ws_data:
                self.has_ws_data[symbol] = True
                # debug only
                pass
            
            # Stocker les données pour utilisation dans la boucle turbo
            if not hasattr(self, 'ws_data'):
                self.ws_data = {}
            
            self.ws_data[symbol] = {
                'timestamp': time.time(),
                'data': data,
                'last_update': time.time()
            }
            
            # Si le symbole est en attente, le débloquer
            if symbol in self.turbo_watchlist and symbol not in self.active:
                # debug only
                pass
                
        except Exception as e:
            self.log.error(f"Erreur traitement tick WS pour {symbol}: {e}")
    
    def is_ws_ready(self, symbol: str) -> bool:
        """
        Vérifie si un symbole a reçu ses premières données WebSocket.
        
        Args:
            symbol: Symbole à vérifier
            
        Returns:
            bool: True si les données WS sont prêtes
        """
        return self.ws_ready.get(symbol, False)
    
    def update_watchlist(self, symbols: List[str]):
        """
        Met à jour la liste des symboles actifs pour le turbo.
        
        Args:
            symbols: Liste des symboles à suivre
        """
        # debug only
        pass
        if not symbols:
            self.log.warning("⚠️ Aucun symbole transmis au TurboManager")
        else:
            self.log.info(f"[Turbo] Watchlist active: {len(symbols)} symboles")
        self.symbols = symbols
    
    def _parse_funding_time_to_seconds(self, funding_time_str, symbol: str = None):
        """
        Parse le funding_time string en secondes.
        
        Args:
            funding_time_str: String du type "2h30m", "1m30s", "45s", etc.
            
        Returns:
            int: Nombre de secondes ou None si parsing échoue
        """
        if not funding_time_str or not isinstance(funding_time_str, str):
            return None
            
        try:
            import re
            
            # Parser "2h 16m 8s" format (avec espaces) - regex flexible
            match_full = re.match(r'(\d+)h\s*(\d+)m\s*(\d+)s', funding_time_str.strip())
            if match_full:
                hours = int(match_full.group(1))
                minutes = int(match_full.group(2))
                seconds = int(match_full.group(3))
                total = hours * 3600 + minutes * 60 + seconds
                if symbol:
                    self.log.debug(f"🔍 [PARSING] {symbol} '{funding_time_str}' -> {hours}h {minutes}m {seconds}s = {total}s")
                else:
                    self.log.debug(f"🔍 [PARSING] '{funding_time_str}' -> {hours}h {minutes}m {seconds}s = {total}s")
                return total
            
            # Parser "2h30m" format (sans espaces)
            match_h = re.match(r'(\d+)h(\d+)m', funding_time_str)
            if match_h:
                hours = int(match_h.group(1))
                minutes = int(match_h.group(2))
                return hours * 3600 + minutes * 60
            
            # Parser "1h15m" format (minutes seulement)
            match_h_only = re.match(r'(\d+)h', funding_time_str)
            if match_h_only:
                hours = int(match_h_only.group(1))
                return hours * 3600
            
            # Parser "1m30s" format
            match_m = re.match(r'(\d+)m(\d+)s', funding_time_str)
            if match_m:
                minutes = int(match_m.group(1))
                seconds = int(match_m.group(2))
                return minutes * 60 + seconds
            
            # Parser "45s" format
            match_s = re.match(r'(\d+)s', funding_time_str)
            if match_s:
                return int(match_s.group(1))
            
            # Fallback: essayer de parser manuellement si la regex échoue
            print(f"⚠️ [FALLBACK] Regex échouée pour '{funding_time_str}', tentative de parsing manuel")
            try:
                # Extraire les heures, minutes, secondes manuellement
                parts = funding_time_str.replace('h', ' ').replace('m', ' ').replace('s', '').split()
                if len(parts) >= 3:
                    hours = int(parts[0])
                    minutes = int(parts[1])
                    seconds = int(parts[2])
                    total = hours * 3600 + minutes * 60 + seconds
                    print(f"✅ [FALLBACK] Parsing manuel réussi: {hours}h {minutes}m {seconds}s = {total}s")
                    return total
            except Exception as e:
                print(f"❌ [FALLBACK] Parsing manuel échoué: {e}")
                
            return None
                
        except Exception:
            return None
    
    def test_funding_time_calculation(self):
        """
        Test unitaire simple pour valider le calcul du funding_time_remaining.
        """
        import time
        
        # Simuler un funding_time = now + 8760s (2h26)
        now = time.time()
        test_funding_time = now + 8760
        
        # Test avec next_funding_time en millisecondes (format Bybit)
        test_funding_time_ms = int(test_funding_time * 1000)
        
        # Simuler le calcul comme dans _get_realtime_snapshot
        # next_funding_time est déjà en secondes (conversion faite dans watchlist_filters.py)
        test_funding_time = test_funding_time_ms / 1000
        
        remaining = int(test_funding_time - now)
        
        self.log.info(f"🧪 [TEST] funding_time_calculation | expected=8760s | actual={remaining}s | diff={abs(8760-remaining)}s")
        
        # Vérifier que le calcul est correct (tolérance de 1 seconde)
        if abs(remaining - 8760) <= 1:
            self.log.info(f"✅ [TEST] funding_time_calculation PASSED")
            return True
        else:
            self.log.error(f"❌ [TEST] funding_time_calculation FAILED | expected=8760s | actual={remaining}s")
            return False
