# bybit_bot_v0

Bot de trading automatisé pour Bybit avec WebSocket et API REST, incluant un système de watchlist avec filtrage par funding et volume.

## 🚀 Démarrage rapide

1. Installer les dépendances : `pip install -r requirements.txt`
2. (Optionnel privé) Créer `.env` avec `BYBIT_API_KEY` et `BYBIT_API_SECRET`
3. Lancer l'orchestrateur principal (watchlist + WS) : `python src/bot.py`

## 📊 Système de watchlist avancé

### Suivi des prix en temps réel avec filtrage intelligent
```bash
python src/bot.py
```

### Configuration
#### Fichier YAML (`src/parameters.yaml`)
```yaml
categorie: "linear"            # "linear" | "inverse" | "both"
funding_min: null              # ex: 0.0001 pour >= 0.01%
funding_max: null              # ex: 0.0005 pour <= 0.05%
volume_min: 1000000            # ex: 1000000 pour >= 1M USDT [ANCIEN]
volume_min_millions: 5.0       # ex: 5.0 pour >= 5M USDT [NOUVEAU]
spread_max: 0.003              # ex: 0.003 pour <= 0.30% spread
volatility_min: null           # ex: 0.002 pour >= 0.20% [NOUVEAU]
volatility_max: 0.007          # ex: 0.007 pour <= 0.70% [NOUVEAU]
funding_time_min_minutes: null # ex: 30 pour >= 30 min avant funding [NOUVEAU]
funding_time_max_minutes: null # ex: 120 pour <= 120 min avant funding [NOUVEAU]
volatility_ttl_sec: 120        # TTL du cache volatilité (secondes)
limite: 10                     # ex: 10 symboles max
```

#### Variables d'environnement (priorité maximale)
```bash
# Windows
setx TESTNET true                  # true|false (défaut true)
setx LOG_LEVEL INFO               # DEBUG|INFO|WARNING|ERROR
setx VOLUME_MIN_MILLIONS 5        # min 5M USDT
setx SPREAD_MAX 0.003             # max 0.30% spread
setx VOLATILITY_MIN 0.002         # min 0.20% volatilité 5m
setx VOLATILITY_MAX 0.007         # max 0.70% volatilité 5m
setx FUNDING_MIN 0.0001           # min 0.01% funding
setx FUNDING_MAX 0.0005           # max 0.05% funding
setx FUNDING_TIME_MIN_MINUTES 30  # min minutes avant funding (optionnel)
setx FUNDING_TIME_MAX_MINUTES 120 # max minutes avant funding (optionnel)
setx VOLATILITY_TTL_SEC 120       # TTL du cache volatilité (s)
setx CATEGORY linear              # linear | inverse | both
setx LIMIT 10                     # nombre max de symboles
setx PUBLIC_HTTP_MAX_CALLS_PER_SEC 5  # rate limiter public
setx PUBLIC_HTTP_WINDOW_SECONDS 1     # fenêtre du rate limiter

# Linux/Mac
export TESTNET=true
export LOG_LEVEL=INFO
export VOLUME_MIN_MILLIONS=5
export SPREAD_MAX=0.003
export VOLATILITY_MIN=0.002
export VOLATILITY_MAX=0.007
export FUNDING_MIN=0.0001
export FUNDING_MAX=0.0005
export FUNDING_TIME_MIN_MINUTES=30
export FUNDING_TIME_MAX_MINUTES=120
export VOLATILITY_TTL_SEC=120
export CATEGORY=linear
export LIMIT=10
export PUBLIC_HTTP_MAX_CALLS_PER_SEC=5
export PUBLIC_HTTP_WINDOW_SECONDS=1
```

### Fonctionnalités avancées
- ✅ **Filtrage par funding rate** (min/max)
- ✅ **Filtrage par volume 24h** (format millions plus lisible)
- ✅ **Filtrage par spread** (bid/ask) via REST tickers
- ✅ **Filtre temporel avant funding** (fenêtre min/max en minutes) — NOUVEAU
- ✅ **Filtrage par volatilité 5m** (plage high-low, min/max) — NOUVEAU
- ✅ **Tri par |funding| décroissant** (les plus extrêmes en premier)
- ✅ **Suivi des prix en temps réel** via WebSocket
- ✅ **Tableau optimisé** : Symbole | Funding % | Volume (M) | Spread % | Volatilité % | Funding T
- ✅ **Logs pédagogiques** avec comptes détaillés à chaque étape
- ✅ **Gestion d'erreurs robuste** pour les symboles invalides

