"""Tests complets pour la gestion des retCode dans tout le projet."""

import pytest
import json
import httpx
from unittest.mock import Mock, patch
from bybit_client import BybitClient
from watchlist_data_fetcher import WatchlistDataFetcher
from instruments import fetch_perpetual_instruments
from ws_private import PrivateWSClient
from tests.mocks.bybit_responses import (
    get_success_response, get_wallet_balance_success,
    get_invalid_api_key_response, get_permission_denied_response,
    get_rate_limit_response, get_invalid_timestamp_response,
    get_ip_not_whitelisted_response, get_invalid_params_response,
    get_insufficient_balance_response, get_unknown_error_response,
    get_all_error_responses, get_success_responses
)


class TestRetCodeComprehensive:
    """Tests complets pour la gestion des retCode dans tout le projet."""
    
    def setup_method(self):
        """Configuration pour chaque test."""
        self.base_url = "https://api-testnet.bybit.com"
        self.category = "linear"
        
        # Initialiser les clients
        self.bybit_client = BybitClient(
            testnet=True,
            timeout=10,
            api_key="test_api_key",
            api_secret="test_api_secret"
        )
        
        self.data_fetcher = WatchlistDataFetcher()
        
        self.ws_client = PrivateWSClient(
            testnet=True,
            api_key="test_api_key",
            api_secret="test_api_secret",
            channels=["order", "position"],
            logger=Mock()
        )
    
    def test_success_scenarios_all_modules(self):
        """Test que tous les modules gèrent correctement retCode=0."""
        success_responses = get_success_responses()
        
        for response in success_responses:
            # Test BybitClient
            with patch('bybit_client.get_http_client') as mock_get_client:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = response
                
                mock_http_client = Mock()
                mock_http_client.get.return_value = mock_response
                mock_get_client.return_value = mock_http_client
                
                # Ne doit pas lever d'exception
                result = self.bybit_client._get_private("/v5/account/wallet-balance")
                assert result is not None
            
            # Test WatchlistDataFetcher
            with patch('watchlist_data_fetcher.get_http_client') as mock_get_client, \
                 patch('watchlist_data_fetcher.get_rate_limiter') as mock_get_rate_limiter:
                
                mock_rate_limiter = Mock()
                mock_get_rate_limiter.return_value = mock_rate_limiter
                
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = response
                
                mock_http_client = Mock()
                mock_http_client.get.return_value = mock_response
                mock_get_client.return_value = mock_http_client
                
                # Ne doit pas lever d'exception
                result = self.data_fetcher.fetch_funding_map(self.base_url, self.category)
                assert result is not None
            
            # Test instruments
            with patch('instruments.get_http_client') as mock_get_client:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = response
                
                mock_http_client = Mock()
                mock_http_client.get.return_value = mock_response
                mock_get_client.return_value = mock_http_client
                
                # Ne doit pas lever d'exception
                result = fetch_perpetual_instruments(self.base_url, self.category)
                assert result is not None
    
    def test_auth_error_scenarios_all_modules(self):
        """Test que tous les modules gèrent correctement les erreurs d'authentification."""
        auth_error_responses = [
            get_invalid_api_key_response(),
            get_permission_denied_response()
        ]
        
        for response in auth_error_responses:
            ret_code = response.get("retCode")
            
            # Test BybitClient
            with patch('bybit_client.get_http_client') as mock_get_client:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = response
                
                mock_http_client = Mock()
                mock_http_client.get.return_value = mock_response
                mock_get_client.return_value = mock_http_client
                
                # Doit lever une exception
                with pytest.raises(RuntimeError) as exc_info:
                    self.bybit_client._get_private("/v5/account/wallet-balance")
                
                assert "Authentification échouée" in str(exc_info.value)
            
            # Test WatchlistDataFetcher
            with patch('watchlist_data_fetcher.get_http_client') as mock_get_client, \
                 patch('watchlist_data_fetcher.get_rate_limiter') as mock_get_rate_limiter:
                
                mock_rate_limiter = Mock()
                mock_get_rate_limiter.return_value = mock_rate_limiter
                
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = response
                
                mock_http_client = Mock()
                mock_http_client.get.return_value = mock_response
                mock_get_client.return_value = mock_http_client
                
                # Doit lever une exception
                with pytest.raises(RuntimeError) as exc_info:
                    self.data_fetcher.fetch_funding_map(self.base_url, self.category)
                
                assert "Erreur API Bybit" in str(exc_info.value)
                assert f"retCode={ret_code}" in str(exc_info.value)
            
            # Test instruments
            with patch('instruments.get_http_client') as mock_get_client:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = response
                
                mock_http_client = Mock()
                mock_http_client.get.return_value = mock_response
                mock_get_client.return_value = mock_http_client
                
                # Doit lever une exception
                with pytest.raises(RuntimeError) as exc_info:
                    fetch_perpetual_instruments(self.base_url, self.category)
                
                assert "Erreur API Bybit" in str(exc_info.value)
                assert f"retCode={ret_code}" in str(exc_info.value)
    
    def test_websocket_auth_scenarios(self):
        """Test que la WebSocket gère correctement les scénarios d'authentification."""
        # Test succès d'authentification
        auth_success = {
            "op": "auth",
            "retCode": 0,
            "retMsg": "OK",
            "success": True
        }
        
        mock_ws = Mock()
        self.ws_client.ws = mock_ws
        
        # Ne doit pas lever d'exception
        self.ws_client.on_message(mock_ws, json.dumps(auth_success))
        assert self.ws_client.status == "AUTHENTICATED"
        
        # Test échec d'authentification
        auth_failure = {
            "op": "auth",
            "retCode": 10005,
            "retMsg": "Invalid API Key",
            "success": False
        }
        
        # Reset du statut
        self.ws_client.status = "CONNECTING"
        
        # Doit fermer la WebSocket et changer le statut
        self.ws_client.on_message(mock_ws, json.dumps(auth_failure))
        assert self.ws_client.status == "AUTH_FAILED"
        mock_ws.close.assert_called()
    
    def test_rate_limit_scenarios(self):
        """Test que tous les modules gèrent correctement les erreurs de rate limit."""
        rate_limit_response = get_rate_limit_response()
        
        # Test BybitClient avec rate limit
        with patch('bybit_client.get_http_client') as mock_get_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = rate_limit_response
            mock_response.headers = {}  # Pas de Retry-After
            
            mock_http_client = Mock()
            mock_http_client.get.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            # Doit lever une exception après les tentatives
            with pytest.raises(RuntimeError) as exc_info:
                self.bybit_client._get_private("/v5/account/wallet-balance")
            
            assert "Limite de requêtes atteinte" in str(exc_info.value)
        
        # Test WatchlistDataFetcher avec rate limit
        with patch('watchlist_data_fetcher.get_http_client') as mock_get_client, \
             patch('watchlist_data_fetcher.get_rate_limiter') as mock_get_rate_limiter:
            
            mock_rate_limiter = Mock()
            mock_get_rate_limiter.return_value = mock_rate_limiter
            
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = rate_limit_response
            
            mock_http_client = Mock()
            mock_http_client.get.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            # Doit lever une exception
            with pytest.raises(RuntimeError) as exc_info:
                self.data_fetcher.fetch_funding_map(self.base_url, self.category)
            
            assert "Erreur API Bybit" in str(exc_info.value)
            assert "retCode=10016" in str(exc_info.value)
    
    def test_unknown_error_scenarios(self):
        """Test que tous les modules gèrent correctement les erreurs inconnues."""
        unknown_error_response = get_unknown_error_response()
        
        # Test BybitClient avec erreur inconnue
        with patch('bybit_client.get_http_client') as mock_get_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = unknown_error_response
            
            mock_http_client = Mock()
            mock_http_client.get.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            # Doit lever une exception générique
            with pytest.raises(RuntimeError) as exc_info:
                self.bybit_client._get_private("/v5/account/wallet-balance")
            
            assert "Erreur API Bybit" in str(exc_info.value)
            assert "retCode=99999" in str(exc_info.value)
        
        # Test WatchlistDataFetcher avec erreur inconnue
        with patch('watchlist_data_fetcher.get_http_client') as mock_get_client, \
             patch('watchlist_data_fetcher.get_rate_limiter') as mock_get_rate_limiter:
            
            mock_rate_limiter = Mock()
            mock_get_rate_limiter.return_value = mock_rate_limiter
            
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = unknown_error_response
            
            mock_http_client = Mock()
            mock_http_client.get.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            # Doit lever une exception générique
            with pytest.raises(RuntimeError) as exc_info:
                self.data_fetcher.fetch_funding_map(self.base_url, self.category)
            
            assert "Erreur API Bybit" in str(exc_info.value)
            assert "retCode=99999" in str(exc_info.value)
    
    def test_http_error_scenarios(self):
        """Test que tous les modules gèrent correctement les erreurs HTTP."""
        # Test BybitClient avec erreur HTTP 400
        with patch('bybit_client.get_http_client') as mock_get_client:
            mock_response = Mock()
            mock_response.status_code = 400
            mock_response.text = "Bad Request"
            
            mock_http_client = Mock()
            mock_http_client.get.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            # Doit lever une exception HTTP
            with pytest.raises(RuntimeError) as exc_info:
                self.bybit_client._get_private("/v5/account/wallet-balance")
            
            assert "Erreur HTTP Bybit" in str(exc_info.value)
            assert "status=400" in str(exc_info.value)
        
        # Test WatchlistDataFetcher avec erreur HTTP 500
        with patch('watchlist_data_fetcher.get_http_client') as mock_get_client, \
             patch('watchlist_data_fetcher.get_rate_limiter') as mock_get_rate_limiter:
            
            mock_rate_limiter = Mock()
            mock_get_rate_limiter.return_value = mock_rate_limiter
            
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            
            mock_http_client = Mock()
            mock_http_client.get.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            # Doit lever une exception HTTP
            with pytest.raises(RuntimeError) as exc_info:
                self.data_fetcher.fetch_funding_map(self.base_url, self.category)
            
            assert "Erreur HTTP Bybit" in str(exc_info.value)
            assert "status=500" in str(exc_info.value)
    
    def test_network_error_scenarios(self):
        """Test que tous les modules gèrent correctement les erreurs réseau."""
        # Test BybitClient avec erreur réseau
        with patch('bybit_client.get_http_client') as mock_get_client:
            mock_http_client = Mock()
            mock_http_client.get.side_effect = httpx.RequestError("Network error")
            mock_get_client.return_value = mock_http_client
            
            # Doit lever une exception réseau
            with pytest.raises(httpx.RequestError):
                self.bybit_client._get_private("/v5/account/wallet-balance")
        
        # Test instruments avec erreur réseau
        with patch('instruments.get_http_client') as mock_get_client:
            mock_http_client = Mock()
            mock_http_client.get.side_effect = httpx.RequestError("Network error")
            mock_get_client.return_value = mock_http_client
            
            # Doit lever une exception réseau
            with pytest.raises(httpx.RequestError):
                fetch_perpetual_instruments(self.base_url, self.category)
    
    def test_timeout_error_scenarios(self):
        """Test que tous les modules gèrent correctement les erreurs de timeout."""
        # Test BybitClient avec timeout
        with patch('bybit_client.get_http_client') as mock_get_client:
            mock_http_client = Mock()
            mock_http_client.get.side_effect = httpx.TimeoutException("Request timeout")
            mock_get_client.return_value = mock_http_client
            
            # Doit lever une exception de timeout
            with pytest.raises(httpx.TimeoutException):
                self.bybit_client._get_private("/v5/account/wallet-balance")
        
        # Test instruments avec timeout
        with patch('instruments.get_http_client') as mock_get_client:
            mock_http_client = Mock()
            mock_http_client.get.side_effect = httpx.TimeoutException("Request timeout")
            mock_get_client.return_value = mock_http_client
            
            # Doit lever une exception de timeout
            with pytest.raises(httpx.TimeoutException):
                fetch_perpetual_instruments(self.base_url, self.category)
    
    def test_json_parsing_error_scenarios(self):
        """Test que tous les modules gèrent correctement les erreurs de parsing JSON."""
        # Test BybitClient avec JSON invalide
        with patch('bybit_client.get_http_client') as mock_get_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.side_effect = ValueError("Invalid JSON")
            
            mock_http_client = Mock()
            mock_http_client.get.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            # Doit lever une exception de parsing
            with pytest.raises(ValueError):
                self.bybit_client._get_private("/v5/account/wallet-balance")
        
        # Test instruments avec JSON invalide
        with patch('instruments.get_http_client') as mock_get_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.side_effect = ValueError("Invalid JSON")
            
            mock_http_client = Mock()
            mock_http_client.get.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            # Doit lever une exception de parsing
            with pytest.raises(ValueError):
                fetch_perpetual_instruments(self.base_url, self.category)
    
    def test_all_error_codes_comprehensive(self):
        """Test que tous les codes d'erreur sont gérés correctement."""
        error_responses = get_all_error_responses()
        
        for response in error_responses:
            ret_code = response.get("retCode", 0)
            
            if ret_code == 0:
                # Succès - ne doit pas lever d'exception
                with patch('bybit_client.get_http_client') as mock_get_client:
                    mock_response = Mock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = response
                    
                    mock_http_client = Mock()
                    mock_http_client.get.return_value = mock_response
                    mock_get_client.return_value = mock_http_client
                    
                    result = self.bybit_client._get_private("/v5/account/wallet-balance")
                    assert result is not None
            else:
                # Erreur - doit lever une exception
                with patch('bybit_client.get_http_client') as mock_get_client:
                    mock_response = Mock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = response
                    mock_response.headers = {}  # Pas de Retry-After
                    
                    mock_http_client = Mock()
                    mock_http_client.get.return_value = mock_response
                    mock_get_client.return_value = mock_http_client
                    
                    with pytest.raises(RuntimeError) as exc_info:
                        self.bybit_client._get_private("/v5/account/wallet-balance")
                    
                    # Vérifier que le message d'erreur contient le retCode
                    assert f"retCode={ret_code}" in str(exc_info.value)
    
    def test_error_message_consistency(self):
        """Test que les messages d'erreur sont cohérents entre les modules."""
        error_response = get_invalid_api_key_response()
        
        # Test BybitClient
        with patch('bybit_client.get_http_client') as mock_get_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = error_response
            
            mock_http_client = Mock()
            mock_http_client.get.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            with pytest.raises(RuntimeError) as exc_info:
                self.bybit_client._get_private("/v5/account/wallet-balance")
            
            bybit_error = str(exc_info.value)
        
        # Test WatchlistDataFetcher
        with patch('watchlist_data_fetcher.get_http_client') as mock_get_client, \
             patch('watchlist_data_fetcher.get_rate_limiter') as mock_get_rate_limiter:
            
            mock_rate_limiter = Mock()
            mock_get_rate_limiter.return_value = mock_rate_limiter
            
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = error_response
            
            mock_http_client = Mock()
            mock_http_client.get.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            with pytest.raises(RuntimeError) as exc_info:
                self.data_fetcher.fetch_funding_map(self.base_url, self.category)
            
            fetcher_error = str(exc_info.value)
        
        # Vérifier que les messages d'erreur sont cohérents
        assert "retCode=10005" in bybit_error
        assert "retCode=10005" in fetcher_error
        assert "Invalid API Key" in bybit_error
        assert "Invalid API Key" in fetcher_error
