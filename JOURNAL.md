# Journal de bord — bybit_bot_v0

> Ce fichier documente **ce qui a été fait** (date, but, fichiers modifiés), **pourquoi**, **comment tester**, et **les prochaines étapes**.  
> **Règle d'or :** chaque modification significative ajoute une entrée ci-dessous.

## 🔰 Base initiale (2025-09-06)
**But :** Démarrage propre du projet, config `.env`, logs clairs, appel REST public pour l'heure serveur.  
**Fichiers clés :** `src/main.py`, `src/config.py`, `src/logging_setup.py`, `src/bybit_client.py`  
**Test :** `python src/main.py` → affiche l'heure serveur puis `OK`.  
**Résultat :** ✅ OK

## 🔐 Passage API privée (2025-09-06)
**But :** Lire le solde via Bybit v5 privé (UNIFIED).  
**Fichiers modifiés :** `src/bybit_client.py`, `src/main.py`, `.env`  
**Test :** `python src/main.py` → logs `✅ Solde USDT ...`  
**Résultat :** ✅ OK (equity ≈ walletBalance)

## 🌐 WebSocket publique — connexion (2025-09-06)
**But :** Vérifier ouverture WS publique (sans abonnement), logs + fermeture propre.  
**Fichier :** `src/run_ws_public.py`  
**Test :** `python src/run_ws_public.py`  
**Résultat :** ✅ OK (timeout si idle → normal)

## 🌐 WebSocket privée — auth & stabilité (2025-09-07)
**But :** Connexion, auth WS privée correcte (`"GET/realtime" + expires_ms`), ping/pong, reconnexion.  
**Fichier :** `src/run_ws_private.py`  
**Test :** `python src/run_ws_private.py`  
**Résultat :** ✅ OK (auth OK, souscription confirmée)

## 🧑‍✈️ Orchestrateur (2025-09-07)
**But :** Lancer REST privé + WS publique + WS privée, health-check périodique, arrêt propre.  
**Fichier :** `src/app.py`  
**Test :** `python src/app.py`  
**Résultat :** ✅ OK (CONNECTED sur public & privé)

## [2025-09-07] — Comptage de l'univers perp (linear/inverse)
**But :** Logguer au démarrage le nombre de contrats perp disponibles (USDT + coin-margined) pour informer l'orchestrateur et la stratégie.
**Fichiers modifiés :** src/app.py
**Tests/commandes :** `python src/app.py` → vérifier la présence des 4 logs :
  - "🗺️ Détection de l'univers perp en cours…"
  - "✅ Perp USDT (linear) détectés : X"
  - "✅ Perp coin-margined (inverse) détectés : Y"
  - "📊 Univers perp total : Z"
**Résultat :** ✅ OK

## [2025-09-07] — Système de watchlist avec filtrage par funding et volume
**But :** Créer un système complet de filtrage des contrats perpétuels par funding rate et volume, avec suivi des prix en temps réel.
**Fichiers créés :** 
  - `src/instruments.py` - Récupération des instruments perpétuels
  - `src/filtering.py` - Filtrage par critères (funding, volume) [VESTIGIAL - non utilisé en production]
  - `src/price_store.py` - Stockage des prix en mémoire
  - `src/run_ws_prices.py` - Script principal de suivi des prix
  - `src/watchlist_config.fr.yaml` - Configuration en français
**Fichiers modifiés :** 
  - `src/bybit_client.py` - Ajout de `public_base_url()`
  - `src/app.py` - Intégration du comptage perp au démarrage
**Fonctionnalités :**
  - Filtrage par catégorie (linear/inverse/both)
  - Filtrage par funding rate (min/max)
  - Filtrage par volume 24h minimum
  - Tri par |funding| décroissant
  - Suivi des prix en temps réel via WebSocket
  - Tableau aligné avec mark price, last price, funding %, volume 24h, âge