### Exemple d'utilisation
```bash
# 1. Configurer les filtres via variables d'environnement
setx VOLUME_MIN_MILLIONS 5
setx SPREAD_MAX 0.003
setx VOLATILITY_MIN 0.002
setx VOLATILITY_MAX 0.007

# 2. Lancer le suivi des prix
python src/bot.py
```

**Résultat attendu :**
```
🎛️ Filtres | catégorie=linear | volume_min_millions=5.0 | spread_max=0.0030 | volatility_min=0.002 | volatility_max=0.007 | ft_min(min)=30 | ft_max(min)=120 | limite=10 | vol_ttl=120s
🧮 Comptes | avant filtres = 618 | après funding/volume/temps = 42 | après spread = 16 | après volatilité = 16 | après tri+limit = 10
✅ Filtre spread : gardés=16 | rejetés=26 (seuil 0.30%)
✅ Calcul volatilité async: gardés=12 | rejetés=4 (seuils: min=0.20% | max=0.70%)

Symbole  |    Funding % | Volume (M) |   Spread % | Volatilité % |    Funding T
---------+--------------+------------+-----------+-------------+--------------
MYXUSDT  |     -2.0000% |      250.5 |    +0.104% |     +0.450% |       1h 12m
REXUSDT  |     +0.4951% |      121.9 |    +0.050% |     +0.320% |          45m
```

## 📁 Structure du projet

### Scripts principaux
- `src/bot.py` - **ORCHESTRATEUR PRINCIPAL** : Watchlist (REST) + suivi temps réel (WS)
- `src/app.py` - Orchestrateur supervision (REST + WS public + WS privé) [DEBUG/SUPERVISION ONLY]
- `src/main.py` - Point d'entrée privé (lecture du solde)

### Modules de base
- `src/bybit_client.py` - Client Bybit API
- `src/config.py` - Configuration et variables d'environnement
- `src/logging_setup.py` - Configuration des logs

### Modules de watchlist
- `src/instruments.py` - Récupération des instruments perpétuels (pagination 1000)
- `src/watchlist_manager.py` - Gestionnaire principal de watchlist avec filtrage et scoring
- `src/volatility.py` - Calcul de volatilité 5 minutes (async, semaphore=5)
- `src/price_store.py` - Stockage des prix en mémoire
- `src/filtering.py` - Code vestigial/expérimental (non utilisé en production)
- `src/parameters.yaml` - Configuration des paramètres

### Scripts de test
- `src/run_ws_public.py` - WebSocket publique
- `src/run_ws_private.py` - WebSocket privée

## 🗒️ Journal de bord & Workflow
- Toutes les modifications importantes doivent être **documentées** dans `JOURNAL.md` (voir modèle).
- Avant de merger un changement :
  1. Mettre à jour `JOURNAL.md` (nouvelle entrée).
  2. Supprimer/renommer **tout code devenu inutile**.
  3. Vérifier les logs (simples, compréhensibles).

## 🎯 Commandes utiles
- **Orchestrateur principal (watchlist + WS)** : `python src/bot.py`
- **Orchestrateur supervision (REST/WS public/privé)** : `python src/app.py` [DEBUG/SUPERVISION ONLY]
- **REST privé (solde)** : `python src/main.py`
- **WS publique (test)** : `python src/run_ws_public.py`
- **WS privée (test)** : `python src/run_ws_private.py`

## 🔧 Configuration avancée
- **Variables d'environnement clés** : `TESTNET`, `TIMEOUT`, `LOG_LEVEL`, `VOLUME_MIN_MILLIONS`, `SPREAD_MAX`, `VOLATILITY_MIN`, `VOLATILITY_MAX`, `FUNDING_MIN`, `FUNDING_MAX`, `FUNDING_TIME_MIN_MINUTES`, `FUNDING_TIME_MAX_MINUTES`, `VOLATILITY_TTL_SEC`, `CATEGORY`, `LIMIT`, `PUBLIC_HTTP_MAX_CALLS_PER_SEC`, `PUBLIC_HTTP_WINDOW_SECONDS`
- **Clés privées (.env)** : `BYBIT_API_KEY`, `BYBIT_API_SECRET` (requis pour `src/app.py` et `src/main.py`)
- **Fichier de config** : `src/parameters.yaml`
- **Priorité** : ENV > fichier YAML > valeurs par défaut
