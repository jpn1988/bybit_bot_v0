"""Module pour stocker et gérer les prix en temps réel."""

import time
import threading
from typing import Dict, Tuple, Optional


# Stockage global des prix (protégé par verrou)
_price_data: Dict[str, Dict[str, float]] = {}
_price_lock = threading.Lock()


def update(symbol: str, mark_price: float, last_price: float, timestamp: float) -> None:
    """
    Met à jour les prix pour un symbole donné.
    
    Args:
        symbol (str): Symbole du contrat (ex: BTCUSDT)
        mark_price (float): Prix de marque
        last_price (float): Dernier prix de transaction
        timestamp (float): Timestamp de la mise à jour
    """
    with _price_lock:
        _price_data[symbol] = {
            "mark_price": mark_price,
            "last_price": last_price,
            "timestamp": timestamp
        }


def get_snapshot() -> Dict[str, Dict[str, float]]:
    """
    Récupère un instantané de tous les prix stockés.
    
    Returns:
        Dict[str, Dict[str, float]]: Dictionnaire des prix par symbole
    """
    with _price_lock:
        return _price_data.copy()


def purge_expired(ttl_seconds: int = 120) -> int:
    """Supprime les entrées plus anciennes que ttl_seconds. Retourne le nombre purgé."""
    now = time.time()
    removed = 0
    with _price_lock:
        to_delete = [s for s, d in _price_data.items() if (now - d.get("timestamp", 0)) > ttl_seconds]
        for s in to_delete:
            _price_data.pop(s, None)
            removed += 1
    return removed


def get_last_update(symbol: str) -> Optional[float]:
    """Retourne le timestamp de dernière mise à jour pour un symbole, ou None s'il n'existe pas."""
    with _price_lock:
        data = _price_data.get(symbol)
        if not data:
            return None
        return data.get("timestamp")


def has_symbol(symbol: str) -> bool:
    """Indique si un symbole est présent dans le store (au moins une mise à jour reçue)."""
    with _price_lock:
        return symbol in _price_data
