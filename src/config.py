"""Configuration module for bybit_bot_v0."""

import os
from dotenv import load_dotenv

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()


def get_settings():
    """
    Retourne un dictionnaire avec les paramètres de configuration.
    Valide également les variables d'environnement pour détecter les fautes de frappe.
    
    Returns:
        dict: Dictionnaire contenant les paramètres de configuration
    """
    # Liste des variables d'environnement valides pour la configuration
    valid_env_vars = {
        "BYBIT_API_KEY", "BYBIT_API_SECRET", "TESTNET", "TIMEOUT", "LOG_LEVEL",
        "SPREAD_MAX", "VOLUME_MIN_MILLIONS", "VOLATILITY_MIN", "VOLATILITY_MAX",
        "FUNDING_MIN", "FUNDING_MAX", "CATEGORY", "LIMIT", "VOLATILITY_TTL_SEC",
        "FUNDING_TIME_MIN_MINUTES", "FUNDING_TIME_MAX_MINUTES", "WS_PRIV_CHANNELS",
        "REFRESH_WATCHLIST_INTERVAL",
        # Variables de rate limiting public (utilisées par volatility.get_async_rate_limiter)
        "PUBLIC_HTTP_MAX_CALLS_PER_SEC", "PUBLIC_HTTP_WINDOW_SECONDS",
    }
    
    # Détecter les variables d'environnement inconnues
    all_env_vars = set(os.environ.keys())
    unknown_vars = all_env_vars - valid_env_vars
    
    # Filtrer les variables système et les variables non liées au bot
    bot_related_unknown = []
    for var in unknown_vars:
        # Ignorer les variables système Windows/Python et les variables non liées au bot
        if not any(prefix in var.upper() for prefix in [
            "PATH", "PYTHON", "WINDOWS", "USER", "HOME", "TEMP", "TMP",
            "PROGRAM", "SYSTEM", "ALLUSER", "APPDATA", "LOCALAPPDATA",
            "COMPUTERNAME", "USERNAME", "USERPROFILE", "WINDIR", "COMSPEC",
            "PATHEXT", "PROCESSOR", "NUMBER_OF_PROCESSORS", "OS", "DRIVE",
            "VIRTUAL_ENV", "CONDA", "PIP", "NODE", "NPM", "GIT", "SSH",
            "DOCKER", "KUBERNETES", "AWS", "AZURE", "GOOGLE", "JAVA",
            "MAVEN", "GRADLE", "NODEJS", "NPM", "YARN", "BOWER"
        ]):
            # Vérifier si la variable semble liée au bot (contient des mots-clés)
            if any(keyword in var.upper() for keyword in [
                "BYBIT", "FUNDING", "VOLATILITY", "SPREAD", "VOLUME", "CATEGORY",
                "LIMIT", "TTL", "TIME", "MIN", "MAX", "CHANNELS", "WS", "PRIV"
            ]):
                bot_related_unknown.append(var)
    
    # Logger les variables inconnues liées au bot
    if bot_related_unknown:
        # Afficher directement sur stderr pour être sûr que le message soit visible
        import sys
        for var in bot_related_unknown:
            print(f"⚠️ Variable d'environnement inconnue ignorée: {var}", file=sys.stderr)
            print(f"💡 Variables valides: {', '.join(sorted(valid_env_vars))}", file=sys.stderr)
        
        # Essayer aussi avec le logger si disponible
        try:
            import logging
            logger = logging.getLogger(__name__)
            for var in bot_related_unknown:
                logger.warning(f"⚠️ Variable d'environnement inconnue ignorée: {var}")
                logger.warning(f"💡 Variables valides: {', '.join(sorted(valid_env_vars))}")
        except Exception:
            pass  # Le message a déjà été affiché sur stderr
    # Récupérer les clés API et convertir les chaînes vides en None
    api_key = os.getenv("BYBIT_API_KEY") or None
    api_secret = os.getenv("BYBIT_API_SECRET") or None
    
    # Récupérer les nouvelles variables d'environnement pour les filtres
    spread_max = os.getenv("SPREAD_MAX")
    volume_min_millions = os.getenv("VOLUME_MIN_MILLIONS")
    volatility_min = os.getenv("VOLATILITY_MIN")
    volatility_max = os.getenv("VOLATILITY_MAX")
    # Variables supplémentaires alignées avec le README
    funding_min = os.getenv("FUNDING_MIN")
    funding_max = os.getenv("FUNDING_MAX")
    category = os.getenv("CATEGORY")  # linear | inverse | both
    limit = os.getenv("LIMIT")
    volatility_ttl_sec = os.getenv("VOLATILITY_TTL_SEC")
    # Nouveaux paramètres de filtre temporel funding
    funding_time_min_minutes = os.getenv("FUNDING_TIME_MIN_MINUTES")
    funding_time_max_minutes = os.getenv("FUNDING_TIME_MAX_MINUTES")
    # Paramètre de rafraîchissement périodique de la watchlist
    refresh_watchlist_interval = os.getenv("REFRESH_WATCHLIST_INTERVAL")
    
    
    # Convertir en float/int si présentes, sinon None (avec gestion d'erreur)
    def safe_float(value):
        try:
            return float(value) if value else None
        except (ValueError, TypeError):
            return None
    
    def safe_int(value):
        try:
            return int(value) if value else None
        except (ValueError, TypeError):
            return None
    
    spread_max = safe_float(spread_max)
    volume_min_millions = safe_float(volume_min_millions)
    volatility_min = safe_float(volatility_min)
    volatility_max = safe_float(volatility_max)
    funding_min = safe_float(funding_min)
    funding_max = safe_float(funding_max)
    limit = safe_int(limit)
    volatility_ttl_sec = safe_int(volatility_ttl_sec)
    # Conversions minutes → int
    funding_time_min_minutes = safe_int(funding_time_min_minutes)
    funding_time_max_minutes = safe_int(funding_time_max_minutes)
    # Conversion refresh_watchlist_interval → int
    refresh_watchlist_interval = safe_int(refresh_watchlist_interval)
    
    return {
        "testnet": os.getenv("TESTNET", "true").lower() == "true",
        "timeout": safe_int(os.getenv("TIMEOUT", "10")) or 10,
        "log_level": os.getenv("LOG_LEVEL", "INFO").upper(),
        "api_key": api_key,
        "api_secret": api_secret,
        "spread_max": spread_max,
        "volume_min_millions": volume_min_millions,
        "volatility_min": volatility_min,
        "volatility_max": volatility_max,
        # Ajouts alignés README
        "funding_min": funding_min,
        "funding_max": funding_max,
        "category": category,
        "limit": limit,
        "volatility_ttl_sec": volatility_ttl_sec,
        # Nouveaux paramètres temporels
        "funding_time_min_minutes": funding_time_min_minutes,
        "funding_time_max_minutes": funding_time_max_minutes,
        # Paramètre de rafraîchissement périodique
        "refresh_watchlist_interval": refresh_watchlist_interval,
    }
