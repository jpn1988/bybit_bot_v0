"""Tests unitaires pour la gestion des retCode dans ws_private.py."""

import pytest
import json
from unittest.mock import Mock, patch
from ws_private import PrivateWSClient
from tests.mocks.bybit_responses import (
    get_invalid_api_key_response, get_permission_denied_response,
    get_unknown_error_response
)


class TestWSPrivateRetCode:
    """Tests pour la gestion des retCode dans ws_private.py."""
    
    def setup_method(self):
        """Configuration pour chaque test."""
        self.client = PrivateWSClient(
            testnet=True,
            api_key="test_api_key",
            api_secret="test_api_secret",
            channels=["order", "position"],
            logger=Mock()
        )
    
    def test_auth_success_retcode_0(self):
        """Test que retCode=0 pour l'authentification réussit."""
        # Mock de la réponse d'authentification réussie
        auth_response = {
            "op": "auth",
            "retCode": 0,
            "retMsg": "OK",
            "success": True
        }
        
        # Mock de la WebSocket
        mock_ws = Mock()
        self.client.ws = mock_ws
        
        # Simuler la réception du message d'authentification
        self.client.on_message(mock_ws, json.dumps(auth_response))
        
        # Vérifier que l'authentification a réussi
        assert self.client.status == "AUTHENTICATED"
    
    def test_auth_failure_retcode_10005(self):
        """Test que retCode=10005 pour l'authentification échoue."""
        # Mock de la réponse d'authentification échouée
        auth_response = {
            "op": "auth",
            "retCode": 10005,
            "retMsg": "Invalid API Key",
            "success": False
        }
        
        # Mock de la WebSocket
        mock_ws = Mock()
        self.client.ws = mock_ws
        
        # Mock du logger pour capturer les messages
        mock_logger = Mock()
        self.client.logger = mock_logger
        
        # Simuler la réception du message d'authentification
        self.client.on_message(mock_ws, json.dumps(auth_response))
        
        # Vérifier que l'authentification a échoué
        assert self.client.status == "AUTH_FAILED"
        
        # Vérifier que le message d'erreur a été loggé
        mock_logger.error.assert_called_once()
        error_call = mock_logger.error.call_args[0][0]
        assert "Échec authentification WS" in error_call
        assert "retCode=10005" in error_call
    
    def test_auth_failure_retcode_10006(self):
        """Test que retCode=10006 pour l'authentification échoue."""
        # Mock de la réponse d'authentification échouée
        auth_response = {
            "op": "auth",
            "retCode": 10006,
            "retMsg": "Permission denied",
            "success": False
        }
        
        # Mock de la WebSocket
        mock_ws = Mock()
        self.client.ws = mock_ws
        
        # Mock du logger pour capturer les messages
        mock_logger = Mock()
        self.client.logger = mock_logger
        
        # Simuler la réception du message d'authentification
        self.client.on_message(mock_ws, json.dumps(auth_response))
        
        # Vérifier que l'authentification a échoué
        assert self.client.status == "AUTH_FAILED"
        
        # Vérifier que le message d'erreur a été loggé
        mock_logger.error.assert_called_once()
        error_call = mock_logger.error.call_args[0][0]
        assert "Échec authentification WS" in error_call
        assert "retCode=10006" in error_call
    
    def test_auth_failure_retcode_99999(self):
        """Test que retCode=99999 pour l'authentification échoue."""
        # Mock de la réponse d'authentification échouée
        auth_response = {
            "op": "auth",
            "retCode": 99999,
            "retMsg": "Unknown error",
            "success": False
        }
        
        # Mock de la WebSocket
        mock_ws = Mock()
        self.client.ws = mock_ws
        
        # Mock du logger pour capturer les messages
        mock_logger = Mock()
        self.client.logger = mock_logger
        
        # Simuler la réception du message d'authentification
        self.client.on_message(mock_ws, json.dumps(auth_response))
        
        # Vérifier que l'authentification a échoué
        assert self.client.status == "AUTH_FAILED"
        
        # Vérifier que le message d'erreur a été loggé
        mock_logger.error.assert_called_once()
        error_call = mock_logger.error.call_args[0][0]
        assert "Échec authentification WS" in error_call
        assert "retCode=99999" in error_call
    
    def test_auth_failure_with_callback(self):
        """Test que le callback d'échec d'authentification est appelé."""
        # Mock de la réponse d'authentification échouée
        auth_response = {
            "op": "auth",
            "retCode": 10005,
            "retMsg": "Invalid API Key",
            "success": False
        }
        
        # Mock de la WebSocket
        mock_ws = Mock()
        self.client.ws = mock_ws
        
        # Mock du callback d'échec d'authentification
        mock_callback = Mock()
        self.client.on_auth_failure = mock_callback
        
        # Simuler la réception du message d'authentification
        self.client.on_message(mock_ws, json.dumps(auth_response))
        
        # Vérifier que le callback a été appelé avec les bons paramètres
        mock_callback.assert_called_once_with(10005, "Invalid API Key")
    
    def test_auth_success_with_callback(self):
        """Test que le callback de succès d'authentification est appelé."""
        # Mock de la réponse d'authentification réussie
        auth_response = {
            "op": "auth",
            "retCode": 0,
            "retMsg": "OK",
            "success": True
        }
        
        # Mock de la WebSocket
        mock_ws = Mock()
        self.client.ws = mock_ws
        
        # Mock du callback de succès d'authentification
        mock_callback = Mock()
        self.client.on_auth_success = mock_callback
        
        # Simuler la réception du message d'authentification
        self.client.on_message(mock_ws, json.dumps(auth_response))
        
        # Vérifier que le callback a été appelé
        mock_callback.assert_called_once()
    
    def test_auth_failure_closes_websocket(self):
        """Test que l'échec d'authentification ferme la WebSocket."""
        # Mock de la réponse d'authentification échouée
        auth_response = {
            "op": "auth",
            "retCode": 10005,
            "retMsg": "Invalid API Key",
            "success": False
        }
        
        # Mock de la WebSocket
        mock_ws = Mock()
        self.client.ws = mock_ws
        
        # Simuler la réception du message d'authentification
        self.client.on_message(mock_ws, json.dumps(auth_response))
        
        # Vérifier que la WebSocket a été fermée
        mock_ws.close.assert_called_once()
    
    def test_auth_success_does_not_close_websocket(self):
        """Test que le succès d'authentification ne ferme pas la WebSocket."""
        # Mock de la réponse d'authentification réussie
        auth_response = {
            "op": "auth",
            "retCode": 0,
            "retMsg": "OK",
            "success": True
        }
        
        # Mock de la WebSocket
        mock_ws = Mock()
        self.client.ws = mock_ws
        
        # Simuler la réception du message d'authentification
        self.client.on_message(mock_ws, json.dumps(auth_response))
        
        # Vérifier que la WebSocket n'a pas été fermée
        mock_ws.close.assert_not_called()
    
    def test_auth_failure_with_exception_in_callback(self):
        """Test que les exceptions dans le callback d'échec sont gérées."""
        # Mock de la réponse d'authentification échouée
        auth_response = {
            "op": "auth",
            "retCode": 10005,
            "retMsg": "Invalid API Key",
            "success": False
        }
        
        # Mock de la WebSocket
        mock_ws = Mock()
        self.client.ws = mock_ws
        
        # Mock du callback d'échec qui lève une exception
        mock_callback = Mock(side_effect=Exception("Callback error"))
        self.client.on_auth_failure = mock_callback
        
        # Simuler la réception du message d'authentification
        # Ne doit pas lever d'exception malgré l'erreur dans le callback
        self.client.on_message(mock_ws, json.dumps(auth_response))
        
        # Vérifier que l'authentification a quand même échoué
        assert self.client.status == "AUTH_FAILED"
    
    def test_auth_success_with_exception_in_callback(self):
        """Test que les exceptions dans le callback de succès sont gérées."""
        # Mock de la réponse d'authentification réussie
        auth_response = {
            "op": "auth",
            "retCode": 0,
            "retMsg": "OK",
            "success": True
        }
        
        # Mock de la WebSocket
        mock_ws = Mock()
        self.client.ws = mock_ws
        
        # Mock du callback de succès qui lève une exception
        mock_callback = Mock(side_effect=Exception("Callback error"))
        self.client.on_auth_success = mock_callback
        
        # Simuler la réception du message d'authentification
        # Ne doit pas lever d'exception malgré l'erreur dans le callback
        self.client.on_message(mock_ws, json.dumps(auth_response))
        
        # Vérifier que l'authentification a quand même réussi
        assert self.client.status == "AUTHENTICATED"
    
    def test_auth_failure_with_exception_in_logger(self):
        """Test que les exceptions dans le logger sont gérées."""
        # Mock de la réponse d'authentification échouée
        auth_response = {
            "op": "auth",
            "retCode": 10005,
            "retMsg": "Invalid API Key",
            "success": False
        }
        
        # Mock de la WebSocket
        mock_ws = Mock()
        self.client.ws = mock_ws
        
        # Mock du logger qui lève une exception
        mock_logger = Mock()
        mock_logger.error.side_effect = Exception("Logger error")
        self.client.logger = mock_logger
        
        # Simuler la réception du message d'authentification
        # Ne doit pas lever d'exception malgré l'erreur dans le logger
        self.client.on_message(mock_ws, json.dumps(auth_response))
        
        # Vérifier que l'authentification a quand même échoué
        assert self.client.status == "AUTH_FAILED"
