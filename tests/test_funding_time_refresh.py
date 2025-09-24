"""Tests pour la mise à jour du funding_time après passage d'échéance."""

import pytest
import time
import datetime
from unittest.mock import Mock, patch
from watchlist_filters import WatchlistFilters


class TestFundingTimeRefresh:
    """Tests pour la mise à jour du funding_time."""
    
    def test_funding_time_after_deadline_passed(self):
        """Test que le funding_time se met à jour après passage d'échéance."""
        filters = WatchlistFilters()
        
        # Simuler un timestamp de funding qui vient de passer
        now = datetime.datetime.now(datetime.timezone.utc)
        past_funding_time = now - datetime.timedelta(minutes=5)  # Funding passé il y a 5 minutes
        past_timestamp_ms = int(past_funding_time.timestamp() * 1000)
        
        # Tester le calcul
        result = filters.calculate_funding_time_remaining(past_timestamp_ms)
        
        # Vérifier que le résultat n'est pas "-" et contient des heures
        assert result != "-"
        assert "h" in result  # Devrait contenir des heures
        
        # Vérifier que le temps restant est proche de 8h - 5min = 7h 55min
        # On accepte une marge d'erreur de 1 minute
        if "h" in result and "m" in result:
            hours_part = result.split("h")[0]
            hours = int(hours_part)
            assert 7 <= hours <= 8  # Devrait être autour de 7-8 heures
    
    def test_funding_time_multiple_deadlines_passed(self):
        """Test avec plusieurs échéances passées."""
        filters = WatchlistFilters()
        
        # Simuler un timestamp très ancien (plusieurs échéances passées)
        now = datetime.datetime.now(datetime.timezone.utc)
        very_old_funding_time = now - datetime.timedelta(hours=25)  # 25h dans le passé
        old_timestamp_ms = int(very_old_funding_time.timestamp() * 1000)
        
        # Tester le calcul
        result = filters.calculate_funding_time_remaining(old_timestamp_ms)
        
        # Vérifier que le résultat n'est pas "-"
        assert result != "-"
        assert "h" in result  # Devrait contenir des heures
        
        # Vérifier que le temps restant est raisonnable (moins de 8h)
        if "h" in result:
            hours_part = result.split("h")[0]
            hours = int(hours_part)
            assert 0 <= hours < 8  # Devrait être moins de 8h
    
    def test_funding_time_future_deadline(self):
        """Test avec une échéance future (cas normal)."""
        filters = WatchlistFilters()
        
        # Simuler un timestamp de funding futur
        now = datetime.datetime.now(datetime.timezone.utc)
        future_funding_time = now + datetime.timedelta(hours=2, minutes=30)  # Dans 2h30
        future_timestamp_ms = int(future_funding_time.timestamp() * 1000)
        
        # Tester le calcul
        result = filters.calculate_funding_time_remaining(future_timestamp_ms)
        
        # Vérifier que le résultat est correct
        assert result != "-"
        assert "h" in result  # Devrait contenir des heures
        assert "m" in result  # Devrait contenir des minutes
        
        # Vérifier que le temps est proche de 2h30
        if "h" in result and "m" in result:
            hours_part = result.split("h")[0]
            minutes_part = result.split("h")[1].split("m")[0].strip()
            hours = int(hours_part)
            minutes = int(minutes_part)
            assert 2 <= hours <= 3  # Devrait être autour de 2-3 heures
            assert 25 <= minutes <= 35  # Devrait être autour de 25-35 minutes
    
    def test_funding_time_edge_case_exactly_now(self):
        """Test avec une échéance exactement maintenant."""
        filters = WatchlistFilters()
        
        # Simuler un timestamp exactement maintenant
        now = datetime.datetime.now(datetime.timezone.utc)
        now_timestamp_ms = int(now.timestamp() * 1000)
        
        # Tester le calcul
        result = filters.calculate_funding_time_remaining(now_timestamp_ms)
        
        # Vérifier que le résultat n'est pas "-" (devrait calculer le prochain)
        assert result != "-"
        assert "h" in result  # Devrait contenir des heures
        
        # Vérifier que le temps restant est proche de 8h
        if "h" in result:
            hours_part = result.split("h")[0]
            hours = int(hours_part)
            assert 7 <= hours <= 8  # Devrait être autour de 7-8 heures
    
    def test_funding_time_invalid_input(self):
        """Test avec des entrées invalides."""
        filters = WatchlistFilters()
        
        # Test avec None
        result = filters.calculate_funding_time_remaining(None)
        assert result == "-"
        
        # Test avec chaîne vide
        result = filters.calculate_funding_time_remaining("")
        assert result == "-"
        
        # Test avec 0
        result = filters.calculate_funding_time_remaining(0)
        assert result == "-"
    
    def test_funding_time_string_formats(self):
        """Test avec différents formats de chaînes."""
        filters = WatchlistFilters()
        
        # Simuler un timestamp futur
        now = datetime.datetime.now(datetime.timezone.utc)
        future_funding_time = now + datetime.timedelta(hours=1, minutes=15)
        future_timestamp_ms = int(future_funding_time.timestamp() * 1000)
        
        # Test avec timestamp numérique
        result1 = filters.calculate_funding_time_remaining(future_timestamp_ms)
        assert result1 != "-"
        assert "h" in result1
        
        # Test avec timestamp en chaîne
        result2 = filters.calculate_funding_time_remaining(str(future_timestamp_ms))
        assert result2 != "-"
        assert "h" in result2
        
        # Les deux résultats devraient être similaires
        assert result1 == result2
    
    def test_funding_time_iso_format(self):
        """Test avec format ISO."""
        filters = WatchlistFilters()
        
        # Simuler un timestamp futur en format ISO
        now = datetime.datetime.now(datetime.timezone.utc)
        future_funding_time = now + datetime.timedelta(hours=3, minutes=45)
        iso_format = future_funding_time.isoformat()
        
        # Tester le calcul
        result = filters.calculate_funding_time_remaining(iso_format)
        
        # Vérifier que le résultat est correct
        assert result != "-"
        assert "h" in result  # Devrait contenir des heures
        assert "m" in result  # Devrait contenir des minutes
        
        # Vérifier que le temps est proche de 3h45
        if "h" in result and "m" in result:
            hours_part = result.split("h")[0]
            minutes_part = result.split("h")[1].split("m")[0].strip()
            hours = int(hours_part)
            minutes = int(minutes_part)
            assert 3 <= hours <= 4  # Devrait être autour de 3-4 heures
            assert 40 <= minutes <= 50  # Devrait être autour de 40-50 minutes
    
    def test_funding_time_minutes_calculation(self):
        """Test de la méthode calculate_funding_minutes_remaining."""
        filters = WatchlistFilters()
        
        # Simuler un timestamp de funding passé
        now = datetime.datetime.now(datetime.timezone.utc)
        past_funding_time = now - datetime.timedelta(minutes=10)  # Funding passé il y a 10 minutes
        past_timestamp_ms = int(past_funding_time.timestamp() * 1000)
        
        # Tester le calcul en minutes
        result = filters.calculate_funding_minutes_remaining(past_timestamp_ms)
        
        # Vérifier que le résultat n'est pas None
        assert result is not None
        assert isinstance(result, float)
        
        # Vérifier que le temps restant est proche de 8h - 10min = 470 minutes
        assert 460 <= result <= 480  # Devrait être autour de 470 minutes
    
    def test_funding_time_consistency_between_methods(self):
        """Test de cohérence entre les deux méthodes de calcul."""
        filters = WatchlistFilters()
        
        # Simuler un timestamp de funding passé
        now = datetime.datetime.now(datetime.timezone.utc)
        past_funding_time = now - datetime.timedelta(minutes=15)  # Funding passé il y a 15 minutes
        past_timestamp_ms = int(past_funding_time.timestamp() * 1000)
        
        # Calculer avec les deux méthodes
        result_string = filters.calculate_funding_time_remaining(past_timestamp_ms)
        result_minutes = filters.calculate_funding_minutes_remaining(past_timestamp_ms)
        
        # Vérifier que les deux méthodes donnent des résultats cohérents
        assert result_string != "-"
        assert result_minutes is not None
        
        # Convertir le résultat string en minutes pour comparaison
        if "h" in result_string and "m" in result_string:
            hours_part = result_string.split("h")[0]
            minutes_part = result_string.split("h")[1].split("m")[0].strip()
            hours = int(hours_part)
            minutes = int(minutes_part)
            total_minutes_string = hours * 60 + minutes
            
            # Vérifier que la différence est inférieure à 1 minute
            assert abs(total_minutes_string - result_minutes) < 1.0
