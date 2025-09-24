"""Exceptions personnalisées pour le bot Bybit."""


class BotError(Exception):
    """Base des erreurs du bot."""


class NoSymbolsError(BotError):
    """Aucun symbole ne correspond aux critères ou n'est disponible."""


class FundingUnavailableError(BotError):
    """Aucun funding disponible pour la catégorie sélectionnée."""


class ConfigError(BotError):
    """Erreur de configuration (paramètres invalides ou manquants)."""


# =============================================================================
# EXCEPTIONS POUR L'API BYBIT
# =============================================================================

class BybitAPIError(BotError):
    """Erreur générique de l'API Bybit."""
    
    def __init__(self, ret_code, ret_msg, message=None):
        self.ret_code = ret_code
        self.ret_msg = ret_msg
        if message is None:
            message = f"Erreur API Bybit : retCode={ret_code} retMsg=\"{ret_msg}\""
        super().__init__(message)


class BybitAuthError(BybitAPIError):
    """Erreur d'authentification Bybit."""
    
    def __init__(self, ret_code, ret_msg, message=None):
        if message is None:
            message = f"Authentification échouée : clé/secret invalides ou signature incorrecte (retCode={ret_code})"
        super().__init__(ret_code, ret_msg, message)


class BybitInvalidParams(BybitAPIError):
    """Erreur de paramètres invalides Bybit."""
    
    def __init__(self, ret_code, ret_msg, message=None):
        if message is None:
            message = f"Paramètres invalides : {ret_msg} (retCode={ret_code})"
        super().__init__(ret_code, ret_msg, message)


class BybitRateLimitError(BybitAPIError):
    """Erreur de limite de taux Bybit."""
    
    def __init__(self, ret_code, ret_msg, message=None):
        if message is None:
            message = f"Limite de requêtes atteinte : ralentis ou réessaie plus tard (retCode={ret_code})"
        super().__init__(ret_code, ret_msg, message)


class BybitIPWhitelistError(BybitAPIError):
    """Erreur d'IP non autorisée Bybit."""
    
    def __init__(self, ret_code, ret_msg, message=None):
        if message is None:
            message = f"Accès refusé : IP non autorisée (whitelist requise dans Bybit) (retCode={ret_code})"
        super().__init__(ret_code, ret_msg, message)


class BybitTimestampError(BybitAPIError):
    """Erreur de timestamp Bybit."""
    
    def __init__(self, ret_code, ret_msg, message=None):
        if message is None:
            message = f"Horodatage invalide : horloge locale désynchronisée (corrige l'heure système) (retCode={ret_code})"
        super().__init__(ret_code, ret_msg, message)


class BybitTradingError(BybitAPIError):
    """Erreur de trading Bybit."""
    
    def __init__(self, ret_code, ret_msg, message=None):
        if message is None:
            message = f"Erreur de trading : {ret_msg} (retCode={ret_code})"
        super().__init__(ret_code, ret_msg, message)


