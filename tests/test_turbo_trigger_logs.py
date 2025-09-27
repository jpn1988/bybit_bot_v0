#!/usr/bin/env python3
"""Tests simples des logs et conditions de déclenchement du Mode Turbo."""

import logging
from logging_setup import setup_logging
from watchlist_manager import WatchlistManager
from turbo import TurboManager


def run_checks(trigger_seconds: int):
    logger = setup_logging()
    wm = WatchlistManager(testnet=True, logger=logger)
    config = wm.load_and_validate_config()
    config.setdefault('turbo', {})
    config['turbo']['trigger_seconds'] = trigger_seconds
    # Désactiver le tick logging pour alléger la sortie de test
    config['turbo']['tick_logging'] = False

    tm = TurboManager(
        config=config,
        data_fetcher=None,  # Pas de WS dans ce test
        order_client=None,
        filters=wm,
        scorer=None,
        volatility_tracker=None,
        logger=logger,
    )

    # Cas 1: funding_time_remaining ~ 8500s (2h 21m 40s)
    print(f"\n=== Test trigger_seconds={trigger_seconds} avec funding_time_remaining≈8500s ===")
    tm.check_candidates([
        ("TEST_8500S", 0.001, 10_000_000, "2h 21m 40s", 0.0, 0.0, 0.0)
    ])

    # Cas 2: funding_time_remaining = 65s (1m 5s)
    print(f"\n=== Test trigger_seconds={trigger_seconds} avec funding_time_remaining=65s ===")
    tm.check_candidates([
        ("TEST_65S", 0.001, 10_000_000, "1m 5s", 0.0, 0.0, 0.0)
    ])


if __name__ == "__main__":
    # Vérifications attendues:
    # - Avec trigger_seconds=70: TEST_8500S -> condition_met=False; TEST_65S -> condition_met=True
    # - Avec trigger_seconds=5000: TEST_8500S -> condition_met=False; TEST_65S -> condition_met=True
    run_checks(70)
    run_checks(5000)


