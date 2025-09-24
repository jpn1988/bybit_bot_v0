"""Tests de stabilité globale pour les accès concurrents."""

import pytest
import threading
import time
import random
from price_store import update, get_snapshot, purge_expired
from metrics import (
    MetricsCollector, 
    record_api_call, 
    record_filter_result, 
    record_ws_connection, 
    record_ws_error, 
    get_metrics_summary, 
    reset_metrics
)


class TestConcurrentStability:
    """Tests de stabilité globale pour les accès concurrents."""
    
    def test_price_store_stability_repeated(self):
        """Test de stabilité répété du price_store."""
        num_iterations = 50
        num_threads = 8
        operations_per_thread = 100
        
        for iteration in range(num_iterations):
            # Nettoyer l'état initial
            snapshot = get_snapshot()
            for symbol in list(snapshot.keys()):
                purge_expired(ttl_seconds=0)  # Purger tout
            
            def stability_worker(thread_id):
                """Worker de stabilité pour price_store."""
                for i in range(operations_per_thread):
                    try:
                        symbol = f"SYMBOL_{thread_id % 5}"
                        operation = i % 3
                        
                        if operation == 0:  # Écriture
                            mark_price = 1000.0 + thread_id * 100 + i
                            last_price = mark_price + random.uniform(-10, 10)
                            timestamp = time.time()
                            update(symbol, mark_price, last_price, timestamp)
                        
                        elif operation == 1:  # Lecture
                            snapshot = get_snapshot()
                            assert isinstance(snapshot, dict)
                        
                        else:  # Purge
                            purged_count = purge_expired(ttl_seconds=1)
                            assert isinstance(purged_count, int)
                            assert purged_count >= 0
                        
                        time.sleep(0.001)
                        
                    except Exception as e:
                        print(f"Iteration {iteration}, Thread {thread_id}, Opération {i}: {e}")
                        raise
            
            # Créer et démarrer les threads
            threads = []
            for i in range(num_threads):
                thread = threading.Thread(target=stability_worker, args=(i,))
                threads.append(thread)
                thread.start()
            
            # Attendre que tous les threads se terminent
            for thread in threads:
                thread.join()
            
            # Vérifier la cohérence finale
            snapshot = get_snapshot()
            assert isinstance(snapshot, dict)
            
            # Vérifier que tous les symboles présents ont des données cohérentes
            for symbol, price_data in snapshot.items():
                assert "mark_price" in price_data
                assert "last_price" in price_data
                assert "timestamp" in price_data
                assert isinstance(price_data["mark_price"], (int, float))
                assert isinstance(price_data["last_price"], (int, float))
                assert isinstance(price_data["timestamp"], (int, float))
    
    def test_metrics_stability_repeated(self):
        """Test de stabilité répété des métriques."""
        num_iterations = 50
        num_threads = 10
        operations_per_thread = 150
        
        for iteration in range(num_iterations):
            # Créer un nouveau collecteur pour chaque itération
            collector = MetricsCollector()
            
            def stability_worker(thread_id):
                """Worker de stabilité pour metrics."""
                for i in range(operations_per_thread):
                    try:
                        operation = i % 5
                        
                        if operation == 0:  # Appel API
                            latency = random.uniform(0.1, 1.0)
                            success = random.choice([True, False])
                            collector.record_api_call(latency, success)
                        
                        elif operation == 1:  # Résultat de filtre
                            filter_name = f"stability_filter_{thread_id % 3}"
                            kept = random.randint(1, 20)
                            rejected = random.randint(0, 10)
                            collector.record_filter_result(filter_name, kept, rejected)
                        
                        elif operation == 2:  # Connexion WS
                            collector.record_ws_connection(connected=True)
                        
                        elif operation == 3:  # Reconnexion WS
                            collector.record_ws_connection(connected=False)
                        
                        else:  # Lecture des métriques
                            summary = collector.get_metrics_summary()
                            assert isinstance(summary, dict)
                            assert "api_calls_total" in summary
                            assert "pairs_kept_total" in summary
                            assert "ws_connections" in summary
                        
                        time.sleep(0.001)
                        
                    except Exception as e:
                        print(f"Iteration {iteration}, Thread {thread_id}, Opération {i}: {e}")
                        raise
            
            # Créer et démarrer les threads
            threads = []
            for i in range(num_threads):
                thread = threading.Thread(target=stability_worker, args=(i,))
                threads.append(thread)
                thread.start()
            
            # Attendre que tous les threads se terminent
            for thread in threads:
                thread.join()
            
            # Vérifier la cohérence finale
            summary = collector.get_metrics_summary()
            assert isinstance(summary, dict)
            
            # Vérifier que toutes les métriques sont cohérentes
            assert summary["api_calls_total"] >= 0
            assert summary["api_errors_total"] >= 0
            assert summary["api_errors_total"] <= summary["api_calls_total"]
            assert summary["pairs_kept_total"] >= 0
            assert summary["pairs_rejected_total"] >= 0
            assert summary["ws_connections"] >= 0
            assert summary["ws_reconnects"] >= 0
            assert summary["ws_errors"] >= 0
            assert 0 <= summary["api_error_rate_percent"] <= 100
            assert 0 <= summary["filter_success_rate_percent"] <= 100
    
    def test_global_metrics_stability_repeated(self):
        """Test de stabilité répété des métriques globales."""
        num_iterations = 30
        num_threads = 12
        operations_per_thread = 200
        
        for iteration in range(num_iterations):
            # Remettre à zéro les métriques globales
            reset_metrics()
            
            def global_stability_worker(thread_id):
                """Worker de stabilité pour les métriques globales."""
                for i in range(operations_per_thread):
                    try:
                        operation = i % 4
                        
                        if operation == 0:  # Appel API global
                            latency = random.uniform(0.1, 1.0)
                            success = random.choice([True, False])
                            record_api_call(latency, success)
                        
                        elif operation == 1:  # Résultat de filtre global
                            filter_name = f"global_stability_{thread_id % 4}"
                            kept = random.randint(1, 15)
                            rejected = random.randint(0, 8)
                            record_filter_result(filter_name, kept, rejected)
                        
                        elif operation == 2:  # Connexion WS globale
                            record_ws_connection(connected=True)
                        
                        else:  # Erreur WS globale
                            record_ws_error()
                        
                        time.sleep(0.001)
                        
                    except Exception as e:
                        print(f"Iteration {iteration}, Thread {thread_id}, Opération {i}: {e}")
                        raise
            
            # Créer et démarrer les threads
            threads = []
            for i in range(num_threads):
                thread = threading.Thread(target=global_stability_worker, args=(i,))
                threads.append(thread)
                thread.start()
            
            # Attendre que tous les threads se terminent
            for thread in threads:
                thread.join()
            
            # Vérifier la cohérence finale
            summary = get_metrics_summary()
            assert isinstance(summary, dict)
            
            # Vérifier que toutes les métriques sont cohérentes
            assert summary["api_calls_total"] >= 0
            assert summary["api_errors_total"] >= 0
            assert summary["api_errors_total"] <= summary["api_calls_total"]
            assert summary["pairs_kept_total"] >= 0
            assert summary["pairs_rejected_total"] >= 0
            assert summary["ws_connections"] >= 0
            assert summary["ws_reconnects"] >= 0
            assert summary["ws_errors"] >= 0
            assert 0 <= summary["api_error_rate_percent"] <= 100
            assert 0 <= summary["filter_success_rate_percent"] <= 100
    
    def test_mixed_modules_stability_repeated(self):
        """Test de stabilité répété avec les deux modules ensemble."""
        num_iterations = 25
        num_threads = 15
        operations_per_thread = 100
        
        for iteration in range(num_iterations):
            # Nettoyer l'état initial
            reset_metrics()
            snapshot = get_snapshot()
            for symbol in list(snapshot.keys()):
                purge_expired(ttl_seconds=0)  # Purger tout
            
            def mixed_stability_worker(thread_id):
                """Worker de stabilité pour les deux modules."""
                for i in range(operations_per_thread):
                    try:
                        operation = i % 7
                        
                        if operation == 0:  # Écriture price_store
                            symbol = f"MIXED_{thread_id % 6}"
                            mark_price = 1000.0 + thread_id * 100 + i
                            last_price = mark_price + random.uniform(-10, 10)
                            timestamp = time.time()
                            update(symbol, mark_price, last_price, timestamp)
                        
                        elif operation == 1:  # Lecture price_store
                            snapshot = get_snapshot()
                            assert isinstance(snapshot, dict)
                        
                        elif operation == 2:  # Purge price_store
                            purged_count = purge_expired(ttl_seconds=1)
                            assert isinstance(purged_count, int)
                            assert purged_count >= 0
                        
                        elif operation == 3:  # Appel API metrics
                            latency = random.uniform(0.1, 1.0)
                            success = random.choice([True, False])
                            record_api_call(latency, success)
                        
                        elif operation == 4:  # Résultat de filtre metrics
                            filter_name = f"mixed_filter_{thread_id % 3}"
                            kept = random.randint(1, 12)
                            rejected = random.randint(0, 6)
                            record_filter_result(filter_name, kept, rejected)
                        
                        elif operation == 5:  # Connexion WS metrics
                            record_ws_connection(connected=True)
                        
                        else:  # Lecture des métriques
                            summary = get_metrics_summary()
                            assert isinstance(summary, dict)
                            assert "api_calls_total" in summary
                            assert "pairs_kept_total" in summary
                            assert "ws_connections" in summary
                        
                        time.sleep(0.001)
                        
                    except Exception as e:
                        print(f"Iteration {iteration}, Thread {thread_id}, Opération {i}: {e}")
                        raise
            
            # Créer et démarrer les threads
            threads = []
            for i in range(num_threads):
                thread = threading.Thread(target=mixed_stability_worker, args=(i,))
                threads.append(thread)
                thread.start()
            
            # Attendre que tous les threads se terminent
            for thread in threads:
                thread.join()
            
            # Vérifier la cohérence finale des deux modules
            
            # Vérifier price_store
            snapshot = get_snapshot()
            assert isinstance(snapshot, dict)
            for symbol, price_data in snapshot.items():
                assert "mark_price" in price_data
                assert "last_price" in price_data
                assert "timestamp" in price_data
                assert isinstance(price_data["mark_price"], (int, float))
                assert isinstance(price_data["last_price"], (int, float))
                assert isinstance(price_data["timestamp"], (int, float))
            
            # Vérifier metrics
            summary = get_metrics_summary()
            assert isinstance(summary, dict)
            assert summary["api_calls_total"] >= 0
            assert summary["api_errors_total"] >= 0
            assert summary["api_errors_total"] <= summary["api_calls_total"]
            assert summary["pairs_kept_total"] >= 0
            assert summary["pairs_rejected_total"] >= 0
            assert summary["ws_connections"] >= 0
            assert summary["ws_reconnects"] >= 0
            assert summary["ws_errors"] >= 0
            assert 0 <= summary["api_error_rate_percent"] <= 100
            assert 0 <= summary["filter_success_rate_percent"] <= 100
    
    def test_extreme_concurrency_stability(self):
        """Test de stabilité sous concurrence extrême."""
        num_iterations = 10
        num_threads = 25
        operations_per_thread = 500
        
        for iteration in range(num_iterations):
            # Nettoyer l'état initial
            reset_metrics()
            snapshot = get_snapshot()
            for symbol in list(snapshot.keys()):
                purge_expired(ttl_seconds=0)  # Purger tout
            
            def extreme_worker(thread_id):
                """Worker de concurrence extrême."""
                for i in range(operations_per_thread):
                    try:
                        operation = i % 8
                        
                        if operation == 0:  # Écriture price_store
                            symbol = f"EXTREME_{thread_id % 10}"
                            mark_price = 1000.0 + thread_id * 100 + i
                            last_price = mark_price + random.uniform(-10, 10)
                            timestamp = time.time()
                            update(symbol, mark_price, last_price, timestamp)
                        
                        elif operation == 1:  # Lecture price_store
                            snapshot = get_snapshot()
                            assert isinstance(snapshot, dict)
                        
                        elif operation == 2:  # Purge price_store
                            purged_count = purge_expired(ttl_seconds=1)
                            assert isinstance(purged_count, int)
                            assert purged_count >= 0
                        
                        elif operation == 3:  # Appel API metrics
                            latency = random.uniform(0.05, 2.0)
                            success = random.choice([True, False])
                            record_api_call(latency, success)
                        
                        elif operation == 4:  # Résultat de filtre metrics
                            filter_name = f"extreme_filter_{thread_id % 5}"
                            kept = random.randint(1, 20)
                            rejected = random.randint(0, 10)
                            record_filter_result(filter_name, kept, rejected)
                        
                        elif operation == 5:  # Connexion WS metrics
                            record_ws_connection(connected=True)
                        
                        elif operation == 6:  # Reconnexion WS metrics
                            record_ws_connection(connected=False)
                        
                        else:  # Erreur WS metrics
                            record_ws_error()
                        
                        # Pas de sleep pour maximiser la concurrence
                        
                    except Exception as e:
                        print(f"Iteration {iteration}, Thread {thread_id}, Opération {i}: {e}")
                        raise
            
            # Créer et démarrer les threads
            threads = []
            for i in range(num_threads):
                thread = threading.Thread(target=extreme_worker, args=(i,))
                threads.append(thread)
                thread.start()
            
            # Attendre que tous les threads se terminent
            for thread in threads:
                thread.join()
            
            # Vérifier la cohérence finale
            snapshot = get_snapshot()
            assert isinstance(snapshot, dict)
            
            summary = get_metrics_summary()
            assert isinstance(summary, dict)
            
            # Vérifier que toutes les métriques sont cohérentes
            assert summary["api_calls_total"] >= 0
            assert summary["api_errors_total"] >= 0
            assert summary["api_errors_total"] <= summary["api_calls_total"]
            assert summary["pairs_kept_total"] >= 0
            assert summary["pairs_rejected_total"] >= 0
            assert summary["ws_connections"] >= 0
            assert summary["ws_reconnects"] >= 0
            assert summary["ws_errors"] >= 0
            assert 0 <= summary["api_error_rate_percent"] <= 100
            assert 0 <= summary["filter_success_rate_percent"] <= 100
