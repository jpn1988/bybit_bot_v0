"""Tests multithreading pour price_store."""

import pytest
import threading
import time
import random
from price_store import update, get_snapshot, purge_expired


class TestConcurrentPriceStore:
    """Tests de concurrence pour price_store."""
    
    def test_concurrent_updates_same_symbol(self):
        """Test d'écritures concurrentes sur le même symbole."""
        symbol = "BTCUSDT"
        num_threads = 10
        updates_per_thread = 100
        
        def update_worker(thread_id):
            """Worker qui effectue des mises à jour."""
            for i in range(updates_per_thread):
                mark_price = 50000.0 + thread_id * 1000 + i
                last_price = mark_price + random.uniform(-10, 10)
                timestamp = time.time()
                update(symbol, mark_price, last_price, timestamp)
                # Petit délai pour simuler des conditions réelles
                time.sleep(0.001)
        
        # Créer et démarrer les threads
        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=update_worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Attendre que tous les threads se terminent
        for thread in threads:
            thread.join()
        
        # Vérifier que le symbole existe et contient des données cohérentes
        snapshot = get_snapshot()
        assert symbol in snapshot
        
        price_data = snapshot[symbol]
        assert "mark_price" in price_data
        assert "last_price" in price_data
        assert "timestamp" in price_data
        
        # Vérifier que les valeurs sont numériques et cohérentes
        assert isinstance(price_data["mark_price"], (int, float))
        assert isinstance(price_data["last_price"], (int, float))
        assert isinstance(price_data["timestamp"], (int, float))
        
        # Vérifier que le timestamp est récent (moins de 5 secondes)
        assert time.time() - price_data["timestamp"] < 5.0
    
    def test_concurrent_updates_different_symbols(self):
        """Test d'écritures concurrentes sur différents symboles."""
        symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "SOLUSDT", "DOTUSDT"]
        num_threads = 20
        updates_per_thread = 50
        
        def update_worker(thread_id):
            """Worker qui effectue des mises à jour sur différents symboles."""
            for i in range(updates_per_thread):
                symbol = symbols[thread_id % len(symbols)]
                mark_price = 1000.0 + thread_id * 100 + i
                last_price = mark_price + random.uniform(-5, 5)
                timestamp = time.time()
                update(symbol, mark_price, last_price, timestamp)
                time.sleep(0.001)
        
        # Créer et démarrer les threads
        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=update_worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Attendre que tous les threads se terminent
        for thread in threads:
            thread.join()
        
        # Vérifier que tous les symboles sont présents
        snapshot = get_snapshot()
        for symbol in symbols:
            assert symbol in snapshot
            price_data = snapshot[symbol]
            assert "mark_price" in price_data
            assert "last_price" in price_data
            assert "timestamp" in price_data
    
    def test_concurrent_read_write(self):
        """Test de lectures et écritures concurrentes."""
        symbol = "BTCUSDT"
        num_writers = 5
        num_readers = 10
        updates_per_writer = 50
        reads_per_reader = 100
        
        def writer_worker(thread_id):
            """Worker qui écrit des données."""
            for i in range(updates_per_writer):
                mark_price = 50000.0 + thread_id * 1000 + i
                last_price = mark_price + random.uniform(-10, 10)
                timestamp = time.time()
                update(symbol, mark_price, last_price, timestamp)
                time.sleep(0.001)
        
        def reader_worker(thread_id):
            """Worker qui lit des données."""
            for i in range(reads_per_reader):
                snapshot = get_snapshot()
                # Vérifier que la lecture ne cause pas d'erreur
                assert isinstance(snapshot, dict)
                time.sleep(0.001)
        
        # Créer et démarrer les threads
        threads = []
        
        # Threads d'écriture
        for i in range(num_writers):
            thread = threading.Thread(target=writer_worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Threads de lecture
        for i in range(num_readers):
            thread = threading.Thread(target=reader_worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Attendre que tous les threads se terminent
        for thread in threads:
            thread.join()
        
        # Vérifier que le symbole existe et contient des données cohérentes
        snapshot = get_snapshot()
        assert symbol in snapshot
        price_data = snapshot[symbol]
        assert "mark_price" in price_data
        assert "last_price" in price_data
        assert "timestamp" in price_data
    
    def test_concurrent_purge_expired(self):
        """Test de purge concurrente avec des mises à jour."""
        symbol = "BTCUSDT"
        num_updaters = 5
        num_purgers = 3
        updates_per_updater = 100
        purges_per_purger = 50
        
        def updater_worker(thread_id):
            """Worker qui met à jour les prix."""
            for i in range(updates_per_updater):
                mark_price = 50000.0 + thread_id * 1000 + i
                last_price = mark_price + random.uniform(-10, 10)
                timestamp = time.time()
                update(symbol, mark_price, last_price, timestamp)
                time.sleep(0.001)
        
        def purger_worker(thread_id):
            """Worker qui purge les données expirées."""
            for i in range(purges_per_purger):
                purged_count = purge_expired(ttl_seconds=1)  # TTL très court
                # Vérifier que la purge ne cause pas d'erreur
                assert isinstance(purged_count, int)
                assert purged_count >= 0
                time.sleep(0.002)
        
        # Créer et démarrer les threads
        threads = []
        
        # Threads de mise à jour
        for i in range(num_updaters):
            thread = threading.Thread(target=updater_worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Threads de purge
        for i in range(num_purgers):
            thread = threading.Thread(target=purger_worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Attendre que tous les threads se terminent
        for thread in threads:
            thread.join()
        
        # Vérifier que le symbole existe toujours (car les mises à jour sont récentes)
        snapshot = get_snapshot()
        if symbol in snapshot:  # Peut être purgé si TTL très court
            price_data = snapshot[symbol]
            assert "mark_price" in price_data
            assert "last_price" in price_data
            assert "timestamp" in price_data
    
    def test_data_consistency_under_load(self):
        """Test de cohérence des données sous charge."""
        symbol = "BTCUSDT"
        num_threads = 15
        operations_per_thread = 200
        
        def mixed_worker(thread_id):
            """Worker qui effectue des opérations mixtes."""
            for i in range(operations_per_thread):
                operation = i % 3
                
                if operation == 0:  # Écriture
                    mark_price = 50000.0 + thread_id * 1000 + i
                    last_price = mark_price + random.uniform(-10, 10)
                    timestamp = time.time()
                    update(symbol, mark_price, last_price, timestamp)
                
                elif operation == 1:  # Lecture
                    snapshot = get_snapshot()
                    assert isinstance(snapshot, dict)
                
                else:  # Purge
                    purged_count = purge_expired(ttl_seconds=2)
                    assert isinstance(purged_count, int)
                    assert purged_count >= 0
                
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
        
        # Vérifier la cohérence finale
        snapshot = get_snapshot()
        assert isinstance(snapshot, dict)
        
        # Si le symbole existe, vérifier sa cohérence
        if symbol in snapshot:
            price_data = snapshot[symbol]
            assert "mark_price" in price_data
            assert "last_price" in price_data
            assert "timestamp" in price_data
            assert isinstance(price_data["mark_price"], (int, float))
            assert isinstance(price_data["last_price"], (int, float))
            assert isinstance(price_data["timestamp"], (int, float))
    
    def test_no_crashes_under_stress(self):
        """Test de stabilité sous stress intense."""
        symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "SOLUSDT"]
        num_threads = 20
        operations_per_thread = 500
        
        def stress_worker(thread_id):
            """Worker de stress qui effectue beaucoup d'opérations."""
            for i in range(operations_per_thread):
                try:
                    symbol = symbols[thread_id % len(symbols)]
                    operation = i % 4
                    
                    if operation == 0:  # Écriture
                        mark_price = 1000.0 + thread_id * 100 + i
                        last_price = mark_price + random.uniform(-5, 5)
                        timestamp = time.time()
                        update(symbol, mark_price, last_price, timestamp)
                    
                    elif operation == 1:  # Lecture
                        snapshot = get_snapshot()
                        assert isinstance(snapshot, dict)
                    
                    elif operation == 2:  # Purge
                        purged_count = purge_expired(ttl_seconds=1)
                        assert isinstance(purged_count, int)
                    
                    else:  # Lecture spécifique
                        snapshot = get_snapshot()
                        if symbol in snapshot:
                            price_data = snapshot[symbol]
                            assert "mark_price" in price_data
                            assert "last_price" in price_data
                            assert "timestamp" in price_data
                    
                    # Pas de sleep pour maximiser la concurrence
                    
                except Exception as e:
                    # Enregistrer l'erreur mais continuer
                    print(f"Erreur dans thread {thread_id}, opération {i}: {e}")
                    raise
        
        # Créer et démarrer les threads
        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=stress_worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Attendre que tous les threads se terminent
        for thread in threads:
            thread.join()
        
        # Vérifier que le système est toujours cohérent
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
