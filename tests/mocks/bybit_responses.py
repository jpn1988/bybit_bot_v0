"""Mocks de réponses API Bybit pour les tests."""

# =============================================================================
# RÉPONSES DE SUCCÈS
# =============================================================================

def get_success_response():
    """Réponse de succès standard."""
    return {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "list": [
                {
                    "symbol": "BTCUSDT",
                    "fundingRate": "0.0001",
                    "volume24h": "1000000.0",
                    "nextFundingTime": "1640995200000",
                    "bid1Price": "50000.0",
                    "ask1Price": "50001.0"
                }
            ]
        }
    }

def get_wallet_balance_success():
    """Réponse de succès pour le solde de portefeuille."""
    return {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "list": [
                {
                    "accountType": "UNIFIED",
                    "accountId": "123456",
                    "totalWalletBalance": "1000.0",
                    "totalUnrealizedPnl": "0.0",
                    "totalMarginBalance": "1000.0",
                    "totalAvailableBalance": "1000.0",
                    "totalPerpUPL": "0.0",
                    "totalInitialMargin": "0.0",
                    "totalMaintenanceMargin": "0.0",
                    "coin": [
                        {
                            "coin": "USDT",
                            "walletBalance": "1000.0",
                            "availableBalance": "1000.0"
                        }
                    ]
                }
            ]
        }
    }

# =============================================================================
# RÉPONSES D'ERREUR - CODES D'AUTHENTIFICATION
# =============================================================================

def get_auth_error_response(ret_code=10005):
    """Réponse d'erreur d'authentification."""
    error_messages = {
        10005: "Invalid API Key",
        10006: "Permission denied",
        10016: "Rate limit exceeded",
        10017: "Invalid timestamp - system clock out of sync",
        10018: "IP not in whitelist"
    }
    
    return {
        "retCode": ret_code,
        "retMsg": error_messages.get(ret_code, "Unknown error"),
        "result": {}
    }

def get_invalid_api_key_response():
    """Réponse pour clé API invalide."""
    return get_auth_error_response(10005)

def get_permission_denied_response():
    """Réponse pour permission refusée."""
    return get_auth_error_response(10006)

def get_rate_limit_response():
    """Réponse pour limite de taux atteinte."""
    return get_auth_error_response(10016)

def get_invalid_timestamp_response():
    """Réponse pour timestamp invalide."""
    return get_auth_error_response(10017)

def get_ip_not_whitelisted_response():
    """Réponse pour IP non autorisée."""
    return get_auth_error_response(10018)

# =============================================================================
# RÉPONSES D'ERREUR - CODES DE PARAMÈTRES
# =============================================================================

def get_invalid_params_response():
    """Réponse pour paramètres invalides."""
    return {
        "retCode": 10002,
        "retMsg": "Invalid API Key",
        "result": {}
    }

def get_invalid_request_response():
    """Réponse pour requête invalide."""
    return {
        "retCode": 10001,
        "retMsg": "Invalid request",
        "result": {}
    }

def get_invalid_signature_response():
    """Réponse pour signature invalide."""
    return {
        "retCode": 10003,
        "retMsg": "Invalid signature",
        "result": {}
    }

# =============================================================================
# RÉPONSES D'ERREUR - CODES DE TRADING
# =============================================================================

def get_insufficient_balance_response():
    """Réponse pour solde insuffisant."""
    return {
        "retCode": 30084,
        "retMsg": "Insufficient balance",
        "result": {}
    }

def get_order_not_found_response():
    """Réponse pour ordre non trouvé."""
    return {
        "retCode": 30085,
        "retMsg": "Order not found",
        "result": {}
    }

def get_position_not_found_response():
    """Réponse pour position non trouvée."""
    return {
        "retCode": 30086,
        "retMsg": "Position not found",
        "result": {}
    }

# =============================================================================
# RÉPONSES D'ERREUR - CODES INCONNUS
# =============================================================================

def get_unknown_error_response():
    """Réponse pour erreur inconnue."""
    return {
        "retCode": 99999,
        "retMsg": "Unknown error",
        "result": {}
    }

def get_custom_error_response(ret_code, ret_msg):
    """Réponse d'erreur personnalisée."""
    return {
        "retCode": ret_code,
        "retMsg": ret_msg,
        "result": {}
    }

# =============================================================================
# RÉPONSES D'ERREUR - CODES GÉNÉRIQUES
# =============================================================================

def get_invalid_request_parameter_response():
    """Réponse pour paramètre de requête invalide."""
    return {
        "retCode": 10009,
        "retMsg": "Invalid request parameter",
        "result": {}
    }

def get_invalid_request_format_response():
    """Réponse pour format de requête invalide."""
    return {
        "retCode": 10010,
        "retMsg": "Invalid request format",
        "result": {}
    }

def get_invalid_request_size_response():
    """Réponse pour taille de requête invalide."""
    return {
        "retCode": 10011,
        "retMsg": "Invalid request size",
        "result": {}
    }

# =============================================================================
# RÉPONSES SPÉCIALES POUR LES TESTS
# =============================================================================

def get_empty_result_response():
    """Réponse avec résultat vide."""
    return {
        "retCode": 0,
        "retMsg": "OK",
        "result": {}
    }

def get_malformed_response():
    """Réponse malformée (sans retCode)."""
    return {
        "retMsg": "OK",
        "result": {}
    }

def get_missing_result_response():
    """Réponse sans champ result."""
    return {
        "retCode": 0,
        "retMsg": "OK"
    }

# =============================================================================
# UTILITAIRES POUR LES TESTS
# =============================================================================

def get_all_error_responses():
    """Retourne toutes les réponses d'erreur disponibles."""
    return [
        get_invalid_api_key_response(),
        get_permission_denied_response(),
        get_rate_limit_response(),
        get_invalid_timestamp_response(),
        get_ip_not_whitelisted_response(),
        get_invalid_params_response(),
        get_invalid_request_response(),
        get_invalid_signature_response(),
        get_insufficient_balance_response(),
        get_order_not_found_response(),
        get_position_not_found_response(),
        get_unknown_error_response(),
        get_invalid_request_parameter_response(),
        get_invalid_request_format_response(),
        get_invalid_request_size_response(),
    ]

def get_success_responses():
    """Retourne toutes les réponses de succès disponibles."""
    return [
        get_success_response(),
        get_wallet_balance_success(),
        get_empty_result_response(),
    ]

def get_special_responses():
    """Retourne les réponses spéciales pour les tests."""
    return [
        get_malformed_response(),
        get_missing_result_response(),
    ]
