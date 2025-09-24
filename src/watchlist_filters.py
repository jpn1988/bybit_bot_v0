#!/usr/bin/env python3
"""
Module de filtrage et scoring pour la watchlist.

Ce module contient uniquement les fonctions pures de filtrage et scoring :
- Filtres sur funding, volume, spread, volatilité
- Calculs temporels (temps avant funding)
- Fonctions de scoring et tri
- Aucun accès réseau ou I/O
"""

import datetime
from typing import List, Tuple, Dict, Optional


class WatchlistFilters:
    """
    Classe dédiée aux filtres et calculs pour la watchlist.
    
    Responsabilités :
    - Filtrage par funding, volume, spread, volatilité
    - Calculs temporels (temps avant funding)
    - Tri et scoring des symboles
    - Fonctions pures sans effets de bord
    """
    
    def __init__(self, logger=None):
        """
        Initialise les filtres.
        
        Args:
            logger: Logger pour les messages (optionnel)
        """
        self.logger = logger
    
    def calculate_funding_time_remaining(self, next_funding_time) -> str:
        """
        Retourne "Xh Ym Zs" à partir d'un timestamp Bybit (ms) ou ISO.
        Si l'échéance est passée, calcule automatiquement le prochain funding (8h plus tard).
        
        Args:
            next_funding_time: Timestamp du prochain funding
            
        Returns:
            String formatée du temps restant ou "-" si erreur
        """
        if not next_funding_time:
            return "-"
        try:
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
            
            # Si l'échéance est passée, calculer le prochain funding (8h plus tard)
            if delta <= 0:
                # Calculer le prochain funding en ajoutant 8h
                next_funding_dt = funding_dt + datetime.timedelta(hours=8)
                delta = (next_funding_dt - now).total_seconds()
                
                # Si même le prochain est passé, continuer à ajouter 8h jusqu'à trouver le bon
                while delta <= 0:
                    next_funding_dt += datetime.timedelta(hours=8)
                    delta = (next_funding_dt - now).total_seconds()
            
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
            if self.logger:
                self.logger.error(f"Erreur calcul temps funding formaté: {type(e).__name__}: {e}")
            return "-"
    
    def calculate_funding_minutes_remaining(self, next_funding_time) -> Optional[float]:
        """
        Retourne les minutes restantes avant le prochain funding (pour filtrage).
        Si l'échéance est passée, calcule automatiquement le prochain funding (8h plus tard).
        
        Args:
            next_funding_time: Timestamp du prochain funding
            
        Returns:
            Minutes restantes ou None si erreur
        """
        if not next_funding_time:
            return None
        try:
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
            
            # Si l'échéance est passée, calculer le prochain funding (8h plus tard)
            if delta_sec <= 0:
                # Calculer le prochain funding en ajoutant 8h
                next_funding_dt = funding_dt + datetime.timedelta(hours=8)
                delta_sec = (next_funding_dt - now).total_seconds()
                
                # Si même le prochain est passé, continuer à ajouter 8h jusqu'à trouver le bon
                while delta_sec <= 0:
                    next_funding_dt += datetime.timedelta(hours=8)
                    delta_sec = (next_funding_dt - now).total_seconds()
            
            return delta_sec / 60.0  # Convertir en minutes
        except Exception as e:
            if self.logger:
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
    
    def apply_volatility_filter(
        self,
        symbols_data: List[Tuple],
        volatility_tracker,
        volatility_min: Optional[float],
        volatility_max: Optional[float]
    ) -> List[Tuple]:
        """
        Applique le filtre de volatilité aux symboles.
        
        Args:
            symbols_data: Liste des symboles avec leurs données
            volatility_tracker: Instance du tracker de volatilité
            volatility_min: Volatilité minimum
            volatility_max: Volatilité maximum
            
        Returns:
            Liste des symboles filtrés par volatilité
        """
        if not symbols_data:
            return symbols_data
        
        try:
            return volatility_tracker.filter_by_volatility(
                symbols_data,
                volatility_min,
                volatility_max
            )
        except Exception as e:
            if self.logger:
                self.logger.warning(f"⚠️ Erreur lors du calcul de la volatilité : {e}")
            return symbols_data
    
    def separate_symbols_by_category(
        self,
        symbols_data: List[Tuple],
        symbol_categories: Dict
    ) -> Tuple[List[str], List[str]]:
        """
        Sépare les symboles par catégorie (linear/inverse).
        
        Args:
            symbols_data: Liste des symboles avec leurs données
            symbol_categories: Dictionnaire des catégories de symboles
            
        Returns:
            Tuple (linear_symbols, inverse_symbols)
        """
        from instruments import category_of_symbol
        
        linear_symbols = []
        inverse_symbols = []
        
        for symbol_data in symbols_data:
            symbol = symbol_data[0]  # Premier élément est toujours le symbole
            category = category_of_symbol(symbol, symbol_categories)
            
            if category == "linear":
                linear_symbols.append(symbol)
            elif category == "inverse":
                inverse_symbols.append(symbol)
        
        return linear_symbols, inverse_symbols
    
    def build_funding_data_dict(
        self,
        symbols_data: List[Tuple]
    ) -> Dict[str, Tuple]:
        """
        Construit le dictionnaire de données de funding à partir des symboles filtrés.
        
        Args:
            symbols_data: Liste des symboles avec leurs données
            
        Returns:
            Dictionnaire {symbol: (funding, volume, funding_time_remaining, spread_pct, volatility_pct)}
        """
        funding_data = {}
        
        for symbol_data in symbols_data:
            symbol = symbol_data[0]
            
            if len(symbol_data) == 6:
                # Format: (symbol, funding, volume, funding_time_remaining, spread_pct, volatility_pct)
                _, funding, volume, funding_time_remaining, spread_pct, volatility_pct = symbol_data
                funding_data[symbol] = (funding, volume, funding_time_remaining, spread_pct, volatility_pct)
            elif len(symbol_data) == 5:
                # Format: (symbol, funding, volume, funding_time_remaining, spread_pct)
                _, funding, volume, funding_time_remaining, spread_pct = symbol_data
                funding_data[symbol] = (funding, volume, funding_time_remaining, spread_pct, None)
            elif len(symbol_data) == 4:
                # Format: (symbol, funding, volume, funding_time_remaining)
                _, funding, volume, funding_time_remaining = symbol_data
                funding_data[symbol] = (funding, volume, funding_time_remaining, 0.0, None)
            else:
                # Format: (symbol, funding, volume)
                _, funding, volume = symbol_data
                funding_data[symbol] = (funding, volume, "-", 0.0, None)
        
        return funding_data
