#!/usr/bin/env python3
"""
Constantes centralisées pour le bot Bybit.

Ce module contient :
- Codes d'erreurs Bybit avec leurs messages
- Emojis et messages de logs communs
- Autres constantes utilisées dans le projet
"""

# =============================================================================
# CODES D'ERREURS BYBIT
# =============================================================================

BYBIT_ERROR_CODES = {
    # Codes d'authentification
    10005: "Invalid API Key",
    10006: "Permission denied",
    10016: "Rate limit exceeded",
    10017: "Invalid timestamp - system clock out of sync",
    10018: "IP not in whitelist",
    
    # Codes de trading
    30084: "Insufficient balance",
    30085: "Order not found",
    30086: "Position not found",
    30087: "Invalid order type",
    30088: "Invalid order size",
    30089: "Invalid order price",
    30090: "Order already exists",
    
    # Codes généraux
    10001: "Invalid request",
    10002: "Invalid API Key",
    10003: "Invalid signature",
    10004: "Invalid timestamp",
    10007: "Invalid request ID",
    10008: "Invalid request method",
    10009: "Invalid request parameter",
    10010: "Invalid request format",
    10011: "Invalid request size",
    10012: "Invalid request type",
    10013: "Invalid request version",
    10014: "Invalid request action",
    10015: "Invalid request data",
}

# Messages d'erreur personnalisés pour les codes les plus courants
BYBIT_ERROR_MESSAGES = {
    10005: "Authentification échouée : clé/secret invalides ou signature incorrecte",
    10006: "Permission denied",
    10016: "Limite de requêtes atteinte : ralentis ou réessaie plus tard",
    10017: "Horodatage invalide : horloge locale désynchronisée (corrige l'heure système)",
    10018: "Accès refusé : IP non autorisée (whitelist requise dans Bybit)",
    30084: "Solde insuffisant pour cette opération",
}

# =============================================================================
# EMOJIS ET MESSAGES DE LOGS
# =============================================================================

LOG_EMOJIS = {
    # Actions générales
    "start": "🚀",
    "stop": "🧹",
    "refresh": "🔄",
    "wait": "⏳",
    "config": "📂",
    "info": "ℹ️",
    
    # Statuts
    "ok": "✅",
    "success": "✅",
    "warn": "⚠️",
    "warning": "⚠️",
    "error": "❌",
    "fail": "❌",
    "trophy": "🏆",
    "target": "🎯",
    
    # Données et métriques
    "data": "📊",
    "metrics": "📊",
    "stats": "📊",
    "count": "🧮",
    "list": "📋",
    "map": "🗺️",
    "filters": "🎛️",
    "watchlist": "🧭",
    
    # Réseau et API
    "api": "📡",
    "network": "🌐",
    "websocket": "🔌",
    "connection": "🔗",
    "auth": "🔐",
    "search": "🔎",
    "monitor": "🩺",
    "thread": "🧵",
    
    # Trading
    "balance": "💼",
    "price": "💰",
    "volume": "📈",
    "spread": "📉",
    "funding": "🎲",
    "volatility": "📊",
}

