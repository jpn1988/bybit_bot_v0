"""Tests unitaires pour la gestion des retCode de l'API Bybit."""

import pytest
import httpx
from unittest.mock import Mock, patch, MagicMock
from bybit_client import BybitClient
from errors import (
    BybitAPIError, BybitAuthError, BybitInvalidParams, BybitRateLimitError,
    BybitIPWhitelistError, BybitTimestampError, BybitTradingError
)
from tests.mocks.bybit_responses import (
    get_success_response, get_wallet_balance_success,
    get_invalid_api_key_response, get_permission_denied_response,
    get_rate_limit_response, get_invalid_timestamp_response,
    get_ip_not_whitelisted_response, get_invalid_params_response,
    get_invalid_request_response, get_insufficient_balance_response,
    get_unknown_error_response, get_malformed_response,
    get_missing_result_response, get_all_error_responses
)


class TestBybitRetCodeHandling:
    """Tests pour la gestion des retCode de l'API Bybit."""
    
    def setup_method(self):
        """Configuration pour chaque test."""
        self.client = BybitClient(
            testnet=True,
            timeout=10,
            api_key="test_api_key",
            api_secret="test_api_secret"
        )
    
    @patch('bybit_client.get_http_client')
    def test_success_retcode_0(self, mock_get_client):
        """Test que retCode=0 ne lève pas d'exception."""
        # Mock de la réponse HTTP
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = get_success_response()
        
        # Mock du client HTTP
        mock_http_client = Mock()
        mock_http_client.get.return_value = mock_response
        mock_get_client.return_value = mock_http_client
        
        # Test que la méthode ne lève pas d'exception
        result = self.client._get_private("/v5/account/wallet-balance")
        
        # Vérifier que le résultat est retourné
        assert result is not None
        assert "list" in result
    
    @patch('bybit_client.get_http_client')
    def test_auth_error_10005(self, mock_get_client):
        """Test que retCode=10005 lève BybitAuthError."""
        # Mock de la réponse HTTP
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = get_invalid_api_key_response()
        
        # Mock du client HTTP
        mock_http_client = Mock()
        mock_http_client.get.return_value = mock_response
        mock_get_client.return_value = mock_http_client
        
        # Test que l'exception est levée
        with pytest.raises(RuntimeError) as exc_info:
            self.client._get_private("/v5/account/wallet-balance")
        
        # Vérifier le message d'erreur
        assert "Authentification échouée" in str(exc_info.value)
    
    @patch('bybit_client.get_http_client')
    def test_auth_error_10006(self, mock_get_client):
        """Test que retCode=10006 lève BybitAuthError."""
        # Mock de la réponse HTTP
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = get_permission_denied_response()
        
        # Mock du client HTTP
        mock_http_client = Mock()
        mock_http_client.get.return_value = mock_response
        mock_get_client.return_value = mock_http_client
        
        # Test que l'exception est levée
        with pytest.raises(RuntimeError) as exc_info:
            self.client._get_private("/v5/account/wallet-balance")
        
        # Vérifier le message d'erreur
        assert "Authentification échouée" in str(exc_info.value)
    
    @patch('bybit_client.get_http_client')
    def test_rate_limit_10016(self, mock_get_client):
        """Test que retCode=10016 gère le rate limiting."""
        # Mock de la réponse HTTP
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = get_rate_limit_response()
        mock_response.headers = {}  # Pas de Retry-After
        
        # Mock du client HTTP
        mock_http_client = Mock()
        mock_http_client.get.return_value = mock_response
        mock_get_client.return_value = mock_http_client
        
        # Test que l'exception est levée après les tentatives
        with pytest.raises(RuntimeError) as exc_info:
            self.client._get_private("/v5/account/wallet-balance")
        
        # Vérifier le message d'erreur
        assert "Limite de requêtes atteinte" in str(exc_info.value)
    
    @patch('bybit_client.get_http_client')
    def test_timestamp_error_10017(self, mock_get_client):
        """Test que retCode=10017 lève BybitTimestampError."""
        # Mock de la réponse HTTP
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = get_invalid_timestamp_response()
        
        # Mock du client HTTP
        mock_http_client = Mock()
        mock_http_client.get.return_value = mock_response
        mock_get_client.return_value = mock_http_client
        
        # Test que l'exception est levée
        with pytest.raises(RuntimeError) as exc_info:
            self.client._get_private("/v5/account/wallet-balance")
        
        # Vérifier le message d'erreur
        assert "Horodatage invalide" in str(exc_info.value)
    
    @patch('bybit_client.get_http_client')
    def test_ip_whitelist_error_10018(self, mock_get_client):
        """Test que retCode=10018 lève BybitIPWhitelistError."""
        # Mock de la réponse HTTP
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = get_ip_not_whitelisted_response()
        
        # Mock du client HTTP
        mock_http_client = Mock()
        mock_http_client.get.return_value = mock_response
        mock_get_client.return_value = mock_http_client
        
        # Test que l'exception est levée
        with pytest.raises(RuntimeError) as exc_info:
            self.client._get_private("/v5/account/wallet-balance")
        
        # Vérifier le message d'erreur
        assert "Accès refusé" in str(exc_info.value)
    
    @patch('bybit_client.get_http_client')
    def test_invalid_params_10002(self, mock_get_client):
        """Test que retCode=10002 lève une exception générique."""
        # Mock de la réponse HTTP
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = get_invalid_params_response()
        
        # Mock du client HTTP
        mock_http_client = Mock()
        mock_http_client.get.return_value = mock_response
        mock_get_client.return_value = mock_http_client
        
        # Test que l'exception est levée
        with pytest.raises(RuntimeError) as exc_info:
            self.client._get_private("/v5/account/wallet-balance")
        
        # Vérifier le message d'erreur
        assert "Erreur API Bybit" in str(exc_info.value)
        assert "retCode=10002" in str(exc_info.value)
    
    @patch('bybit_client.get_http_client')
    def test_trading_error_30084(self, mock_get_client):
        """Test que retCode=30084 lève une exception générique."""
        # Mock de la réponse HTTP
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = get_insufficient_balance_response()
        
        # Mock du client HTTP
        mock_http_client = Mock()
        mock_http_client.get.return_value = mock_response
        mock_get_client.return_value = mock_http_client
        
        # Test que l'exception est levée
        with pytest.raises(RuntimeError) as exc_info:
            self.client._get_private("/v5/account/wallet-balance")
        
        # Vérifier le message d'erreur
        assert "Erreur API Bybit" in str(exc_info.value)
        assert "retCode=30084" in str(exc_info.value)
    
    @patch('bybit_client.get_http_client')
    def test_unknown_error_99999(self, mock_get_client):
        """Test que retCode=99999 lève une exception générique."""
        # Mock de la réponse HTTP
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = get_unknown_error_response()
        
        # Mock du client HTTP
        mock_http_client = Mock()
        mock_http_client.get.return_value = mock_response
        mock_get_client.return_value = mock_http_client
        
        # Test que l'exception est levée
        with pytest.raises(RuntimeError) as exc_info:
            self.client._get_private("/v5/account/wallet-balance")
        
        # Vérifier le message d'erreur
        assert "Erreur API Bybit" in str(exc_info.value)
        assert "retCode=99999" in str(exc_info.value)
    
    @patch('bybit_client.get_http_client')
    def test_malformed_response(self, mock_get_client):
        """Test avec une réponse malformée (sans retCode)."""
        # Mock de la réponse HTTP
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = get_malformed_response()
        
        # Mock du client HTTP
        mock_http_client = Mock()
        mock_http_client.get.return_value = mock_response
        mock_get_client.return_value = mock_http_client
        
        # Test que la méthode ne lève pas d'exception (retCode par défaut = 0)
        result = self.client._get_private("/v5/account/wallet-balance")
        
        # Vérifier que le résultat est retourné
        assert result is not None
    
    @patch('bybit_client.get_http_client')
    def test_missing_result_field(self, mock_get_client):
        """Test avec une réponse sans champ result."""
        # Mock de la réponse HTTP
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = get_missing_result_response()
        
        # Mock du client HTTP
        mock_http_client = Mock()
        mock_http_client.get.return_value = mock_response
        mock_get_client.return_value = mock_http_client
        
        # Test que la méthode ne lève pas d'exception
        result = self.client._get_private("/v5/account/wallet-balance")
        
        # Vérifier que le résultat est un dictionnaire vide
        assert result == {}
    
    @patch('bybit_client.get_http_client')
    def test_all_error_codes(self, mock_get_client):
        """Test avec tous les codes d'erreur disponibles."""
        error_responses = get_all_error_responses()
        
        for response in error_responses:
            # Mock de la réponse HTTP
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = response
            mock_response.headers = {}  # Pas de Retry-After pour les tests
            
            # Mock du client HTTP
            mock_http_client = Mock()
            mock_http_client.get.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            ret_code = response.get("retCode", 0)
            
            if ret_code == 0:
                # Succès - ne doit pas lever d'exception
                result = self.client._get_private("/v5/account/wallet-balance")
                assert result is not None
            else:
                # Erreur - doit lever une exception
                with pytest.raises(RuntimeError):
                    self.client._get_private("/v5/account/wallet-balance")
    
    @patch('bybit_client.get_http_client')
    def test_http_error_handling(self, mock_get_client):
        """Test de la gestion des erreurs HTTP."""
        # Mock du client HTTP qui lève une exception
        mock_http_client = Mock()
        mock_http_client.get.side_effect = httpx.HTTPStatusError("Server error", request=None, response=None)
        mock_get_client.return_value = mock_http_client
        
        # Test que l'exception est propagée
        with pytest.raises(httpx.HTTPStatusError):
            self.client._get_private("/v5/account/wallet-balance")
    
    @patch('bybit_client.get_http_client')
    def test_timeout_error_handling(self, mock_get_client):
        """Test de la gestion des erreurs de timeout."""
        # Mock du client HTTP qui lève une exception de timeout
        mock_http_client = Mock()
        mock_http_client.get.side_effect = httpx.TimeoutException("Request timeout")
        mock_get_client.return_value = mock_http_client
        
        # Test que l'exception est propagée
        with pytest.raises(httpx.TimeoutException):
            self.client._get_private("/v5/account/wallet-balance")
    
    @patch('bybit_client.get_http_client')
    def test_json_parsing_error(self, mock_get_client):
        """Test de la gestion des erreurs de parsing JSON."""
        # Mock de la réponse HTTP avec JSON invalide
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        
        # Mock du client HTTP
        mock_http_client = Mock()
        mock_http_client.get.return_value = mock_response
        mock_get_client.return_value = mock_http_client
        
        # Test que l'exception est propagée
        with pytest.raises(ValueError):
            self.client._get_private("/v5/account/wallet-balance")
    
    def test_client_initialization_without_keys(self):
        """Test de l'initialisation du client sans clés API."""
        with pytest.raises(RuntimeError) as exc_info:
            BybitClient(testnet=True, api_key=None, api_secret=None)
        
        assert "Clés API manquantes" in str(exc_info.value)
    
    def test_client_initialization_with_empty_keys(self):
        """Test de l'initialisation du client avec des clés vides."""
        with pytest.raises(RuntimeError) as exc_info:
            BybitClient(testnet=True, api_key="", api_secret="")
        
        assert "Clés API manquantes" in str(exc_info.value)
    
    @patch('bybit_client.get_http_client')
    def test_metrics_recording_on_success(self, mock_get_client):
        """Test que les métriques sont enregistrées en cas de succès."""
        # Mock de la réponse HTTP
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = get_success_response()
        
        # Mock du client HTTP
        mock_http_client = Mock()
        mock_http_client.get.return_value = mock_response
        mock_get_client.return_value = mock_http_client
        
        # Mock de record_api_call
        with patch('bybit_client.record_api_call') as mock_record:
            self.client._get_private("/v5/account/wallet-balance")
            
            # Vérifier que record_api_call a été appelé avec success=True
            mock_record.assert_called_once()
            args = mock_record.call_args[0]
            assert len(args) == 2
            assert args[1] is True  # success=True
    
    @patch('bybit_client.get_http_client')
    def test_metrics_recording_on_error(self, mock_get_client):
        """Test que les métriques sont enregistrées en cas d'erreur."""
        # Mock de la réponse HTTP avec erreur
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = get_invalid_api_key_response()
        
        # Mock du client HTTP
        mock_http_client = Mock()
        mock_http_client.get.return_value = mock_response
        mock_get_client.return_value = mock_http_client
        
        # Mock de record_api_call
        with patch('bybit_client.record_api_call') as mock_record:
            try:
                self.client._get_private("/v5/account/wallet-balance")
            except RuntimeError:
                pass
            
            # Vérifier que record_api_call n'a pas été appelé (erreur avant enregistrement)
            mock_record.assert_not_called()