**Tests/commandes :** 
  - `python src/run_ws_prices.py` → affiche les paires filtrées avec prix temps réel
  - Modifier `src/watchlist_config.fr.yaml` pour ajuster les filtres
**Résultat :** ✅ OK (système complet et fonctionnel)

## [2025-09-08] — Amélioration du système de watchlist : filtres de spread et volume en millions
**But :** Ajouter un filtre de spread (bid/ask) et améliorer la gestion du volume avec un format en millions, plus des logs pédagogiques détaillés.
**Fichiers modifiés :** 
  - `src/config.py` - Ajout des variables d'environnement SPREAD_MAX et VOLUME_MIN_MILLIONS
  - `src/run_ws_prices.py` - Pipeline de filtrage enrichi avec spread et volume en millions
  - `src/watchlist_config.fr.yaml` - Configuration mise à jour avec les nouveaux paramètres
**Nouvelles fonctionnalités :**
  - **Filtre de spread** : Calcul automatique du spread (ask1-bid1)/((ask1+bid1)/2) via API REST
  - **Volume en millions** : Format plus lisible (5.0 = 5M USDT) avec priorité ENV > fichier > ancien format
  - **Gestion d'erreurs robuste** : Récupération des spreads un par un en cas de symboles invalides
  - **Tableau simplifié** : Suppression des colonnes Mark Price, Last Price et Âge (s)
  - **Logs pédagogiques** : Comptes détaillés à chaque étape du filtrage
**Configuration :**
  - Variables d'environnement : `VOLUME_MIN_MILLIONS=5` et `SPREAD_MAX=0.003`
  - Fichier YAML : `volume_min_millions: 5.0` et `spread_max: 0.03`
**Tests/commandes :** 
  - `setx VOLUME_MIN_MILLIONS 5 && setx SPREAD_MAX 0.003`
  - `python src/run_ws_prices.py` → tableau avec colonnes : Symbole | Funding % | Volume (M) | Spread %
**Résultat :** ✅ OK (filtres fonctionnels, tableau optimisé, logs clairs)

## [2025-01-27] — Renommage de l'orchestrateur principal : run_ws_prices.py → bot.py
**But :** Faire de `src/bot.py` l'orchestrateur officiel du bot avec un nom plus classique, sans refactor lourd.
**Fichiers modifiés :** 
  - `src/run_ws_prices.py` → `src/bot.py` (renommé)
  - `src/bot.py` - Ajustement des bandeaux de démarrage
  - `README.md` - Mise à jour des commandes et variables d'environnement
  - `JOURNAL.md` - Documentation du changement
**Décisions/raisons :**
  - Nom plus classique et professionnel pour l'orchestrateur principal
  - Conservation exacte de la logique actuelle (aucun refactor)
  - Mise à jour des libellés : "🚀 Orchestrateur du bot (filters + WebSocket prix)"
  - Message de statut : "🟢 Orchestrateur prêt (WS connectée, flux en cours)"
**Tests/commandes :** 
  - `python src/bot.py` → doit afficher les nouveaux titres et fonctionner identiquement
  - Vérification que `if __name__ == "__main__": main()` est présent
**Résultat :** ✅ OK (renommage réussi, comportement identique, documentation mise à jour)

## [2025-01-27] — Ajout du filtre de volatilité 5 minutes
**But :** Ajouter un filtre de volatilité 5 minutes pour éviter les paires trop instables avant l'entrée, déclenché seulement si funding T ≤ 5 min.
**Fichiers modifiés :** 
  - `src/config.py` - Ajout de VOLATILITY_MAX_5M (défaut 0.007 = 0.7%)
  - `src/volatility.py` - Nouveau module de calcul de volatilité
  - `src/bot.py` - Intégration du filtre dans le flux principal
  - `README.md` - Documentation de la nouvelle variable d'environnement
  - `JOURNAL.md` - Documentation du changement
