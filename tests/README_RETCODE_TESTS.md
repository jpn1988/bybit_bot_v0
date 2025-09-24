# Tests de gestion des retCode de l'API Bybit

Ce document décrit les tests unitaires créés pour vérifier la gestion des `retCode` de l'API Bybit dans le projet.

## 📁 Structure des tests

```
tests/
├── mocks/
│   ├── __init__.py
│   └── bybit_responses.py          # Mocks de réponses API
├── test_bybit_retcode_handling.py  # Tests pour BybitClient
├── test_watchlist_data_fetcher_retcode.py  # Tests pour WatchlistDataFetcher
├── test_instruments_retcode.py     # Tests pour instruments.py
├── test_ws_private_retcode.py      # Tests pour WebSocket privée
├── test_retcode_comprehensive.py   # Tests complets
└── README_RETCODE_TESTS.md         # Ce fichier
```

## 🎯 Objectifs des tests

Les tests vérifient que le bot réagit correctement aux différents `retCode` de l'API Bybit :

- ✅ **retCode = 0** → Succès, pas d'exception
- ❌ **retCode = 10002** → Paramètres invalides, exception générique
- ❌ **retCode = 10005** → Clé API invalide, exception d'authentification
- ❌ **retCode = 10006** → Permission refusée, exception d'authentification
- ❌ **retCode = 10016** → Limite de taux atteinte, gestion spéciale
- ❌ **retCode = 10017** → Timestamp invalide, exception spécifique
- ❌ **retCode = 10018** → IP non autorisée, exception spécifique
- ❌ **retCode = 30084** → Solde insuffisant, exception de trading
- ❌ **retCode = 99999** → Erreur inconnue, exception générique

## 🧪 Types de tests

### 1. Tests unitaires par module

#### `test_bybit_retcode_handling.py`
- Tests de la gestion des retCode dans `BybitClient`
- Vérification des exceptions levées
- Tests des métriques d'API
- Gestion des erreurs HTTP et réseau

#### `test_watchlist_data_fetcher_retcode.py`
- Tests de la gestion des retCode dans `WatchlistDataFetcher`
- Vérification des exceptions pour les requêtes de funding
- Tests des erreurs HTTP et de parsing

#### `test_instruments_retcode.py`
- Tests de la gestion des retCode dans `instruments.py`
- Vérification des exceptions pour les requêtes d'instruments
- Tests des erreurs réseau et de timeout

#### `test_ws_private_retcode.py`
- Tests de la gestion des retCode dans la WebSocket privée
- Vérification de l'authentification WebSocket
- Tests des callbacks d'erreur

### 2. Tests complets

#### `test_retcode_comprehensive.py`
- Tests de tous les modules ensemble
- Vérification de la cohérence des messages d'erreur
- Tests de tous les codes d'erreur disponibles
- Validation des scénarios d'erreur réseau et HTTP

## 🔧 Mocks de réponses

### `tests/mocks/bybit_responses.py`

Contient des mocks pour tous les types de réponses API :

#### Réponses de succès
- `get_success_response()` - Réponse standard de succès
- `get_wallet_balance_success()` - Réponse de solde de portefeuille
- `get_empty_result_response()` - Réponse avec résultat vide

#### Réponses d'erreur d'authentification
- `get_invalid_api_key_response()` - retCode=10005
- `get_permission_denied_response()` - retCode=10006
- `get_rate_limit_response()` - retCode=10016
- `get_invalid_timestamp_response()` - retCode=10017
- `get_ip_not_whitelisted_response()` - retCode=10018

#### Réponses d'erreur de paramètres
- `get_invalid_params_response()` - retCode=10002
- `get_invalid_request_response()` - retCode=10001
- `get_invalid_signature_response()` - retCode=10003

#### Réponses d'erreur de trading
- `get_insufficient_balance_response()` - retCode=30084
- `get_order_not_found_response()` - retCode=30085
- `get_position_not_found_response()` - retCode=30086

#### Réponses d'erreur inconnues
- `get_unknown_error_response()` - retCode=99999
- `get_custom_error_response(ret_code, ret_msg)` - Erreur personnalisée

