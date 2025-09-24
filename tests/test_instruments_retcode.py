"""Tests unitaires pour la gestion des retCode dans instruments.py."""

import pytest
import httpx
from unittest.mock import Mock, patch
from instruments import fetch_perpetual_instruments
from tests.mocks.bybit_responses import (
    get_success_response, get_invalid_api_key_response,
    get_permission_denied_response, get_unknown_error_response
)


class TestInstrumentsRetCode:
    """Tests pour la gestion des retCode dans instruments.py."""
    
    def setup_method(self):
        """Configuration pour chaque test."""
        self.base_url = "https://api-testnet.bybit.com"
        self.category = "linear"
    
    @patch('instruments.get_http_client')
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
        result = fetch_perpetual_instruments(self.base_url, self.category)
        
        # Vérifier que le résultat est retourné
        assert result is not None
        assert isinstance(result, list)
    
    @patch('instruments.get_http_client')
    def test_auth_error_10005(self, mock_get_client):
        """Test que retCode=10005 lève RuntimeError."""
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
            fetch_perpetual_instruments(self.base_url, self.category)
        
        # Vérifier le message d'erreur
        assert "Erreur API Bybit" in str(exc_info.value)
        assert "retCode=10005" in str(exc_info.value)
    
    @patch('instruments.get_http_client')
    def test_permission_denied_10006(self, mock_get_client):
        """Test que retCode=10006 lève RuntimeError."""
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
            fetch_perpetual_instruments(self.base_url, self.category)
        
        # Vérifier le message d'erreur
        assert "Erreur API Bybit" in str(exc_info.value)
        assert "retCode=10006" in str(exc_info.value)
    
    @patch('instruments.get_http_client')
    def test_unknown_error_99999(self, mock_get_client):
        """Test que retCode=99999 lève RuntimeError."""
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
            fetch_perpetual_instruments(self.base_url, self.category)
        
        # Vérifier le message d'erreur
        assert "Erreur API Bybit" in str(exc_info.value)
        assert "retCode=99999" in str(exc_info.value)
    
    @patch('instruments.get_http_client')
    def test_http_error_400(self, mock_get_client):
        """Test de la gestion des erreurs HTTP 400."""
        # Mock de la réponse HTTP avec erreur 400
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        
        # Mock du client HTTP
        mock_http_client = Mock()
        mock_http_client.get.return_value = mock_response
        mock_get_client.return_value = mock_http_client
        
        # Test que l'exception est levée
        with pytest.raises(httpx.HTTPStatusError):
            fetch_perpetual_instruments(self.base_url, self.category)
    
    @patch('instruments.get_http_client')
    def test_http_error_500(self, mock_get_client):
        """Test de la gestion des erreurs HTTP 500."""
        # Mock de la réponse HTTP avec erreur 500
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        
        # Mock du client HTTP
        mock_http_client = Mock()
        mock_http_client.get.return_value = mock_response
        mock_get_client.return_value = mock_http_client
        
        # Test que l'exception est levée
        with pytest.raises(httpx.HTTPStatusError):
            fetch_perpetual_instruments(self.base_url, self.category)
    
    @patch('instruments.get_http_client')
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
            fetch_perpetual_instruments(self.base_url, self.category)
    
    @patch('instruments.get_http_client')
    def test_network_error(self, mock_get_client):
        """Test de la gestion des erreurs réseau."""
        # Mock du client HTTP qui lève une exception réseau
        mock_http_client = Mock()
        mock_http_client.get.side_effect = httpx.RequestError("Network error")
        mock_get_client.return_value = mock_http_client
        
        # Test que l'exception est propagée
        with pytest.raises(httpx.RequestError):
            fetch_perpetual_instruments(self.base_url, self.category)
    
    @patch('instruments.get_http_client')
    def test_timeout_error(self, mock_get_client):
        """Test de la gestion des erreurs de timeout."""
        # Mock du client HTTP qui lève une exception de timeout
        mock_http_client = Mock()
        mock_http_client.get.side_effect = httpx.TimeoutException("Request timeout")
        mock_get_client.return_value = mock_http_client
        
        # Test que l'exception est propagée
        with pytest.raises(httpx.TimeoutException):
            fetch_perpetual_instruments(self.base_url, self.category)
