"""Tests unitaires pour la gestion des retCode dans WatchlistDataFetcher."""

import pytest
import httpx
from unittest.mock import Mock, patch
from watchlist_data_fetcher import WatchlistDataFetcher
from tests.mocks.bybit_responses import (
    get_success_response, get_invalid_api_key_response,
    get_permission_denied_response, get_rate_limit_response,
    get_unknown_error_response, get_all_error_responses
)


class TestWatchlistDataFetcherRetCode:
    """Tests pour la gestion des retCode dans WatchlistDataFetcher."""
    
    def setup_method(self):
        """Configuration pour chaque test."""
        self.fetcher = WatchlistDataFetcher()
        self.base_url = "https://api-testnet.bybit.com"
        self.category = "linear"
    
    @patch('watchlist_data_fetcher.get_http_client')
    @patch('watchlist_data_fetcher.get_rate_limiter')
    def test_success_retcode_0(self, mock_get_rate_limiter, mock_get_client):
        """Test que retCode=0 ne lève pas d'exception."""
        # Mock du rate limiter
        mock_rate_limiter = Mock()
        mock_get_rate_limiter.return_value = mock_rate_limiter
        
        # Mock de la réponse HTTP
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = get_success_response()
        
        # Mock du client HTTP
        mock_http_client = Mock()
        mock_http_client.get.return_value = mock_response
        mock_get_client.return_value = mock_http_client
        
        # Test que la méthode ne lève pas d'exception
        result = self.fetcher.fetch_funding_map(self.base_url, self.category)
        
        # Vérifier que le résultat est retourné
        assert result is not None
        assert isinstance(result, dict)
    
    @patch('watchlist_data_fetcher.get_http_client')
    @patch('watchlist_data_fetcher.get_rate_limiter')
    def test_auth_error_10005(self, mock_get_rate_limiter, mock_get_client):
        """Test que retCode=10005 lève RuntimeError."""
        # Mock du rate limiter
        mock_rate_limiter = Mock()
        mock_get_rate_limiter.return_value = mock_rate_limiter
        
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
            self.fetcher.fetch_funding_map(self.base_url, self.category)
        
        # Vérifier le message d'erreur
        assert "Erreur API Bybit" in str(exc_info.value)
        assert "retCode=10005" in str(exc_info.value)
    
    @patch('watchlist_data_fetcher.get_http_client')
    @patch('watchlist_data_fetcher.get_rate_limiter')
    def test_permission_denied_10006(self, mock_get_rate_limiter, mock_get_client):
        """Test que retCode=10006 lève RuntimeError."""
        # Mock du rate limiter
        mock_rate_limiter = Mock()
        mock_get_rate_limiter.return_value = mock_rate_limiter
        
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
            self.fetcher.fetch_funding_map(self.base_url, self.category)
        
        # Vérifier le message d'erreur
        assert "Erreur API Bybit" in str(exc_info.value)
        assert "retCode=10006" in str(exc_info.value)
    
    @patch('watchlist_data_fetcher.get_http_client')
    @patch('watchlist_data_fetcher.get_rate_limiter')
    def test_rate_limit_10016(self, mock_get_rate_limiter, mock_get_client):
        """Test que retCode=10016 lève RuntimeError."""
        # Mock du rate limiter
        mock_rate_limiter = Mock()
        mock_get_rate_limiter.return_value = mock_rate_limiter
        
        # Mock de la réponse HTTP
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = get_rate_limit_response()
        
        # Mock du client HTTP
        mock_http_client = Mock()
        mock_http_client.get.return_value = mock_response
        mock_get_client.return_value = mock_http_client
        
        # Test que l'exception est levée
        with pytest.raises(RuntimeError) as exc_info:
            self.fetcher.fetch_funding_map(self.base_url, self.category)
        
        # Vérifier le message d'erreur
        assert "Erreur API Bybit" in str(exc_info.value)
        assert "retCode=10016" in str(exc_info.value)
    
    @patch('watchlist_data_fetcher.get_http_client')
    @patch('watchlist_data_fetcher.get_rate_limiter')
    def test_unknown_error_99999(self, mock_get_rate_limiter, mock_get_client):
        """Test que retCode=99999 lève RuntimeError."""
        # Mock du rate limiter
        mock_rate_limiter = Mock()
        mock_get_rate_limiter.return_value = mock_rate_limiter
        
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
            self.fetcher.fetch_funding_map(self.base_url, self.category)
        
        # Vérifier le message d'erreur
        assert "Erreur API Bybit" in str(exc_info.value)
        assert "retCode=99999" in str(exc_info.value)
    
    @patch('watchlist_data_fetcher.get_http_client')
    @patch('watchlist_data_fetcher.get_rate_limiter')
    def test_http_error_400(self, mock_get_rate_limiter, mock_get_client):
        """Test de la gestion des erreurs HTTP 400."""
        # Mock du rate limiter
        mock_rate_limiter = Mock()
        mock_get_rate_limiter.return_value = mock_rate_limiter
        
        # Mock de la réponse HTTP avec erreur 400
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        
        # Mock du client HTTP
        mock_http_client = Mock()
        mock_http_client.get.return_value = mock_response
        mock_get_client.return_value = mock_http_client
        
        # Test que l'exception est levée
        with pytest.raises(RuntimeError) as exc_info:
            self.fetcher.fetch_funding_map(self.base_url, self.category)
        
        # Vérifier le message d'erreur
        assert "Erreur HTTP Bybit" in str(exc_info.value)
        assert "status=400" in str(exc_info.value)
    
    @patch('watchlist_data_fetcher.get_http_client')
    @patch('watchlist_data_fetcher.get_rate_limiter')
    def test_http_error_500(self, mock_get_rate_limiter, mock_get_client):
        """Test de la gestion des erreurs HTTP 500."""
        # Mock du rate limiter
        mock_rate_limiter = Mock()
        mock_get_rate_limiter.return_value = mock_rate_limiter
        
        # Mock de la réponse HTTP avec erreur 500
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        
        # Mock du client HTTP
        mock_http_client = Mock()
        mock_http_client.get.return_value = mock_response
        mock_get_client.return_value = mock_http_client
        
        # Test que l'exception est levée
        with pytest.raises(RuntimeError) as exc_info:
            self.fetcher.fetch_funding_map(self.base_url, self.category)
        
        # Vérifier le message d'erreur
        assert "Erreur HTTP Bybit" in str(exc_info.value)
        assert "status=500" in str(exc_info.value)
    
    @patch('watchlist_data_fetcher.get_http_client')
    @patch('watchlist_data_fetcher.get_rate_limiter')
    def test_all_error_codes(self, mock_get_rate_limiter, mock_get_client):
        """Test avec tous les codes d'erreur disponibles."""
        error_responses = get_all_error_responses()
        
        for response in error_responses:
            # Mock du rate limiter
            mock_rate_limiter = Mock()
            mock_get_rate_limiter.return_value = mock_rate_limiter
            
            # Mock de la réponse HTTP
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = response
            
            # Mock du client HTTP
            mock_http_client = Mock()
            mock_http_client.get.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            ret_code = response.get("retCode", 0)
            
            if ret_code == 0:
                # Succès - ne doit pas lever d'exception
                result = self.fetcher.fetch_funding_map(self.base_url, self.category)
                assert result is not None
            else:
                # Erreur - doit lever une exception
                with pytest.raises(RuntimeError):
                    self.fetcher.fetch_funding_map(self.base_url, self.category)
    
    @patch('watchlist_data_fetcher.get_http_client')
    @patch('watchlist_data_fetcher.get_rate_limiter')
    def test_fetch_spreads_retcode_handling(self, mock_get_rate_limiter, mock_get_client):
        """Test de la gestion des retCode dans fetch_spreads."""
        # Mock du rate limiter
        mock_rate_limiter = Mock()
        mock_get_rate_limiter.return_value = mock_rate_limiter
        
        # Mock de la réponse HTTP avec erreur
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = get_invalid_api_key_response()
        
        # Mock du client HTTP
        mock_http_client = Mock()
        mock_http_client.get.return_value = mock_response
        mock_get_client.return_value = mock_http_client
        
        # Test que l'exception est levée
        with pytest.raises(RuntimeError) as exc_info:
            self.fetcher.fetch_spreads(self.base_url, ["BTCUSDT"], self.category)
        
        # Vérifier le message d'erreur
        assert "Erreur API Bybit" in str(exc_info.value)
        assert "retCode=10005" in str(exc_info.value)
    
    @patch('watchlist_data_fetcher.get_http_client')
    @patch('watchlist_data_fetcher.get_rate_limiter')
    def test_fetch_ticker_retcode_handling(self, mock_get_rate_limiter, mock_get_client):
        """Test de la gestion des retCode dans fetch_ticker."""
        # Mock du rate limiter
        mock_rate_limiter = Mock()
        mock_get_rate_limiter.return_value = mock_rate_limiter
        
        # Mock de la réponse HTTP avec erreur
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = get_permission_denied_response()
        
        # Mock du client HTTP
        mock_http_client = Mock()
        mock_http_client.get.return_value = mock_response
        mock_get_client.return_value = mock_http_client
        
        # Test que l'exception est levée
        with pytest.raises(RuntimeError) as exc_info:
            self.fetcher.fetch_ticker(self.base_url, "BTCUSDT", self.category)
        
        # Vérifier le message d'erreur
        assert "Erreur API Bybit" in str(exc_info.value)
        assert "retCode=10006" in str(exc_info.value)