# Messages de logs communs
LOG_MESSAGES = {
    "config_loaded": "Configuration chargée",
    "config_not_found": "Aucun fichier de paramètres trouvé (src/parameters.yaml) → utilisation des valeurs par défaut.",
    "config_loaded_from_file": "Configuration chargée depuis src/parameters.yaml",
    "perp_universe_retrieved": "Univers perp récupéré",
    "no_filtered_pairs": "Aucune paire filtrée disponible pour le classement",
    "no_valid_symbols": "Aucun symbole valide trouvé",
    "no_funding_available": "Aucun funding disponible pour la catégorie sélectionnée",
    "no_symbols_match_criteria": "Aucun symbole ne correspond aux critères de filtrage",
    "watchlist_rebuilt": "Watchlist reconstruite avec {count} paires sélectionnées",
    "scoring_applied": "Application du classement par score...",
    "scoring_refresh": "Rafraîchissement du classement par score...",
    "no_change_top": "Pas de changement dans le top 3",
    "new_top_detected": "Nouveau top détecté :",
    "initial_selection": "Sélection initiale : {symbols}",
    "waiting_first_ws_data": "En attente de la première donnée WS…",
    "ws_opened": "WS ouverte ({category})",
    "ws_subscription": "Souscription tickers → {count} symboles ({category})",
    "ws_connection": "Connexion à la WebSocket publique ({category})…",
    "ws_private_connection": "Connexion à la WebSocket privée…",
    "ws_authenticated": "Authentification WebSocket réussie",
    "ws_auth_failed": "Échec authentification WS : retCode={code} retMsg=\"{msg}\"",
    "ws_closed": "Connexion WebSocket fermée",
    "ws_error": "Erreur WebSocket: {error}",
    "ws_json_error": "Erreur JSON ({category}): {error}",
    "ws_subscription_error": "Erreur souscription {category}: {error}",
    "ws_no_symbols": "Aucun symbole à suivre pour {category}",
    "ws_callback_error": "Erreur callback on_open: {error}",
    "funding_rates_linear": "Récupération des funding rates pour linear (optimisé)…",
    "funding_rates_inverse": "Récupération des funding rates pour inverse (optimisé)…",
    "funding_rates_both": "Récupération des funding rates pour linear+inverse (optimisé: parallèle)…",
    "spread_evaluation": "Évaluation du spread (REST tickers) pour {count} symboles…",
    "spread_retrieval": "Récupération spreads (optimisé: batch=200, parallèle) - linear: {linear_count}, inverse: {inverse_count}…",
    "spread_filter_success": "Filtre spread : gardés={kept} | rejetés={rejected} (seuil {threshold:.2f}%)",
    "spread_filter_error": "Erreur lors de la récupération des spreads : {error}",
    "volatility_evaluation": "Évaluation de la volatilité 5m pour tous les symboles…",
    "volatility_calculation": "Calcul volatilité async (parallèle) pour {count} symboles…",
    "volatility_filter_success": "Filtre volatilité : gardés={kept} | rejetés={rejected} (seuils max={max_threshold:.2f}%)",
    "volatility_filter_error": "Erreur lors du calcul de la volatilité : {error}",
    "volatility_refresh": "Refresh volatilité : {count} symboles",
    "volatility_refresh_complete": "Refresh volatilité terminé: ok={ok} | fail={fail}",
    "volatility_thread_started": "Thread volatilité démarré",
    "volatility_thread_active": "Volatilité: thread actif | ttl={ttl}s | interval={interval}s",
    "filter_counts": "Comptes | avant filtres = {before} | après funding/volume/temps = {after_funding} | après spread = {after_spread} | après volatilité = {after_volatility} | après tri+limit = {final}",
    "symbols_retained": "Symboles retenus (Top {count}) : {symbols}",
    "symbols_linear_inverse": "Symboles linear: {linear_count}, inverse: {inverse_count}",
    "filters_config": "Filtres | catégorie={category} | funding_min={funding_min} | funding_max={funding_max} | volume_min_millions={volume_min} | spread_max={spread_max} | volatility_min={volatility_min} | volatility_max={volatility_max} | ft_min(min)={ft_min} | ft_max(min)={ft_max} | limite={limit} | vol_ttl={vol_ttl}s",
    "error_config": "Erreur de configuration : {error}",
    "error_realtime_update": "Erreur mise à jour données temps réel pour {symbol}: {error}",
    "error_scoring_refresh": "Erreur lors du rafraîchissement du scoring: {error}",
    "error_volatility": "Erreur : {error}",
}

# =============================================================================
# AUTRES CONSTANTES
# =============================================================================

# Timeouts et limites
DEFAULT_TIMEOUT = 10
DEFAULT_RECV_WINDOW = 10000
MAX_RETRY_ATTEMPTS = 4
BACKOFF_BASE = 0.5

# Intervalles de temps
VOLATILITY_TTL_DEFAULT = 120  # secondes
VOLATILITY_INTERVAL_DEFAULT = 60  # secondes
METRICS_INTERVAL_DEFAULT = 300  # secondes (5 minutes)

# Limites API
MAX_SYMBOLS_PER_REQUEST = 1000
MAX_BATCH_SIZE = 200

# Catégories de symboles
SYMBOL_CATEGORIES = ["linear", "inverse", "both"]

# Formats de données
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
FUNDING_TIME_FORMAT = "{hours}h {minutes}m {seconds}s"

# Messages d'erreur génériques
GENERIC_ERROR_MESSAGES = {
    "network_error": "Erreur réseau",
    "api_error": "Erreur API",
    "timeout_error": "Timeout de la requête",
    "json_error": "Erreur de parsing JSON",
    "unknown_error": "Erreur inconnue",
    "invalid_response": "Réponse invalide de l'API",
    "missing_data": "Données manquantes",
    "invalid_parameter": "Paramètre invalide",
}
