#!/usr/bin/env python3
"""WebSocket publique Bybit v5 - Client réutilisable avec reconnexion automatique."""

import json
import time
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
        on_ticker_callback: Callable[[dict], None]
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
        self.logger.info(f"{LOG_EMOJIS['websocket']} {LOG_MESSAGES['ws_opened'].format(category=self.category)}")
        
        # Enregistrer la connexion WebSocket
        record_ws_connection(connected=True)
        
        # Réinitialiser l'index de délai de reconnexion après une connexion réussie
        self.current_delay_index = 0
        
        # S'abonner aux tickers pour tous les symboles
        if self.symbols:
            subscribe_message = {
                "op": "subscribe",
                "args": [f"tickers.{symbol}" for symbol in self.symbols]
            }
            try:
                ws.send(json.dumps(subscribe_message))
                self.logger.info(
                    f"{LOG_EMOJIS['watchlist']} {LOG_MESSAGES['ws_subscription'].format(count=len(self.symbols), category=self.category)}"
                )
            except (json.JSONEncodeError, ConnectionError, OSError) as e:
                self.logger.error(
                    f"Erreur souscription WebSocket {self.category}: {type(e).__name__}: {e}"
                )
            except Exception as e:
                self.logger.warning(f"{LOG_EMOJIS['warn']} {LOG_MESSAGES['ws_subscription_error'].format(category=self.category, error=e)}")
        else:
            self.logger.warning(f"{LOG_EMOJIS['warn']} {LOG_MESSAGES['ws_no_symbols'].format(category=self.category)}")
        
        # Appeler le callback externe si défini
        if self.on_open_callback:
            try:
                self.on_open_callback()
            except Exception as e:
                self.logger.warning(f"{LOG_EMOJIS['warn']} {LOG_MESSAGES['ws_callback_error'].format(error=e)} {e}")

    def _on_message(self, ws, message):
        """Callback interne appelé à chaque message reçu."""
        try:
            data = json.loads(message)
            if data.get("topic", "").startswith("tickers."):
                ticker_data = data.get("data", {})
                if ticker_data:
                    self.on_ticker_callback(ticker_data)
        except json.JSONDecodeError as e:
            self.logger.warning(f"{LOG_EMOJIS['warn']} {LOG_MESSAGES['ws_json_error'].format(category=self.category, error=e)}")
        except (KeyError, TypeError, AttributeError) as e:
            self.logger.warning(
                f"⚠️ Erreur parsing données ({self.category}): {type(e).__name__}: {e}"
            )
        except Exception as e:
            self.logger.warning(f"⚠️ Erreur parsing ({self.category}): {e}")

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
