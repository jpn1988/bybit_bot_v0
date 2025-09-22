#!/usr/bin/env python3
"""WebSocket privée Bybit v5 PRO - Runner persistant avec authentification et reconnexion."""

import os
import signal
from config import get_settings
from logging_setup import setup_logging
from ws_private import PrivateWSClient, create_private_ws_client


class PrivateWSRunner:
    """Runner WebSocket privée Bybit v5, basé sur PrivateWSClient (réutilisable)."""

    def __init__(self):
        self.logger = setup_logging()
        # Configuration du signal handler pour Ctrl+C
        signal.signal(signal.SIGINT, self._signal_handler)

        # Utiliser la fonction utilitaire centralisée
        try:
            self.client = create_private_ws_client(self.logger)
            # Récupérer les paramètres pour les logs
            self.testnet = self.client.testnet
            self.channels = self.client.channels
        except RuntimeError as e:
            self.logger.error(f"⛔ {e}")
            exit(1)

    def _signal_handler(self, signum, frame):
        """Gestionnaire de signal pour Ctrl+C."""
        self.logger.info("🧹 Arrêt demandé par l'utilisateur (Ctrl+C)")
        self.client.close()
        exit(0)

    def run(self):
        self.logger.info("🚀 Démarrage WebSocket privée (runner)")
        self.logger.info(f"📂 Configuration chargée (testnet={self.testnet}, channels={self.channels})")
        self.logger.info(f"🔑 Clé API: {'présente' if self.client.api_key else 'absente'}")
        self.client.run()


def main():
    """Fonction principale."""
    runner = PrivateWSRunner()
    runner.run()


if __name__ == "__main__":
    main()