**Décisions/raisons :**
  - Filtre basé sur la plage de prix (high-low) des 5 dernières bougies 1 minute
  - Activation conditionnelle : seulement si funding T ≤ 5 minutes (optimisation)
  - Cache TTL 60s pour éviter les recalculs inutiles
  - Gestion d'erreurs robuste avec fallback gracieux
  - Logs détaillés pour le debugging et le monitoring
**Fonctionnalités :**
  - Calcul automatique via API REST Bybit (endpoint kline)
  - Filtrage par seuil configurable (VOLATILITY_MAX_5M)
  - Cache en mémoire pour optimiser les performances
  - Logs pédagogiques avec comptes détaillés
**Tests/commandes :** 
  - `setx VOLATILITY_MAX_5M 0.007` (Windows) ou `export VOLATILITY_MAX_5M=0.007` (Linux/Mac)
  - `python src/bot.py` → vérifier les logs de volatilité pour les symboles proches du funding
  - Test d'import et de configuration réussi
**Résultat :** ✅ OK (filtre fonctionnel, intégration propre, documentation complète)

## [2025-01-27] — Amélioration du filtre de volatilité : support min/max et fichier parameters.yaml
**But :** Permettre le filtrage min/max de volatilité depuis le fichier YAML et renommer le fichier de configuration avec un nom plus approprié.
**Fichiers modifiés :** 
  - `src/watchlist_config.fr.yaml` → `src/parameters.yaml` (renommé)
  - `src/parameters.yaml` - Ajout de volatility_min et volatility_max
  - `src/config.py` - Support des variables VOLATILITY_MIN et VOLATILITY_MAX
  - `src/bot.py` - Mise à jour du filtre pour supporter min/max
  - `README.md` - Documentation du nouveau fichier et paramètres
  - `JOURNAL.md` - Documentation du changement
**Décisions/raisons :**
  - Nom de fichier plus générique : `parameters.yaml` au lieu de `watchlist_config.fr.yaml`
  - Support des bornes min et max pour la volatilité (plus flexible)
  - Priorité maintenue : ENV > YAML > valeurs par défaut
  - Logs améliorés avec affichage des seuils min/max
  - Gestion d'erreurs robuste avec fallback gracieux
**Fonctionnalités :**
  - Paramètres YAML : `volatility_min` et `volatility_max`
  - Variables d'environnement : `VOLATILITY_MIN` et `VOLATILITY_MAX`
  - Filtrage conditionnel : seulement si funding T ≤ 5 minutes
  - Logs détaillés : "seuils: min=0.20% | max=0.70%"
  - Support des rejets pour volatilité trop faible ou trop élevée
**Tests/commandes :** 
  - Configuration YAML testée : volatility_min=null, volatility_max=0.007
  - Variables d'environnement testées : VOLATILITY_MIN et VOLATILITY_MAX
  - Import et configuration du bot validés
**Résultat :** ✅ OK (système min/max fonctionnel, fichier renommé, documentation mise à jour)

## [2025-01-27] — Correction de l'affichage de la volatilité dans le tableau
**But :** Corriger l'affichage de la volatilité dans le tableau pour tous les symboles, pas seulement ceux avec funding T ≤ 5 min.
**Fichiers modifiés :** 
  - `src/bot.py` - Modification du filtre de volatilité et de l'affichage du tableau
  - `README.md` - Mise à jour de l'exemple d'affichage
  - `JOURNAL.md` - Documentation du changement
**Décisions/raisons :**
  - Problème identifié : la volatilité n'était calculée que pour les symboles avec funding T ≤ 5 min
  - Solution : calculer la volatilité pour tous les symboles, mais appliquer le filtre seulement pour ceux proches du funding
  - Affichage : la volatilité est maintenant visible dans le tableau pour tous les symboles
  - Logs améliorés : distinction entre filtrage et affichage