#### Réponses spéciales
- `get_malformed_response()` - Réponse sans retCode
- `get_missing_result_response()` - Réponse sans champ result

## 🚀 Exécution des tests

### Tous les tests
```bash
python -m pytest tests/ -k "retcode" -v
```

### Tests spécifiques
```bash
# Tests BybitClient
python -m pytest tests/test_bybit_retcode_handling.py -v

# Tests WatchlistDataFetcher
python -m pytest tests/test_watchlist_data_fetcher_retcode.py -v

# Tests instruments
python -m pytest tests/test_instruments_retcode.py -v

# Tests WebSocket privée
python -m pytest tests/test_ws_private_retcode.py -v

# Tests complets
python -m pytest tests/test_retcode_comprehensive.py -v
```

### Tests avec couverture
```bash
python -m pytest tests/ -k "retcode" --cov=src --cov-report=html
```

## 📊 Couverture des tests

Les tests couvrent :

- ✅ **Tous les retCode** documentés dans `constants.py`
- ✅ **Tous les modules** qui interagissent avec l'API Bybit
- ✅ **Tous les types d'erreurs** : HTTP, réseau, timeout, JSON
- ✅ **Tous les scénarios** : succès, échec, cas limites
- ✅ **Cohérence des messages** d'erreur entre modules
- ✅ **Gestion des exceptions** dans les callbacks

## 🔍 Scénarios testés

### Scénarios de succès
- retCode=0 avec données valides
- retCode=0 avec résultat vide
- Authentification WebSocket réussie

### Scénarios d'erreur d'authentification
- Clé API invalide (10005)
- Permission refusée (10006)
- Limite de taux (10016) avec retry
- Timestamp invalide (10017)
- IP non autorisée (10018)

### Scénarios d'erreur de paramètres
- Paramètres invalides (10002)
- Requête invalide (10001)
- Signature invalide (10003)

### Scénarios d'erreur de trading
- Solde insuffisant (30084)
- Ordre non trouvé (30085)
- Position non trouvée (30086)

### Scénarios d'erreur inconnue
- Code d'erreur non documenté (99999)
- Messages d'erreur personnalisés

### Scénarios d'erreur technique
- Erreurs HTTP (400, 500)
- Erreurs réseau (timeout, connexion)
- Erreurs de parsing JSON
- Réponses malformées

## 🎯 Résultats attendus

### Succès (retCode=0)
- Aucune exception levée
- Données retournées correctement
- Métriques d'API enregistrées

### Erreurs d'authentification (10005, 10006)
- Exception `RuntimeError` avec message spécifique
- Message contient "Authentification échouée"
- WebSocket fermée en cas d'échec d'auth

### Erreurs de paramètres (10002, etc.)
- Exception `RuntimeError` avec message générique
- Message contient le retCode et retMsg

### Erreurs inconnues (99999, etc.)
- Exception `RuntimeError` avec message générique
- Message contient "Erreur API Bybit"

### Erreurs techniques
- Exceptions appropriées (HTTP, réseau, JSON)
- Pas de crash du bot
- Logs d'erreur appropriés

## 🔧 Maintenance

### Ajout de nouveaux retCode
1. Ajouter le code dans `constants.py`
2. Créer un mock dans `bybit_responses.py`
3. Ajouter des tests dans les fichiers de test appropriés
4. Mettre à jour ce README

### Ajout de nouveaux modules
1. Créer un fichier de test `test_[module]_retcode.py`
2. Tester tous les retCode pertinents
3. Vérifier la cohérence des messages d'erreur
4. Ajouter à `test_retcode_comprehensive.py`

## 📝 Notes importantes

- Les tests utilisent des mocks pour éviter les appels API réels
- Tous les tests sont isolés et ne dépendent pas les uns des autres
- Les messages d'erreur sont vérifiés pour la cohérence
- Les exceptions sont testées pour s'assurer qu'elles sont levées au bon moment
- Les métriques d'API sont vérifiées en cas de succès
