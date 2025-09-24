"""
Module pour filtrer les contrats perpétuels et construire des watchlists.

NOTE: FilterCriteria et build_watchlist ne sont PAS utilisés dans le code de production.
Ce module contient du code vestigial/expérimental conservé pour les tests futurs.
Le code de production utilise maintenant WatchlistManager dans watchlist_manager.py.
"""

import re
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class FilterCriteria:
    """Critères de filtrage pour les contrats perpétuels."""
    category: str = "both"  # "linear" | "inverse" | "both"
    include: List[str] | None = None  # symboles exacts à forcer
    exclude: List[str] | None = None  # symboles à exclure
    regex: str | None = None  # motif regex pour filtrer
    limit: int | None = None  # limite d'éléments à afficher


def build_watchlist(perp: Dict, criteria: FilterCriteria) -> List[str]:
    """
    Construit une watchlist filtrée à partir des contrats perpétuels.
    
    Args:
        perp (Dict): Dictionnaire avec "linear", "inverse", "total" de get_perp_symbols()
        criteria (FilterCriteria): Critères de filtrage
        
    Returns:
        List[str]: Liste des symboles filtrés et triés
    """
    # Sélectionner le pool selon la catégorie
    if criteria.category == "linear":
        pool = perp["linear"]
    elif criteria.category == "inverse":
        pool = perp["inverse"]
    else:  # "both"
        # Concaténer sans doublons
        pool = list(set(perp["linear"] + perp["inverse"]))
    
    # Appliquer les filtres dans l'ordre
    
    # 1) Filtre include : ne garder que ceux présents dans include
    if criteria.include:
        pool = [symbol for symbol in pool if symbol in criteria.include]
    
    # 2) Filtre regex : filtrer par motif (insensible à la casse)
    if criteria.regex:
        try:
            pattern = re.compile(criteria.regex, re.IGNORECASE)
            pool = [symbol for symbol in pool if pattern.match(symbol)]
        except re.error:
            # Si regex invalide, ignorer le filtre
            pass
    
    # 3) Filtre exclude : retirer ces symboles
    if criteria.exclude:
        pool = [symbol for symbol in pool if symbol not in criteria.exclude]
    
    # Trier alphabétiquement (stable)
    pool.sort()
    
    # 4) Limiter le nombre d'éléments
    if criteria.limit:
        pool = pool[:criteria.limit]
    
    return pool
