#!/usr/bin/env python3
"""WebSocket publique Bybit v5 - Client réutilisable avec reconnexion automatique."""

import json
import time
import threading
import websocket
from typing import Callable, List, Optional
from metrics import record_ws_connection, record_ws_error
from constants.constants import LOG_EMOJIS, LOG_MESSAGES


class PublicWSClient:
    """
    Client WebSocket publique Bybit v5 réutilisable.
    
    Gère automatiquement la connexion, reconnexion, souscription aux symboles
    et le traitement des messages tickers.
    """
    
    def __init__(
        self, 
        category: str, 
        symbols: List[str], 
        testnet: bool, 
        logger, 
        on_ticker_callback: Callable[[dict], None],
        *,
        debug_ws: bool = False,
        debug_ws_inactivity_s: int = 10,
    ):
        """
        Initialise le client WebSocket publique.
        
        Args:
            category (str): Catégorie des symboles ("linear" ou "inverse")
            symbols (List[str]): Liste des symboles à suivre
            testnet (bool): Utiliser le testnet (True) ou le mainnet (False)
            logger: Instance du logger pour les messages
            on_ticker_callback (Callable): Fonction appelée pour chaque ticker reçu
        """
        self.category = category
        self.symbols = symbols
        self.testnet = testnet
        self.logger = logger
        self.on_ticker_callback = on_ticker_callback
        self.ws: Optional[websocket.WebSocketApp] = None
        self.running = False
        self.debug_ws = bool(debug_ws)
        self.debug_ws_inactivity_s = int(debug_ws_inactivity_s) if debug_ws_inactivity_s is not None else 10
        # Contrôle du bruit trades/orderbook
        try:
            from watchlist_manager import WatchlistManager
            tmp_wm = WatchlistManager(testnet=testnet, logger=logger)
            cfg = tmp_wm.load_and_validate_config()
            self.debug_trades = bool(((cfg.get('logging') or {}).get('debug_trades')))
            self.debug_ws_ticks = bool(((cfg.get('logging') or {}).get('debug_ws_ticks')))
            self.ws_ticks_summary_interval_s = int(((cfg.get('logging') or {}).get('ws_ticks_summary_interval_s') or 10))
        except Exception:
            self.debug_trades = False
            self.debug_ws_ticks = False
            self.ws_ticks_summary_interval_s = 10
        # Throttling des résumés de trades
        self._last_trade_summary_ts = {}
        self._last_trade_by_symbol = {}
        self.trade_summary_interval_s = 10
        # Throttling des résumés de ticks WS pour Turbo
        self._ws_ticks_count = {}
        self._ws_ticks_last_summary_ts = 0.0
        self._last_msg_ts_by_topic = {}
        self._last_warn_ts_by_topic = {}
        self._watchdog_thread = None
        self._watchdog_started = False
        
        # Compteur de messages pour heartbeat
        self._message_count = 0
        self._heartbeat_start_time = time.time()
        self._heartbeat_thread = None
        self._heartbeat_running = False
        
        # Configuration de reconnexion avec backoff progressif
        self.reconnect_delays = [1, 2, 5, 10, 30]  # secondes
        self.current_delay_index = 0
        
        # Callbacks optionnels pour événements de connexion
        self.on_open_callback: Optional[Callable] = None
        self.on_close_callback: Optional[Callable] = None
        self.on_error_callback: Optional[Callable] = None

    def _build_url(self) -> str:
        """Construit l'URL WebSocket selon la catégorie et l'environnement."""
        if self.category == "linear":
            return (
                "wss://stream-testnet.bybit.com/v5/public/linear" if self.testnet 
                else "wss://stream.bybit.com/v5/public/linear"
            )
        else:
            return (
                "wss://stream-testnet.bybit.com/v5/public/inverse" if self.testnet 
                else "wss://stream.bybit.com/v5/public/inverse"
            )

    def _on_open(self, ws):
        """Callback interne appelé à l'ouverture de la connexion."""
        # Logger l'URL exacte utilisée
        try:
            ws_url = self._build_url()
            self.logger.info(f"[WS DEBUG] Connexion ouverte sur: {ws_url}")
        except Exception:
            pass
        
        self.logger.info(f"{LOG_EMOJIS['websocket']} {LOG_MESSAGES['ws_opened'].format(category=self.category)}")
        
        # Enregistrer la connexion WebSocket
        record_ws_connection(connected=True)
        
        # Réinitialiser l'index de délai de reconnexion après une connexion réussie
        self.current_delay_index = 0
        
        # S'abonner aux topics pour tous les symboles
        topics = []
        if self.symbols:
            # Souscrire aux trades publics, carnet d'ordres niveau 1 et tickers (maj funding/volume/bid-ask)
            for symbol in self.symbols:
                topics.extend([
                    f"publicTrade.{symbol}",      # Derniers trades
                    f"orderbook.1.{symbol}",      # Carnet d'ordres niveau 1
                    f"tickers.{symbol}"           # Tickers (fundingRate, volume24h, bid/ask, mark/last)
                ])
        
        # Initialiser le suivi d'inactivité par topic
        if self.debug_ws:
            now = time.time()
            for t in topics:
                self._last_msg_ts_by_topic[t] = now
                self._last_warn_ts_by_topic[t] = 0.0
        
        # Log concis des souscriptions
        try:
            if topics:
                self.logger.info(f"[WS SUBSCRIBE] {len(topics)} topics ({self.category})")
        except Exception:
            pass
        
        if not topics:
            self.logger.warning(f"⚠️ Aucun topic à souscrire pour {self.category}")
            return
        
        subscribe_message = {
            "op": "subscribe",
            "args": topics
        }
        
        try:
            ws.send(json.dumps(subscribe_message))
            self.logger.info(
                f"{LOG_EMOJIS['watchlist']} {LOG_MESSAGES['ws_subscription'].format(count=len(self.symbols), category=self.category)}"
            )
            self.logger.info(f"✅ Souscription réussie pour {len(topics)} topics: {topics}")
        except (json.JSONEncodeError, ConnectionError, OSError) as e:
            self.logger.error(
                f"❌ Erreur souscription WebSocket {self.category}: {type(e).__name__}: {e}"
            )
        except Exception as e:
            self.logger.warning(f"⚠️ Erreur souscription {self.category}: {e}")
        else:
            # Vérifier si la liste des symboles est vraiment vide
            if not self.symbols:
                self.logger.warning(f"⚠️ Aucun symbole à suivre pour {self.category}")
            else:
                # Log de debug pour comprendre pourquoi le warning apparaît
                self.logger.info(f"[DEBUG] WebSocket {self.category} a {len(self.symbols)} symboles: {self.symbols}")
        
        # Appeler le callback externe si défini
        if self.on_open_callback:
            try:
                self.on_open_callback()
            except Exception as e:
                self.logger.warning(f"{LOG_EMOJIS['warn']} {LOG_MESSAGES['ws_callback_error'].format(error=e)} {e}")

        # Démarrer le watchdog d'inactivité si demandé
        if self.debug_ws and not self._watchdog_started and self.symbols:
            try:
                self._watchdog_started = True
                self._watchdog_thread = __import__('threading').Thread(target=self._inactivity_watchdog, daemon=True)
                self._watchdog_thread.start()
            except Exception:
                pass
        
        # Démarrer le heartbeat
        self._start_heartbeat()

    def _on_message(self, ws, message):
        """Callback interne appelé à chaque message reçu."""
        # Incrémenter le compteur de messages
        self._message_count += 1
        
        # DEBUG: Logger les 200 premiers caractères du message brut si debug_ws activé
        if self.debug_ws:
            try:
                message_preview = message[:200] if len(message) > 200 else message
                self.logger.info(f"[WS RAW] {message_preview}")
            except Exception:
                pass
        
        # Parsing classique
        try:
            data = json.loads(message)
            topic = data.get("topic", "")
            
            # Gérer les réponses de souscription (succès/erreur)
            if data.get("op") == "subscribe":
                success = data.get("success", True)
                # Les erreurs Bybit renvoient souvent ret_msg / retMsg
                ret_msg = data.get("ret_msg") or data.get("retMsg") or ""
                request = data.get("request", {}) or {}
                args = request.get("args") or data.get("args") or []
                if not success:
                    self.logger.error(f"[WS SUBSCRIBE ERROR] {ret_msg or 'unknown error'} | args={args}")
                else:
                    # Optionnel: log succès détaillé
                    self.logger.info(f"[WS SUBSCRIBE OK] args={args}")
                return
            
            # Mettre à jour l'horodatage de dernière réception pour le watchdog
            if self.debug_ws and topic:
                try:
                    self._last_msg_ts_by_topic[topic] = time.time()
                except Exception:
                    pass
            
            # Traitement des différents types de messages
            if topic.startswith("instrument_info."):
                # Messages d'informations d'instrument (pour turbo)
                instrument_data = data.get("data", {})
                if instrument_data:
                    try:
                        symbol = instrument_data.get("symbol", "UNKNOWN")
                        
                        # Marquer que les données WS sont prêtes pour le turbo
                        self._notify_turbo_ws_ready(symbol)
                        self._notify_turbo_ws_data_received(symbol)
                        
                        # Notifier le TurboManager avec les données complètes
                        self._notify_turbo_ws_tick(symbol, instrument_data)
                        self._count_ws_tick(symbol)
                        
                        # Réduit en mode non-debug (trop verbeux)
                        pass
                    except Exception:
                        self.logger.info(f"[Turbo TICK] {topic}: {instrument_data}")
            elif topic.startswith("publicTrade."):
                # Messages de trades publics
                raw = data.get("data", {})
                trade = None
                if isinstance(raw, list):
                    trade = raw[0] if raw else None
                elif isinstance(raw, dict):
                    trade = raw
                if trade:
                    try:
                        # Extraire les champs robustement (formats V5 possibles)
                        symbol = trade.get("symbol") or trade.get("s") or "UNKNOWN"
                        price = trade.get("price") or trade.get("p")
                        qty = trade.get("size") or trade.get("v")
                        # Notifier TurboManager
                        self._notify_turbo_ws_ready(symbol)
                        self._notify_turbo_ws_data_received(symbol)
                        self._notify_turbo_ws_tick(symbol, trade)
                        self._count_ws_tick(symbol)
                        # Logging: détaillé seulement si debug_trades
                        if self.debug_trades:
                            self.logger.info(f"[Trade] {topic}: {raw}")
                        else:
                            self._maybe_log_trade_summary(symbol, price, qty)
                    except Exception:
                        if self.debug_trades:
                            self.logger.info(f"[Trade] {topic}: {raw}")
            elif topic.startswith("orderbook.1."):
                # Messages de carnet d'ordres niveau 1 (Bybit V5)
                orderbook_data = data.get("data", {})
                if orderbook_data:
                    try:
                        symbol = orderbook_data.get("s", "UNKNOWN")
                        self._notify_turbo_ws_ready(symbol)
                        self._notify_turbo_ws_data_received(symbol)
                        self._notify_turbo_ws_tick(symbol, orderbook_data)
                        self._count_ws_tick(symbol)
                        if self.debug_trades:
                            bids = orderbook_data.get("b", orderbook_data.get("bids", []))
                            asks = orderbook_data.get("a", orderbook_data.get("asks", []))
                            best_bid = "N/A"
                            best_ask = "N/A"
                            if bids and len(bids) > 0 and len(bids[0]) > 0:
                                best_bid = str(bids[0][0])
                            if asks and len(asks) > 0 and len(asks[0]) > 0:
                                best_ask = str(asks[0][0])
                            self.logger.info(f"[OrderBook] {symbol} best_bid={best_bid} best_ask={best_ask}")
                    except Exception as e:
                        if self.debug_trades:
                            self.logger.warning(f"[OrderBook] Erreur parsing {topic}: {e}")
            elif topic.startswith("tickers."):
                # Messages tickers (maj funding_rate, volume24h, bid1/ask1, mark/last, nextFundingTime)
                ticker_data = data.get("data", {})
                if ticker_data:
                    try:
                        # Normaliser quelques champs attendus par le PriceTracker
                        norm = {
                            "symbol": ticker_data.get("symbol") or ticker_data.get("s"),
                            "fundingRate": ticker_data.get("fundingRate"),
                            "volume24h": ticker_data.get("turnover24h") or ticker_data.get("volume24h"),
                            "bid1Price": ticker_data.get("bid1Price") or ticker_data.get("bp"),
                            "ask1Price": ticker_data.get("ask1Price") or ticker_data.get("ap"),
                            "nextFundingTime": ticker_data.get("nextFundingTime") or ticker_data.get("nft"),
                            "markPrice": ticker_data.get("markPrice"),
                            "lastPrice": ticker_data.get("lastPrice") or ticker_data.get("lp"),
                        }
                        # Appeler le callback avec le format compatible
                        self.on_ticker_callback(norm)
                        symbol = norm.get("symbol")
                        if symbol:
                            self._count_ws_tick(symbol)
                    except Exception:
                        # Fallback brut si normalisation échoue
                        self.on_ticker_callback(ticker_data)
                    
        except json.JSONDecodeError as e:
            self.logger.warning(f"{LOG_EMOJIS['warn']} {LOG_MESSAGES['ws_json_error'].format(category=self.category, error=e)}")
        except (KeyError, TypeError, AttributeError) as e:
            self.logger.warning(
                f"⚠️ Erreur parsing données ({self.category}): {type(e).__name__}: {e}"
            )
        except Exception as e:
            self.logger.warning(f"⚠️ Erreur parsing ({self.category}): {e}")

    def _maybe_log_trade_summary(self, symbol: str, price, qty):
        """Log un résumé de trade au plus toutes les trade_summary_interval_s secondes."""
        try:
            now = time.time()
            last_ts = self._last_trade_summary_ts.get(symbol, 0.0)
            # Stocker la dernière valeur vue
            self._last_trade_by_symbol[symbol] = (price, qty, now)
            if now - last_ts >= self.trade_summary_interval_s:
                self._last_trade_summary_ts[symbol] = now
                # Formatage léger -> niveau DEBUG pour ne pas polluer
                self.logger.debug(f"[Trade] Dernier trade {symbol}: {price} (vol={qty})")
        except Exception:
            pass

    def _count_ws_tick(self, symbol: str):
        """Compter les ticks WS Turbo et émettre un résumé périodique si demandé."""
        try:
            now = time.time()
            self._ws_ticks_count[symbol] = self._ws_ticks_count.get(symbol, 0) + 1
            if self.debug_ws_ticks:
                # En mode debug brut, on logge chaque tick ailleurs (déjà géré si activé)
                return
            # Sinon, émettre un résumé périodique
            if now - self._ws_ticks_last_summary_ts >= self.ws_ticks_summary_interval_s:
                self._ws_ticks_last_summary_ts = now
                if self._ws_ticks_count:
                    parts = [f"{sym}={cnt}" for sym, cnt in list(self._ws_ticks_count.items())]
                    try:
                        self.logger.info(f"[Turbo] WS ticks reçus ({self.ws_ticks_summary_interval_s}s): " + ", ".join(parts))
                    except Exception:
                        pass
                    self._ws_ticks_count.clear()
        except Exception:
            pass

    def _inactivity_watchdog(self):
        """Vérifie périodiquement l'absence de messages par topic et log un avertissement."""
        try:
            check_period = 1
            while self.running:
                now = time.time()
                ws_url = self._build_url()
                for topic, last_ts in list(self._last_msg_ts_by_topic.items()):
                    try:
                        if last_ts is None:
                            continue
                        idle = now - last_ts
                        if idle >= self.debug_ws_inactivity_s:
                            last_warn = self._last_warn_ts_by_topic.get(topic, 0.0)
                            if now - last_warn >= self.debug_ws_inactivity_s:
                                try:
                                    self.logger.warning(f"[WS ERROR] Aucun message reçu sur {topic}, endpoint={ws_url}")
                                except Exception:
                                    pass
                                self._last_warn_ts_by_topic[topic] = now
                    except Exception:
                        pass
                for _ in range(check_period):
                    if not self.running:
                        return
                    time.sleep(1)
        except Exception:
            pass

    def _notify_turbo_ws_ready(self, symbol: str):
        """
        Notifie le TurboManager qu'un symbole a reçu ses premières données WebSocket.
        
        Args:
            symbol: Symbole qui a reçu des données WS
        """
        try:
            # Chercher le TurboManager via le callback ticker
            if hasattr(self.on_ticker_callback, '__self__'):
                # Si c'est une méthode d'instance
                instance = self.on_ticker_callback.__self__
                if hasattr(instance, 'turbo_manager') and instance.turbo_manager:
                    instance.turbo_manager.mark_ws_ready(symbol)
                elif hasattr(instance, 'ws_manager') and hasattr(instance.ws_manager, '_ticker_callback'):
                    # Chercher dans le ws_manager
                    callback_instance = instance.ws_manager._ticker_callback.__self__
                    if hasattr(callback_instance, 'turbo_manager') and callback_instance.turbo_manager:
                        callback_instance.turbo_manager.mark_ws_ready(symbol)
        except Exception:
            # Ignorer les erreurs de notification
            pass

    def _notify_turbo_ws_data_received(self, symbol: str):
        """
        Notifie le TurboManager qu'un symbole a reçu ses premières données WebSocket (orderbook ou trade).
        
        Args:
            symbol: Symbole qui a reçu des données WS
        """
        try:
            # Chercher le TurboManager via le callback ticker
            if hasattr(self.on_ticker_callback, '__self__'):
                # Si c'est une méthode d'instance
                instance = self.on_ticker_callback.__self__
                if hasattr(instance, 'turbo_manager') and instance.turbo_manager:
                    instance.turbo_manager.mark_ws_data_received(symbol)
                elif hasattr(instance, 'ws_manager') and hasattr(instance.ws_manager, '_ticker_callback'):
                    # Chercher dans le ws_manager
                    callback_instance = instance.ws_manager._ticker_callback.__self__
                    if hasattr(callback_instance, 'turbo_manager') and callback_instance.turbo_manager:
                        callback_instance.turbo_manager.mark_ws_data_received(symbol)
        except Exception:
            # Ignorer les erreurs de notification
            pass

    def _notify_turbo_ws_tick(self, symbol: str, data: dict):
        """
        Notifie le TurboManager qu'un tick WebSocket a été reçu pour un symbole.
        
        Args:
            symbol: Symbole qui a reçu le tick
            data: Données du tick
        """
        try:
            # Chercher le TurboManager via le callback ticker
            if hasattr(self.on_ticker_callback, '__self__'):
                # Si c'est une méthode d'instance
                instance = self.on_ticker_callback.__self__
                if hasattr(instance, 'turbo_manager') and instance.turbo_manager:
                    instance.turbo_manager.on_ws_tick(symbol, data)
                elif hasattr(instance, 'ws_manager') and hasattr(instance.ws_manager, '_ticker_callback'):
                    # Chercher dans le ws_manager
                    callback_instance = instance.ws_manager._ticker_callback.__self__
                    if hasattr(callback_instance, 'turbo_manager') and callback_instance.turbo_manager:
                        callback_instance.turbo_manager.on_ws_tick(symbol, data)
        except Exception:
            # Ignorer les erreurs de notification
            pass

    def _start_heartbeat(self):
        """Démarre le thread de heartbeat pour afficher les statistiques de messages."""
        if self._heartbeat_running:
            return
        
        self._heartbeat_running = True
        self._heartbeat_start_time = time.time()
        self._message_count = 0
        
        def heartbeat_loop():
            while self._heartbeat_running and self.running:
                try:
                    time.sleep(10)  # Heartbeat toutes les 10 secondes
                    if not self._heartbeat_running or not self.running:
                        break
                    
                    # Calculer les statistiques
                    elapsed = time.time() - self._heartbeat_start_time
                    if elapsed > 0:
                        msg_per_sec = self._message_count / elapsed
                        self.logger.info(f"[WS HEARTBEAT] {self._message_count} msgs reçus sur les {elapsed:.0f} dernières secondes (~{msg_per_sec:.1f} msg/s)")
                    
                    # Reset pour la prochaine période
                    self._message_count = 0
                    self._heartbeat_start_time = time.time()
                    
                except Exception as e:
                    self.logger.debug(f"Erreur heartbeat: {e}")
                    break
        
        self._heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    def _on_error(self, ws, error):
        """Callback interne appelé en cas d'erreur."""
        if self.running:
            self.logger.warning(f"⚠️ WS erreur ({self.category}) : {error}")
            record_ws_error()
            
            # Appeler le callback externe si défini
            if self.on_error_callback:
                try:
                    self.on_error_callback(error)
                except Exception as e:
                    self.logger.warning(f"⚠️ Erreur callback on_error: {e}")

    def _on_close(self, ws, close_status_code, close_msg):
        """Callback interne appelé à la fermeture."""
        if self.running:
            self.logger.info(
                f"🔌 WS fermée ({self.category}) (code={close_status_code}, reason={close_msg})"
            )
            
            # Appeler le callback externe si défini
            if self.on_close_callback:
                try:
                    self.on_close_callback(close_status_code, close_msg)
                except Exception as e:
                    self.logger.warning(f"⚠️ Erreur callback on_close: {e}")

    def run(self):
        """
        Boucle principale avec reconnexion automatique et backoff progressif.
        
        Cette méthode bloque jusqu'à ce que close() soit appelé.
        """
        self.running = True
        
        while self.running:
            try:
                try:
                    self.logger.info(f"🔐 Connexion à la WebSocket publique ({self.category})…")
                except Exception:
                    pass
                
                url = self._build_url()
                self.ws = websocket.WebSocketApp(
                    url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close
                )
                
                self.ws.run_forever(ping_interval=20, ping_timeout=10)
                
            except (ConnectionError, OSError, TimeoutError) as e:
                if self.running:
                    try:
                        self.logger.error(
                            f"Erreur connexion réseau WS publique ({self.category}): "
                            f"{type(e).__name__}: {e}"
                        )
                    except Exception:
                        pass
            except Exception as e:
                if self.running:
                    try:
                        self.logger.error(f"Erreur connexion WS publique ({self.category}): {e}")
                    except Exception:
                        pass
            
            # Reconnexion avec backoff progressif
            if self.running:
                delay = self.reconnect_delays[
                    min(self.current_delay_index, len(self.reconnect_delays) - 1)
                ]
                try:
                    self.logger.warning(
                        f"🔁 WS publique ({self.category}) déconnectée → reconnexion dans {delay}s"
                    )
                    record_ws_connection(connected=False)  # Enregistrer la reconnexion
                except Exception:
                    pass
                
                # Attendre le délai avec vérification périodique de l'arrêt
                for _ in range(delay):
                    if not self.running:
                        break
                    time.sleep(1)
                
                # Augmenter l'index de délai pour le prochain backoff (jusqu'à la limite)
                if self.current_delay_index < len(self.reconnect_delays) - 1:
                    self.current_delay_index += 1
            else:
                break

    def close(self):
        """Ferme proprement la connexion WebSocket."""
        self.running = False
        self._heartbeat_running = False
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass

    def set_callbacks(
        self, 
        on_open: Optional[Callable] = None,
        on_close: Optional[Callable] = None,
        on_error: Optional[Callable] = None
    ):
        """
        Définit des callbacks optionnels pour les événements de connexion.
        
        Args:
            on_open (Callable, optional): Appelé à l'ouverture de la connexion
            on_close (Callable, optional): Appelé à la fermeture (code, reason)
            on_error (Callable, optional): Appelé en cas d'erreur (error)
        """
        self.on_open_callback = on_open
        self.on_close_callback = on_close
        self.on_error_callback = on_error


