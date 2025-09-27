#!/usr/bin/env python3
"""
Gestionnaire WebSocket dédié pour les connexions publiques Bybit.

Cette classe gère uniquement :
- La connexion WS publique
- La souscription aux symboles  
- La réception et mise à jour des prix en temps réel
"""

import threading
import time
from typing import List, Callable, Optional
from bybit_client import BybitPublicClient
from instruments import category_of_symbol
from http_client_manager import get_http_client
from logging_setup import setup_logging
from ws_public import PublicWSClient
from price_store import update


class WebSocketManager:
    """
    Gestionnaire WebSocket pour les connexions publiques Bybit.
    
    Responsabilités :
    - Gestion des connexions WebSocket publiques (linear/inverse)
    - Souscription aux symboles pour les tickers
    - Réception et traitement des données de prix en temps réel
    - Callbacks vers l'application principale
    """
    
    def __init__(self, testnet: bool = True, logger=None, *, debug_ws: bool = False, debug_ws_inactivity_s: int = 10):
        """
        Initialise le gestionnaire WebSocket.
        
        Args:
            testnet (bool): Utiliser le testnet (True) ou le marché réel (False)
            logger: Logger pour les messages (optionnel)
        """
        self.testnet = testnet
        self.logger = logger or setup_logging()
        self.running = False
        self.debug_ws = bool(debug_ws)
        self.debug_ws_inactivity_s = int(debug_ws_inactivity_s) if debug_ws_inactivity_s is not None else 10
        
        # Connexions WebSocket
        self._ws_conns: List[PublicWSClient] = []
        self._ws_threads: List[threading.Thread] = []
        
        # Callbacks
        self._ticker_callback: Optional[Callable] = None
        
        # Symboles par catégorie
        self.linear_symbols: List[str] = []
        self.inverse_symbols: List[str] = []
    
    def set_ticker_callback(self, callback: Callable[[dict], None]):
        """
        Définit le callback à appeler lors de la réception de données ticker.
        
        Args:
            callback: Fonction à appeler avec les données ticker reçues
        """
        self._ticker_callback = callback
    
    def start_connections(self, linear_symbols: List[str], inverse_symbols: List[str]):
        """
        Démarre les connexions WebSocket pour les symboles donnés.
        
        Args:
            linear_symbols: Liste des symboles linear à suivre
            inverse_symbols: Liste des symboles inverse à suivre
        """
        if self.running:
            self.logger.warning("⚠️ WebSocketManager déjà en cours d'exécution")
            return
        
        # Valider les symboles via REST (instruments-info) avant souscription
        self.linear_symbols = self._validate_symbols(linear_symbols or [], "linear")
        self.inverse_symbols = self._validate_symbols(inverse_symbols or [], "inverse")
        self.running = True
        
        # Déterminer le type de connexions nécessaires
        if self.linear_symbols and self.inverse_symbols:
            self.logger.info("🔄 Démarrage des connexions WebSocket pour linear et inverse")
            self._start_dual_connections()
        elif self.linear_symbols:
            self.logger.info("🔄 Démarrage de la connexion WebSocket linear")
            self._start_single_connection("linear", self.linear_symbols)
        elif self.inverse_symbols:
            self.logger.info("🔄 Démarrage de la connexion WebSocket inverse")
            self._start_single_connection("inverse", self.inverse_symbols)
        else:
            self.logger.warning("⚠️ Aucun symbole fourni pour les connexions WebSocket")

    def _validate_symbols(self, symbols: List[str], category: str) -> List[str]:
        """Valide l'existence des symboles via l'API `instruments-info`. Retourne uniquement ceux trouvés."""
        if not symbols:
            return []
        try:
            public_client = BybitPublicClient(testnet=self.testnet, timeout=10)
            base_url = public_client.public_base_url()
            url = f"{base_url}/v5/market/instruments-info"
            client = get_http_client(timeout=10)
            valid: List[str] = []
            for sym in symbols:
                # Déterminer la catégorie attendue pour le symbole si besoin
                wanted_category = category
                try:
                    wanted_category = category_of_symbol(sym, {sym: category})
                except Exception:
                    pass
                resp = client.get(url, params={"category": wanted_category, "symbol": sym})
                try:
                    if resp.status_code >= 400:
                        self.logger.warning(f"[WS ERROR] HTTP {resp.status_code} instruments-info pour {sym}")
                        continue
                    data = resp.json()
                    if data.get("retCode") != 0:
                        ret_msg = data.get("retMsg") or data.get("ret_msg") or ""
                        self.logger.warning(f"[WS ERROR] API instruments-info retCode={data.get('retCode')} msg=\"{ret_msg}\" pour {sym}")
                        continue
                    result = (data.get("result") or {}).get("list") or []
                    if result:
                        valid.append(sym)
                    else:
                        self.logger.error(f"[WS ERROR] Symbole {sym} introuvable sur Bybit")
                except Exception as e:
                    self.logger.warning(f"[WS ERROR] Validation symbole {sym} échouée → {e}")
            return valid
        except Exception as e:
            self.logger.warning(f"[WS ERROR] Validation REST des symboles échouée → {e}")
            # En cas d'erreur globale, retourner la liste originale pour ne pas bloquer
            return symbols
    
    def _handle_ticker(self, ticker_data: dict):
        """
        Gestionnaire interne pour les données ticker reçues.
        Met à jour le store de prix et appelle le callback externe.
        
        Args:
            ticker_data: Données ticker reçues via WebSocket
        """
        try:
            # Mettre à jour le store de prix global
            symbol = ticker_data.get("symbol", "")
            mark_price = ticker_data.get("markPrice")
            last_price = ticker_data.get("lastPrice")
            
            if symbol and mark_price is not None and last_price is not None:
                mark_val = float(mark_price)
                last_val = float(last_price)
                update(symbol, mark_val, last_val, time.time())
            
            # Appeler le callback externe si défini
            if self._ticker_callback and symbol:
                self._ticker_callback(ticker_data)
                
        except Exception as e:
            self.logger.warning(f"⚠️ Erreur traitement ticker WebSocket: {e}")
    
    def _start_single_connection(self, category: str, symbols: List[str]):
        """
        Démarre une connexion WebSocket pour une seule catégorie.
        
        Args:
            category: Catégorie ("linear" ou "inverse")
            symbols: Liste des symboles à suivre
        """
        conn = PublicWSClient(
            category=category,
            symbols=symbols,
            testnet=self.testnet,
            logger=self.logger,
            on_ticker_callback=self._handle_ticker,
            debug_ws=self.debug_ws,
            debug_ws_inactivity_s=self.debug_ws_inactivity_s,
        )
        self._ws_conns = [conn]
        
        # Lancer la connexion (bloquant)
        conn.run()
    
    def _start_dual_connections(self):
        """
        Démarre deux connexions WebSocket isolées (linear et inverse).
        """
        # Créer les connexions isolées
        linear_conn = PublicWSClient(
            category="linear",
            symbols=self.linear_symbols,
            testnet=self.testnet,
            logger=self.logger,
            on_ticker_callback=self._handle_ticker,
            debug_ws=self.debug_ws,
            debug_ws_inactivity_s=self.debug_ws_inactivity_s,
        )
        inverse_conn = PublicWSClient(
            category="inverse",
            symbols=self.inverse_symbols,
            testnet=self.testnet,
            logger=self.logger,
            on_ticker_callback=self._handle_ticker,
            debug_ws=self.debug_ws,
            debug_ws_inactivity_s=self.debug_ws_inactivity_s,
        )
        
        self._ws_conns = [linear_conn, inverse_conn]
        
        # Lancer en parallèle dans des threads séparés
        linear_thread = threading.Thread(target=linear_conn.run)
        inverse_thread = threading.Thread(target=inverse_conn.run)
        linear_thread.daemon = True
        inverse_thread.daemon = True
        
        self._ws_threads = [linear_thread, inverse_thread]
        linear_thread.start()
        inverse_thread.start()
        
        # Bloquer le thread principal sur les deux connexions
        linear_thread.join()
        inverse_thread.join()
    
    def stop(self):
        """
        Arrête toutes les connexions WebSocket.
        """
        self.logger.info("🧹 Arrêt des connexions WebSocket...")
        self.running = False
        
        # Fermer toutes les connexions
        for conn in self._ws_conns:
            try:
                conn.close()
            except Exception as e:
                self.logger.warning(f"⚠️ Erreur fermeture connexion WebSocket: {e}")
        
        # Attendre la fin des threads
        for thread in self._ws_threads:
            if thread.is_alive():
                try:
                    thread.join(timeout=5)
                except Exception as e:
                    self.logger.warning(f"⚠️ Erreur attente thread WebSocket: {e}")
        
        # Nettoyer les listes
        self._ws_conns.clear()
        self._ws_threads.clear()
    
    def is_running(self) -> bool:
        """
        Vérifie si le gestionnaire WebSocket est en cours d'exécution.
        
        Returns:
            bool: True si en cours d'exécution
        """
        return self.running
    
    def get_connected_symbols(self) -> dict:
        """
        Retourne les symboles actuellement connectés par catégorie.
        
        Returns:
            dict: {"linear": [...], "inverse": [...]}
        """
        return {
            "linear": self.linear_symbols.copy(),
            "inverse": self.inverse_symbols.copy()
        }
    
    def subscribe_turbo_symbol(self, symbol: str):
        """
        Souscrit dynamiquement aux topics pour un symbole en mode turbo.
        
        Args:
            symbol: Symbole à ajouter aux souscriptions
        """
        if not self.running or not self._ws_conns:
            self.logger.warning(f"[WS TURBO] Impossible de souscrire à {symbol} - WebSocket non connecté")
            return False
        
        try:
            # Déterminer la catégorie du symbole
            category = "linear"  # Par défaut
            if symbol in self.inverse_symbols:
                category = "inverse"
            elif symbol in self.linear_symbols:
                category = "linear"
            
            # Trouver la connexion appropriée
            target_conn = None
            for conn in self._ws_conns:
                if conn.category == category:
                    target_conn = conn
                    break
            
            if not target_conn:
                self.logger.warning(f"[WS TURBO] Aucune connexion trouvée pour {symbol} (catégorie: {category})")
                return False
            
            # Topics à souscrire pour le turbo
            turbo_topics = [
                f"instrument_info.{symbol}",
                f"publicTrade.{symbol}",
                f"orderbook.1.{symbol}"
            ]
            
            # Envoyer la souscription
            subscribe_message = {
                "op": "subscribe",
                "args": turbo_topics
            }
            
            import json
            import websocket
            
            if hasattr(target_conn, 'ws') and target_conn.ws:
                target_conn.ws.send(json.dumps(subscribe_message))
                
                # Logger les souscriptions
                for topic in turbo_topics:
                    self.logger.info(f"[WS SUBSCRIBE] {topic}")
                
                self.logger.info(f"🚀 [Turbo WS] Souscription activée pour {symbol}")
                return True
            else:
                self.logger.warning(f"[WS TURBO] WebSocket non disponible pour {symbol}")
                return False
                
        except Exception as e:
            self.logger.error(f"[WS TURBO] Erreur souscription {symbol}: {e}")
            return False
