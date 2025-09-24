"""Tests multithreading pour metrics."""

import pytest
import threading
import time
import random
from metrics import (
    MetricsCollector, 
    record_api_call, 
    record_filter_result, 
    record_ws_connection, 
    record_ws_error, 
    get_metrics_summary, 
    reset_metrics
)


class TestConcurrentMetrics:
    """Tests de concurrence pour metrics."""
    
    def test_concurrent_api_calls(self):
        """Test d'enregistrements concurrents d'appels API."""
        collector = MetricsCollector()
        num_threads = 10
        calls_per_thread = 100
        
        def api_call_worker(thread_id):
            """Worker qui enregistre des appels API."""
            for i in range(calls_per_thread):
                latency = random.uniform(0.1, 2.0)
                success = random.choice([True, False])
                collector.record_api_call(latency, success)
                time.sleep(0.001)
        
        # Créer et démarrer les threads
        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=api_call_worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Attendre que tous les threads se terminent
        for thread in threads:
            thread.join()
        
        # Vérifier que le nombre total d'appels est correct
        expected_total_calls = num_threads * calls_per_thread
        assert collector._data.api_calls_total == expected_total_calls
        
        # Vérifier que les latences sont stockées
        assert len(collector._data.api_latencies) == expected_total_calls
        
        # Vérifier que le résumé est cohérent
        summary = collector.get_metrics_summary()
        assert summary["api_calls_total"] == expected_total_calls
        assert summary["api_errors_total"] >= 0
        assert summary["api_errors_total"] <= expected_total_calls
        assert summary["api_avg_latency_ms"] > 0
    
    def test_concurrent_filter_results(self):
        """Test d'enregistrements concurrents de résultats de filtres."""
        collector = MetricsCollector()
        num_threads = 8
        results_per_thread = 50
        filter_names = ["funding", "spread", "volume", "volatility"]
        
        def filter_worker(thread_id):
            """Worker qui enregistre des résultats de filtres."""
            for i in range(results_per_thread):
                filter_name = filter_names[thread_id % len(filter_names)]
                kept = random.randint(1, 20)
                rejected = random.randint(0, 10)
                collector.record_filter_result(filter_name, kept, rejected)
                time.sleep(0.001)
        
        # Créer et démarrer les threads
        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=filter_worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Attendre que tous les threads se terminent
        for thread in threads:
            thread.join()
        
        # Vérifier que les totaux sont cohérents
        expected_total_results = num_threads * results_per_thread
        assert collector._data.pairs_kept_total > 0
        assert collector._data.pairs_rejected_total >= 0
        
        # Vérifier que tous les filtres ont des statistiques
        for filter_name in filter_names:
            assert filter_name in collector._data.filter_stats
            assert "kept" in collector._data.filter_stats[filter_name]
            assert "rejected" in collector._data.filter_stats[filter_name]
        
        # Vérifier que le résumé est cohérent
        summary = collector.get_metrics_summary()
        assert summary["pairs_kept_total"] > 0
        assert summary["pairs_rejected_total"] >= 0
        assert summary["filter_success_rate_percent"] >= 0
        assert summary["filter_success_rate_percent"] <= 100
    
    def test_concurrent_ws_operations(self):
        """Test d'opérations WebSocket concurrentes."""
        collector = MetricsCollector()
        num_threads = 6
        operations_per_thread = 75
        
        def ws_worker(thread_id):
            """Worker qui effectue des opérations WebSocket."""
            for i in range(operations_per_thread):
                operation = i % 3
                
                if operation == 0:  # Connexion
                    collector.record_ws_connection(connected=True)
                elif operation == 1:  # Reconnexion
                    collector.record_ws_connection(connected=False)
                else:  # Erreur
                    collector.record_ws_error()
                
                time.sleep(0.001)
        
        # Créer et démarrer les threads
        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=ws_worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Attendre que tous les threads se terminent
        for thread in threads:
            thread.join()
        
        # Vérifier que les compteurs sont cohérents
        expected_total_operations = num_threads * operations_per_thread
        total_ws_operations = (collector._data.ws_connections + 
                             collector._data.ws_reconnects + 
                             collector._data.ws_errors)
        
        assert total_ws_operations == expected_total_operations
        assert collector._data.ws_connections > 0
        assert collector._data.ws_reconnects > 0
        assert collector._data.ws_errors > 0
        
        # Vérifier que le résumé est cohérent
        summary = collector.get_metrics_summary()
        assert summary["ws_connections"] > 0
        assert summary["ws_reconnects"] > 0
        assert summary["ws_errors"] > 0
    
    def test_concurrent_mixed_operations(self):
        """Test d'opérations mixtes concurrentes."""
        collector = MetricsCollector()
        num_threads = 12
        operations_per_thread = 100
        
        def mixed_worker(thread_id):
            """Worker qui effectue des opérations mixtes."""
            for i in range(operations_per_thread):
                operation = i % 5
                
                if operation == 0:  # Appel API
                    latency = random.uniform(0.1, 1.0)
                    success = random.choice([True, False])
                    collector.record_api_call(latency, success)
                
                elif operation == 1:  # Résultat de filtre
                    filter_name = f"filter_{thread_id % 3}"
                    kept = random.randint(1, 15)
                    rejected = random.randint(0, 8)
                    collector.record_filter_result(filter_name, kept, rejected)
                
                elif operation == 2:  # Connexion WS
                    collector.record_ws_connection(connected=True)
                
                elif operation == 3:  # Reconnexion WS
                    collector.record_ws_connection(connected=False)
                
                else:  # Erreur WS
                    collector.record_ws_error()
                
                time.sleep(0.001)
        
        # Créer et démarrer les threads
        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=mixed_worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Attendre que tous les threads se terminent
        for thread in threads:
            thread.join()
        
        # Vérifier que toutes les métriques sont cohérentes
        summary = collector.get_metrics_summary()
        
        assert summary["api_calls_total"] > 0
        assert summary["pairs_kept_total"] > 0
        assert summary["ws_connections"] > 0
        assert summary["ws_reconnects"] > 0
        assert summary["ws_errors"] > 0
        
        # Vérifier que les taux sont cohérents
        assert 0 <= summary["api_error_rate_percent"] <= 100
        assert 0 <= summary["filter_success_rate_percent"] <= 100
        
        # Vérifier que les statistiques de filtres sont présentes
        assert "filter_stats" in summary
        assert len(summary["filter_stats"]) > 0
    
    def test_concurrent_global_functions(self):
        """Test des fonctions globales de métriques en concurrence."""
        reset_metrics()  # S'assurer d'un état propre
        
        num_threads = 8
        operations_per_thread = 50
        
        def global_worker(thread_id):
            """Worker qui utilise les fonctions globales."""
            for i in range(operations_per_thread):
                operation = i % 4
                
                if operation == 0:  # Appel API global
                    latency = random.uniform(0.1, 1.0)
                    success = random.choice([True, False])
                    record_api_call(latency, success)
                
                elif operation == 1:  # Résultat de filtre global
                    filter_name = f"global_filter_{thread_id % 2}"
                    kept = random.randint(1, 10)
                    rejected = random.randint(0, 5)
                    record_filter_result(filter_name, kept, rejected)
                
                elif operation == 2:  # Connexion WS globale
                    record_ws_connection(connected=True)
                
                else:  # Erreur WS globale
                    record_ws_error()
                
                time.sleep(0.001)
        
        # Créer et démarrer les threads
        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=global_worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Attendre que tous les threads se terminent
        for thread in threads:
            thread.join()
        
        # Vérifier que les métriques globales sont cohérentes
        summary = get_metrics_summary()
        
        assert summary["api_calls_total"] > 0
        assert summary["pairs_kept_total"] > 0
        assert summary["ws_connections"] > 0
        assert summary["ws_reconnects"] > 0
        assert summary["ws_errors"] > 0
        
        # Vérifier que les taux sont cohérents
        assert 0 <= summary["api_error_rate_percent"] <= 100
        assert 0 <= summary["filter_success_rate_percent"] <= 100
    
    def test_concurrent_reset_operations(self):
        """Test de remise à zéro concurrente."""
        collector = MetricsCollector()
        num_threads = 6
        operations_per_thread = 100
        
        def reset_worker(thread_id):
            """Worker qui effectue des opérations et des resets."""
            for i in range(operations_per_thread):
                operation = i % 4
                
                if operation == 0:  # Ajouter des métriques
                    collector.record_api_call(random.uniform(0.1, 1.0), True)
                    collector.record_filter_result("test", 5, 3)
                    collector.record_ws_connection(connected=True)
                
                elif operation == 1:  # Lire les métriques
                    summary = collector.get_metrics_summary()
                    assert isinstance(summary, dict)
                
                elif operation == 2:  # Reset (seulement certains threads)
                    if thread_id % 3 == 0:  # Un tiers des threads font des resets
                        collector.reset()
                
                else:  # Ajouter plus de métriques
                    collector.record_ws_error()
                
                time.sleep(0.001)
        
        # Créer et démarrer les threads
        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=reset_worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Attendre que tous les threads se terminent
        for thread in threads:
            thread.join()
        
        # Vérifier que le système est toujours cohérent
        summary = collector.get_metrics_summary()
        assert isinstance(summary, dict)
        assert "api_calls_total" in summary
        assert "pairs_kept_total" in summary
        assert "ws_connections" in summary
        assert "ws_reconnects" in summary
        assert "ws_errors" in summary
    
    def test_data_consistency_under_load(self):
        """Test de cohérence des données sous charge intense."""
        collector = MetricsCollector()
        num_threads = 15
        operations_per_thread = 300
        
        def load_worker(thread_id):
            """Worker de charge qui effectue beaucoup d'opérations."""
            for i in range(operations_per_thread):
                try:
                    operation = i % 6
                    
                    if operation == 0:  # Appel API
                        latency = random.uniform(0.05, 2.0)
                        success = random.choice([True, False])
                        collector.record_api_call(latency, success)
                    
                    elif operation == 1:  # Résultat de filtre
                        filter_name = f"load_filter_{thread_id % 4}"
                        kept = random.randint(1, 25)
                        rejected = random.randint(0, 15)
                        collector.record_filter_result(filter_name, kept, rejected)
                    
                    elif operation == 2:  # Connexion WS
                        collector.record_ws_connection(connected=True)
                    
                    elif operation == 3:  # Reconnexion WS
                        collector.record_ws_connection(connected=False)
                    
                    elif operation == 4:  # Erreur WS
                        collector.record_ws_error()
                    
                    else:  # Lecture des métriques
                        summary = collector.get_metrics_summary()
                        assert isinstance(summary, dict)
                        assert "api_calls_total" in summary
                        assert "pairs_kept_total" in summary
                        assert "ws_connections" in summary
                    
                    # Pas de sleep pour maximiser la concurrence
                    
                except Exception as e:
                    # Enregistrer l'erreur mais continuer
                    print(f"Erreur dans thread {thread_id}, opération {i}: {e}")
                    raise
        
        # Créer et démarrer les threads
        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=load_worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Attendre que tous les threads se terminent
        for thread in threads:
            thread.join()
        
        # Vérifier que le système est toujours cohérent
        summary = collector.get_metrics_summary()
        assert isinstance(summary, dict)
        
        # Vérifier que toutes les métriques sont présentes et cohérentes
        assert "api_calls_total" in summary
        assert "api_errors_total" in summary
        assert "pairs_kept_total" in summary
        assert "pairs_rejected_total" in summary
        assert "ws_connections" in summary
        assert "ws_reconnects" in summary
        assert "ws_errors" in summary
        
        # Vérifier que les valeurs sont cohérentes
        assert summary["api_calls_total"] >= 0
        assert summary["api_errors_total"] >= 0
        assert summary["api_errors_total"] <= summary["api_calls_total"]
        assert summary["pairs_kept_total"] >= 0
        assert summary["pairs_rejected_total"] >= 0
        assert summary["ws_connections"] >= 0
        assert summary["ws_reconnects"] >= 0
        assert summary["ws_errors"] >= 0
        
        # Vérifier que les taux sont cohérents
        assert 0 <= summary["api_error_rate_percent"] <= 100
        assert 0 <= summary["filter_success_rate_percent"] <= 100