**Fonctionnalités :**
  - Calcul de volatilité pour tous les symboles (pour l'affichage)
  - Filtrage conditionnel : seulement si funding T ≤ 5 minutes
  - Logs détaillés : "📊 Volatilité 5m = X% → affiché SYMBOL (funding T > 5 min)"
  - Tableau mis à jour : colonne "Volatilité %" avec valeurs réelles
  - Cache TTL 60s pour optimiser les performances
**Tests/commandes :** 
  - Import du bot validé avec les nouvelles modifications
  - Tableau affiche maintenant la volatilité pour tous les symboles
  - Filtrage fonctionne toujours pour les symboles proches du funding
**Résultat :** ✅ OK (affichage de la volatilité corrigé, filtrage conditionnel maintenu)

## [2025-01-27] — Suppression de la condition de temps pour le filtre de volatilité
**But :** Supprimer la condition de temps (funding T ≤ 5 min) du filtre de volatilité pour l'appliquer à tous les symboles.
**Fichiers modifiés :** 
  - `src/bot.py` - Modification de la fonction `filter_by_volatility`
  - `JOURNAL.md` - Documentation du changement
**Décisions/raisons :**
  - Demande utilisateur : garder le filtre de volatilité mais enlever la condition sur le temps de funding
  - Simplification : le filtre s'applique maintenant à tous les symboles, peu importe leur temps de funding
  - Logique maintenue : calcul et affichage de la volatilité pour tous les symboles
**Fonctionnalités :**
  - Filtre de volatilité appliqué à tous les symboles (sans condition de temps)
  - Logs simplifiés : "🔎 Volatilité 5m = X% → OK SYMBOL" ou "⚠️ Volatilité 5m = X% > seuil max Y% → rejeté SYMBOL"
  - Message de log mis à jour : "🔎 Évaluation de la volatilité 5m pour tous les symboles…"
  - Cache TTL 60s maintenu pour optimiser les performances
**Tests/commandes :** 
  - Import du bot validé avec les nouvelles modifications
  - Test en conditions réelles : 2 symboles rejetés (MYXUSDT 4.37%, AVNTUSDT 5.89%) car volatilité > 0.70%
  - 8 symboles gardés avec volatilité ≤ 0.70%
  - Tableau affiche correctement la volatilité pour tous les symboles
**Résultat :** ✅ OK (filtre de volatilité simplifié, appliqué à tous les symboles)

## [2025-09-16] — Alignement documentation ↔ code (ENV, TTL, fenêtre funding, supervision)
**But :** Aligner toute la documentation avec le code actuel (ENV, YAML, pagination 1000, async volatilité avec semaphore=5, rate limiter public).
**Fichiers modifiés :** 
- `README.md` — Démarrage, YAML, variables ENV (incluant `FUNDING_TIME_MIN_MINUTES`, `FUNDING_TIME_MAX_MINUTES`, `VOLATILITY_TTL_SEC`, rate limiter public), structure, commandes, config avancée
- `CONTRIBUTING.md` — Checklist pointant `python src/bot.py` comme orchestrateur principal
- `OPTIMISATIONS_PERFORMANCE.md` — Pagination 1000, fallback spread, suppression des délais artificiels, async volatilité + semaphore
- `OPTIMISATIONS_VOLATILITE.md` — Concurrence plafonnée, temps indicatifs, rate limiter public
- `NETTOYAGE_CODE.md` — Architecture finale (REST → filtres → WS), checklist PR
**Tests/commandes :**
- `python src/bot.py` → vérification des logs de filtres (incluant ft_min/ft_max, vol_ttl)
- `python src/app.py` → supervision REST/WS public/privé OK
**Résultat :** ✅ OK (docs alignées au code, variables ENV à jour)

## [2025-01-27] — Ajout de la reconnexion automatique pour les WebSockets publiques
**But :** Corriger le problème critique où le bot s'arrêtait à la première coupure réseau de la WS publique, en ajoutant une logique de reconnexion avec backoff progressif.
**Fichiers modifiés :** 
- `src/bot.py` — Classe `PublicWSConnection` enrichie avec reconnexion automatique
**Décisions/raisons :**
- **Problème identifié** : `PublicWSConnection.run()` n'avait pas de logique de reconnexion, contrairement à `PrivateWSClient`
- **Solution** : Implémentation d'une boucle de reconnexion avec backoff progressif [1s, 2s, 5s, 10s, 30s]
- **Alignement** : Même logique que la WS privée pour la cohérence du code
- **Robustesse** : Réinitialisation de l'index de délai après connexion réussie
- **Logs clairs** : Messages informatifs pour le debugging et monitoring
**Fonctionnalités :**
- **Reconnexion automatique** : Boucle `while self.running` avec gestion d'exceptions
- **Backoff progressif** : Délais croissants jusqu'à 30s maximum
- **Restauration des abonnements** : Re-souscription automatique aux tickers après reconnexion
- **Arrêt propre** : Vérification périodique de `self.running` pendant les délais
- **Logs détaillés** : Messages de connexion, déconnexion, et reconnexion
**Tests/commandes :** 
- `python src/bot.py` → logs montrent : "🌐 WS ouverte (linear)" + "🧭 Souscription tickers → 299 symboles"
- Test de coupure réseau simulée → reconnexion automatique avec logs "🔁 WS publique (linear) déconnectée → reconnexion dans Xs"
**Résultat :** ✅ OK (reconnexion automatique fonctionnelle, bot stable en production)

## [2025-01-27] — Correction des blocages async dans le calcul de volatilité
**But :** Éliminer les micro-blocages dans l'event loop causés par l'utilisation de `time.sleep()` dans le rate limiter synchrone lors du calcul de volatilité asynchrone.
**Fichiers modifiés :** 
- `src/volatility.py` — Ajout d'`AsyncRateLimiter` et remplacement du rate limiter synchrone
**Décisions/raisons :**
- **Problème identifié** : `compute_volatility_batch_async()` appelait `rate_limiter.acquire()` qui utilisait `time.sleep()` bloquant dans du code async
- **Impact** : Micro-blocages dans l'event loop, latence variable, performance dégradée
- **Solution** : Création d'une version asynchrone du rate limiter avec `await asyncio.sleep()`
- **Cohérence** : Même logique de fenêtre glissante, mais non-bloquante
**Fonctionnalités :**
- **AsyncRateLimiter** : Rate limiter asynchrone avec `asyncio.Lock()` et `await asyncio.sleep()`
- **Fenêtre glissante** : Même comportement que le rate limiter synchrone (max_calls dans window_seconds)
- **Configuration ENV** : Utilise les mêmes variables `PUBLIC_HTTP_MAX_CALLS_PER_SEC` et `PUBLIC_HTTP_WINDOW_SECONDS`
- **Intégration transparente** : Remplacement direct dans `limited_task()` sans impact sur le reste du code
- **Performance** : Élimination des blocages, latence plus stable et prévisible
**Tests/commandes :** 
- `python src/bot.py` → logs montrent : "✅ Refresh volatilité terminé: ok=316 | fail=5" + retry automatique
- Calcul de volatilité fonctionne normalement sans blocages observables
- Performance améliorée : latence plus stable lors des cycles de volatilité
**Résultat :** ✅ OK (rate limiter asynchrone fonctionnel, event loop non-bloqué, performance améliorée)

## [2025-01-27] — Ajout de la validation de configuration
**But :** Empêcher le démarrage du bot avec des paramètres de configuration incohérents ou invalides, et fournir des messages d'erreur clairs pour faciliter le debugging.
**Fichiers modifiés :** 
- `src/bot.py` — Ajout de `validate_config()` et intégration dans `load_config()` et `start()`
**Décisions/raisons :**
- **Problème identifié** : Aucune validation des paramètres de configuration (YAML + ENV)
- **Risques** : Comportements silencieux avec des valeurs incohérentes (ex: `funding_min > funding_max`)
- **Solution** : Validation complète avec messages d'erreur explicites et arrêt propre
- **UX** : Messages clairs en français avec conseils pour corriger
**Fonctionnalités :**
- **Validation des bornes** : `funding_min ≤ funding_max`, `volatility_min ≤ volatility_max`
- **Validation des valeurs négatives** : Tous les paramètres numériques ≥ 0
- **Validation des plages** : Spread ≤ 100%, temps funding ≤ 24h, limite ≤ 1000, TTL volatilité 10s-1h
- **Validation des catégories** : `categorie` dans `["linear", "inverse", "both"]`
- **Validation des fenêtres temporelles** : `funding_time_min ≤ funding_time_max`
- **Messages d'erreur explicites** : Chaque erreur avec la valeur problématique et la règle violée
- **Arrêt propre** : `return` dans `start()` au lieu de `sys.exit()` brutal
**Tests/commandes :** 
- Configuration incohérente : `funding_time_max_minutes: 2000` → "trop élevé (2000), maximum: 1440 (24h)"
- Configuration incohérente : `funding_min: 0.01, funding_max: 0.005` → "ne peut pas être supérieur"
- Configuration valide : Bot démarre normalement avec logs de filtrage
- Messages clairs : "❌ Erreur de configuration" + "💡 Corrigez les paramètres dans src/parameters.yaml"
**Résultat :** ✅ OK (validation robuste fonctionnelle, messages d'erreur clairs, arrêt propre)

## [2025-01-27] — Nettoyage du code et suppression des imports inutilisés
**But :** Supprimer le code mort et les imports redondants pour améliorer la lisibilité et réduire la dette technique.
**Fichiers modifiés :** 
- `src/app.py` — Suppression de `_generate_ws_signature()` inutilisée et imports redondants
- `src/volatility.py` — Suppression des imports inutilisés (httpx, Tuple)
- `src/bot.py` — Remplacement de `sys.exit(0)` par `return` pour arrêt propre
**Décisions/raisons :**
- **Problème identifié** : Code mort et imports inutilisés dans plusieurs fichiers
- **Dette technique** : Méthodes non utilisées, imports redondants, arrêt brutal
- **Solution** : Nettoyage systématique sans casser la fonctionnalité
- **Qualité** : Code plus propre et maintenable
**Fonctionnalités supprimées :**
- **`_generate_ws_signature()`** : Méthode inutilisée dans `src/app.py` (doublon avec `ws_private.py`)
- **Imports redondants** : `json`, `hmac`, `hashlib` dans `src/app.py` (non utilisés)
- **Imports inutilisés** : `httpx`, `Tuple` dans `src/volatility.py` (non référencés)
- **Arrêt brutal** : `sys.exit(0)` remplacé par `return` dans `src/bot.py`
**Tests/commandes :** 
- `python src/bot.py` → démarrage normal avec logs de configuration
- Validation de la fonctionnalité : filtrage, WebSocket, calcul de volatilité
- Vérification des linters : aucune erreur détectée
- Logs confirmés : "🚀 Orchestrateur du bot (filters + WebSocket prix)" + "📂 Configuration chargée"
**Résultat :** ✅ OK (code nettoyé, fonctionnalité préservée, aucune régression)

## [2025-01-27] — Validation des variables d'environnement pour détecter les fautes de frappe
**But :** Détecter et signaler les variables d'environnement inconnues liées au bot pour aider à identifier les fautes de frappe dans la configuration.
**Fichiers modifiés :** 
- `src/config.py` — Ajout de la validation des variables d'environnement dans `get_settings()`
**Décisions/raisons :**
- **Problème identifié** : Variables ENV mal orthographiées ignorées silencieusement (ex: `CATEGROY` au lieu de `CATEGORY`)
- **Risques** : Configuration incorrecte non détectée, comportement inattendu du bot
- **Solution** : Validation proactive avec warnings explicites pour variables inconnues liées au bot
- **UX** : Messages d'aide avec liste des variables valides
**Fonctionnalités :**
- **Liste des variables valides** : Définition explicite des ENV supportées
- **Détection intelligente** : Filtrage des variables système pour éviter le spam
- **Filtrage par mots-clés** : Détection des variables liées au bot par analyse des noms
- **Warnings clairs** : Messages d'erreur explicites avec suggestions
- **Double sortie** : Affichage sur `stderr` + logger si disponible
- **Variables valides** : `BYBIT_API_KEY`, `BYBIT_API_SECRET`, `TESTNET`, `TIMEOUT`, `LOG_LEVEL`, `SPREAD_MAX`, `VOLUME_MIN_MILLIONS`, `VOLATILITY_MIN`, `VOLATILITY_MAX`, `FUNDING_MIN`, `FUNDING_MAX`, `CATEGORY`, `LIMIT`, `VOLATILITY_TTL_SEC`, `FUNDING_TIME_MIN_MINUTES`, `FUNDING_TIME_MAX_MINUTES`, `WS_PRIV_CHANNELS`
- **Filtrage système** : Ignore les variables Windows/Python (`PATH`, `PYTHON`, etc.)
- **Filtrage par mots-clés** : Détecte les variables contenant `BYBIT`, `FUNDING`, `VOLATILITY`, `SPREAD`, `VOLUME`, `CATEGORY`, etc.
**Implémentation :**
```python
# Validation des variables d'environnement dans get_settings()
valid_env_vars = {
    "BYBIT_API_KEY", "BYBIT_API_SECRET", "TESTNET", "TIMEOUT", "LOG_LEVEL",
    "SPREAD_MAX", "VOLUME_MIN_MILLIONS", "VOLATILITY_MIN", "VOLATILITY_MAX",
    "FUNDING_MIN", "FUNDING_MAX", "CATEGORY", "LIMIT", "VOLATILITY_TTL_SEC",
    "FUNDING_TIME_MIN_MINUTES", "FUNDING_TIME_MAX_MINUTES", "WS_PRIV_CHANNELS"
}

# Détecter et signaler les variables inconnues liées au bot
bot_related_unknown = []
for var in (set(os.environ.keys()) - valid_env_vars):
    if not any(prefix in var.upper() for prefix in SYSTEM_PREFIXES):
        if any(keyword in var.upper() for keyword in BOT_KEYWORDS):
            bot_related_unknown.append(var)

# Afficher warnings pour variables inconnues
if bot_related_unknown:
    for var in bot_related_unknown:
        print(f"⚠️ Variable d'environnement inconnue ignorée: {var}", file=sys.stderr)
        print(f"💡 Variables valides: {', '.join(sorted(valid_env_vars))}", file=sys.stderr)
```
**Tests/commandes :** 
- Test avec variable correcte : `CATEGORY=linear` → Aucun warning, fonctionne normalement
- Test avec faute de frappe : `CATEGROY=linear` → Warning affiché avec liste des variables valides
- Test avec variable système : `PYTHONPATH=/path` → Ignorée silencieusement (correct)
- Messages d'aide : Liste complète des variables d'environnement supportées
**Résultat :** ✅ OK (validation implémentée, détection des fautes de frappe, messages d'aide clairs)

---

## 🧩 Modèle d'entrée à réutiliser
### [AAAA-MM-JJ] — Titre court de la modification
**But :** (en une phrase, simple)
**Fichiers modifiés :** (liste)
**Décisions/raisons :** (bullets courtes)
**Tests/commandes :** (cmds exactes + résultat attendu)
**Risques/limitations :** (si pertinents)
**Prochaines étapes :** (1–3 bullets max)

---