class SimplePublicWSClient:
    """
    Version simplifiée du client WebSocket publique pour les tests et usages basiques.
    
    NOTE: SimplePublicWSClient n'est PAS utilisée dans le bot principal (bot.py).
    Cette classe est utilisée uniquement dans app.py pour la supervision/debug.
    Ne gère que la connexion basique sans souscription automatique aux symboles.
    """
    
    def __init__(self, testnet: bool, logger):
        """
        Initialise le client WebSocket publique simple.
        
        Args:
            testnet (bool): Utiliser le testnet (True) ou le mainnet (False)
            logger: Instance du logger pour les messages
        """
        self.testnet = testnet
        self.logger = logger
        self.ws: Optional[websocket.WebSocketApp] = None
        self.running = False
        self.connected = False
        
        # Callbacks optionnels
        self.on_open_callback: Optional[Callable] = None
        self.on_close_callback: Optional[Callable] = None
        self.on_error_callback: Optional[Callable] = None
        self.on_message_callback: Optional[Callable] = None

    def _build_url(self, category: str = "linear") -> str:
        """Construit l'URL WebSocket selon la catégorie."""
        if category == "linear":
            return (
                "wss://stream-testnet.bybit.com/v5/public/linear" if self.testnet 
                else "wss://stream.bybit.com/v5/public/linear"
            )
        else:
            return (
                "wss://stream-testnet.bybit.com/v5/public/inverse" if self.testnet 
                else "wss://stream.bybit.com/v5/public/inverse"
            )

    def _on_open(self, ws):
        """Callback interne appelé à l'ouverture."""
        self.logger.info("🌐 WS publique ouverte")
        self.connected = True
        
        if self.on_open_callback:
            try:
                self.on_open_callback()
            except Exception as e:
                self.logger.warning(f"{LOG_EMOJIS['warn']} {LOG_MESSAGES['ws_callback_error'].format(error=e)} {e}")

    def _on_message(self, ws, message):
        """Callback interne appelé à chaque message."""
        if self.on_message_callback:
            try:
                self.on_message_callback(message)
            except Exception as e:
                self.logger.warning(f"⚠️ Erreur callback on_message: {e}")

    def _on_error(self, ws, error):
        """Callback interne appelé en cas d'erreur."""
        self.logger.warning(f"⚠️ WS publique erreur : {error}")
        self.connected = False
        
        if self.on_error_callback:
            try:
                self.on_error_callback(error)
            except Exception as e:
                self.logger.warning(f"⚠️ Erreur callback on_error: {e}")

    def _on_close(self, ws, close_status_code, close_msg):
        """Callback interne appelé à la fermeture."""
        self.logger.info(f"🔌 WS publique fermée (code={close_status_code}, reason={close_msg})")
        self.connected = False
        
        if self.on_close_callback:
            try:
                self.on_close_callback(close_status_code, close_msg)
            except Exception as e:
                self.logger.warning(f"⚠️ Erreur callback on_close: {e}")

    def connect(self, category: str = "linear"):
        """
        Établit la connexion WebSocket avec reconnexion automatique.
        
        Args:
            category (str): Catégorie ("linear" ou "inverse")
        """
        if self.running:
            self.logger.warning("⚠️ Connexion déjà en cours")
            return
            
        self.running = True
        reconnect_delays = [1, 2, 5, 10]  # secondes
        delay_index = 0
        
        while self.running:
            try:
                url = self._build_url(category)
                self.ws = websocket.WebSocketApp(
                    url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close
                )
                
                self.ws.run_forever(ping_interval=20, ping_timeout=10)
                
            except Exception as e:
                if self.running:
                    self.logger.error(f"Erreur WS publique: {e}")
            
            # Reconnexion avec backoff
            if self.running:
                delay = reconnect_delays[min(delay_index, len(reconnect_delays) - 1)]
                self.logger.warning(f"🔁 WS publique déconnectée → reconnexion dans {delay}s")
                
                for _ in range(delay):
                    if not self.running:
                        break
                    time.sleep(1)
                
                if delay_index < len(reconnect_delays) - 1:
                    delay_index += 1
            else:
                break

    def close(self):
        """Ferme proprement la connexion."""
        self.running = False
        self.connected = False
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass

    def set_callbacks(
        self, 
        on_open: Optional[Callable] = None,
        on_message: Optional[Callable] = None,
        on_close: Optional[Callable] = None,
        on_error: Optional[Callable] = None
    ):
        """
        Définit les callbacks pour les événements WebSocket.
        
        Args:
            on_open (Callable, optional): Appelé à l'ouverture
            on_message (Callable, optional): Appelé pour chaque message (raw message)
            on_close (Callable, optional): Appelé à la fermeture (code, reason)
            on_error (Callable, optional): Appelé en cas d'erreur (error)
        """
        self.on_open_callback = on_open
        self.on_message_callback = on_message
        self.on_close_callback = on_close
        self.on_error_callback = on_error
