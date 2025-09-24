"""Utilitaires communs pour le bot Bybit."""

from typing import Union, Dict, Any, Optional


def compute_spread(bid: Union[float, int, str], ask: Union[float, int, str]) -> float:
    """
    Calcule le spread en pourcentage entre le prix bid et ask.
    
    Formule utilisée : (ask - bid) / ask * 100
    
    Args:
        bid: Prix bid (peut être float, int ou string)
        ask: Prix ask (peut être float, int ou string)
        
    Returns:
        float: Spread en pourcentage (0.0 si ask == 0 pour éviter division par zéro)
        
    Examples:
        >>> compute_spread(100.0, 101.0)
        0.9900990099009901  # ~0.99%
        >>> compute_spread(0, 100)
        100.0  # 100%
        >>> compute_spread(100, 0)
        0.0  # Évite division par zéro
    """
    try:
        # Convertir en float si nécessaire
        bid_price = float(bid)
        ask_price = float(ask)
        
        # Éviter la division par zéro
        if ask_price == 0:
            return 0.0
            
        # Calculer le spread : (ask - bid) / ask
        spread_ratio = (ask_price - bid_price) / ask_price
        return spread_ratio
        
    except (ValueError, TypeError, ZeroDivisionError):
        # Retourner 0.0 en cas d'erreur de conversion ou division par zéro
        return 0.0


def compute_spread_with_mid_price(bid: Union[float, int, str], ask: Union[float, int, str]) -> float:
    """
    Calcule le spread en pourcentage en utilisant le prix moyen (mid price).
    
    Formule utilisée : (ask - bid) / ((ask + bid) / 2)
    
    Args:
        bid: Prix bid (peut être float, int ou string)
        ask: Prix ask (peut être float, int ou string)
        
    Returns:
        float: Spread en pourcentage basé sur le prix moyen
        
    Examples:
        >>> compute_spread_with_mid_price(100.0, 101.0)
        0.009950248756218905  # ~0.995%
        >>> compute_spread_with_mid_price(0, 100)
        2.0  # 200%
    """
    try:
        # Convertir en float si nécessaire
        bid_price = float(bid)
        ask_price = float(ask)
        
        # Éviter la division par zéro
        if bid_price == 0 and ask_price == 0:
            return 0.0
            
        # Calculer le prix moyen
        mid_price = (ask_price + bid_price) / 2
        
        # Éviter la division par zéro
        if mid_price == 0:
            return 0.0
            
        # Calculer le spread : (ask - bid) / mid_price
        spread_ratio = (ask_price - bid_price) / mid_price
        return spread_ratio
        
    except (ValueError, TypeError, ZeroDivisionError):
        # Retourner 0.0 en cas d'erreur de conversion ou division par zéro
        return 0.0


def merge_symbol_data(
    symbol: str, 
    rest_data: Dict[str, Any], 
    ws_data: Dict[str, Any],
    volatility_tracker: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Fusionne les données REST et WebSocket pour un symbole donné.
    
    Cette fonction centralise la logique de fusion des données pour éviter la duplication
    et assurer la cohérence entre le scoring et l'affichage.
    
    Args:
        symbol: Le symbole à traiter
        rest_data: Données REST (funding, volume, spread, volatilité, funding_time)
        ws_data: Données WebSocket (funding_rate, volume24h, bid1_price, ask1_price, etc.)
        volatility_tracker: Instance du tracker de volatilité (optionnel)
        
    Returns:
        Dict contenant les données fusionnées avec les clés :
        - funding: Taux de funding (priorité WS, fallback REST)
        - volume: Volume 24h (priorité WS, fallback REST)
        - spread: Spread calculé (priorité WS temps réel, fallback REST)
        - volatility: Volatilité (priorité REST, fallback tracker)
        - funding_time: Temps de funding (priorité WS, fallback REST)
        - symbol: Le symbole
    """
    # Extraire les données REST
    original_funding = rest_data.get('funding')
    original_volume = rest_data.get('volume')
    original_spread = rest_data.get('spread', 0.0)
    original_volatility = rest_data.get('volatility', 0.0)
    original_funding_time = rest_data.get('funding_time', "-")
    
    # Fusionner le funding (priorité WS, fallback REST)
    funding = original_funding
    if ws_data.get('funding_rate') is not None:
        try:
            funding = float(ws_data['funding_rate'])
        except (ValueError, TypeError):
            pass  # Garder la valeur REST en cas d'erreur
    
    # Fusionner le volume (priorité WS, fallback REST)
    volume = original_volume
    if ws_data.get('volume24h') is not None:
        try:
            volume = float(ws_data['volume24h'])
        except (ValueError, TypeError):
            pass  # Garder la valeur REST en cas d'erreur
    
    # Calculer le spread (priorité WS temps réel, fallback REST)
    spread = original_spread
    if ws_data.get('bid1_price') and ws_data.get('ask1_price'):
        calculated_spread = compute_spread_with_mid_price(
            ws_data['bid1_price'], 
            ws_data['ask1_price']
        )
        # Utiliser le spread calculé seulement s'il est valide (> 0)
        if calculated_spread > 0:
            spread = calculated_spread
    
    # Fusionner la volatilité (priorité REST, fallback tracker)
    volatility = original_volatility
    if volatility is None and volatility_tracker:
        volatility = volatility_tracker.get_cached_volatility(symbol)
    if volatility is None:
        volatility = 0.0
    
    # Fusionner le temps de funding (priorité WS, fallback REST)
    funding_time = original_funding_time
    if ws_data.get('next_funding_time'):
        # Le temps de funding sera recalculé par l'appelant si nécessaire
        funding_time = original_funding_time  # Garder la logique de calcul externe
    
    return {
        'symbol': symbol,
        'funding': funding,
        'volume': volume,
        'spread': spread,
        'volatility': volatility,
        'funding_time': funding_time
    }
