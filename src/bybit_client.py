"""Client Bybit pour les opérations synchrones avec authentification privée."""

import time
import hashlib
import hmac
import httpx
import random
from config import get_settings
from metrics import record_api_call
from http_client_manager import get_http_client


class BybitClient:
    """Client pour interagir avec l'API privée Bybit v5."""
    
    def __init__(
        self, 
        testnet: bool = True, 
        timeout: int = 10, 
        api_key: str | None = None, 
        api_secret: str | None = None
    ):
        """
        Initialise le client Bybit.
        
        Args:
            testnet (bool): Utiliser le testnet (True) ou le marché réel (False)
            timeout (int): Timeout pour les requêtes HTTP en secondes
            api_key (str | None): Clé API Bybit
            api_secret (str | None): Secret API Bybit
            
        Raises:
            RuntimeError: Si les clés API sont manquantes
        """
        if not api_key or not api_secret:
            raise RuntimeError("Clés API manquantes")
            
        self.testnet = testnet
        self.timeout = timeout
        self.api_key = api_key
        self.api_secret = api_secret
        
        # Définir l'URL de base selon l'environnement
        if testnet:
            self.base_url = "https://api-testnet.bybit.com"
        else:
            self.base_url = "https://api.bybit.com"
    
    def _get_private(self, path: str, params: dict = None) -> dict:
        """
        Effectue une requête GET privée authentifiée.
        
        Args:
            path (str): Chemin de l'endpoint
            params (dict): Paramètres de la requête
            
        Returns:
            dict: Réponse JSON de l'API
            
        Raises:
            RuntimeError: En cas d'erreur HTTP ou API
        """
        if params is None:
            params = {}
            
        # Générer timestamp et recv_window
        timestamp = int(time.time() * 1000)
        recv_window_ms = 10000
        
        # Créer la query string triée
        query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
        
        # Créer le payload pour la signature
        payload = f"{timestamp}{self.api_key}{recv_window_ms}{query_string}"
        
        # Générer la signature HMAC-SHA256
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Headers requis
        headers = {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-SIGN-TYPE": "2",
            "X-BAPI-TIMESTAMP": str(timestamp),
            "X-BAPI-RECV-WINDOW": str(recv_window_ms),
            "Content-Type": "application/json"
        }
        
        # Construire l'URL complète
        url = f"{self.base_url}{path}"
        if query_string:
            url += f"?{query_string}"
        
        attempts = 0
        max_attempts = 4
        backoff_base = 0.5
        last_error: Exception | None = None
        start_time = time.time()
        
        while attempts < max_attempts:
            attempts += 1
            try:
                client = get_http_client(timeout=self.timeout)
                response = client.get(url, headers=headers)
                
                # HTTP errors (4xx/5xx)
                if response.status_code >= 500:
                    raise httpx.HTTPStatusError("Server error", request=None, response=response)
                if response.status_code == 429:
                    # Respecter Retry-After si présent
                    retry_after = response.headers.get("Retry-After")
                    delay = (float(retry_after) if retry_after 
                            else backoff_base * (2 ** (attempts - 1)))
                    delay += random.uniform(0, 0.25)
                    time.sleep(delay)
                    continue
                if response.status_code >= 400:
                    # Erreurs client non récupérables
                    detail = response.text[:100]
                    raise RuntimeError(f"Erreur HTTP Bybit: status={response.status_code} detail=\"{detail}\"")
                
                data = response.json()
                
                # API retCode handling
                if data.get("retCode") != 0:
                    ret_code = data.get("retCode")
                    ret_msg = data.get("retMsg", "")
                    if ret_code in [10005, 10006]:
                        raise RuntimeError(
                            "Authentification échouée : clé/secret invalides ou signature incorrecte"
                        )
                    elif ret_code == 10018:
                        raise RuntimeError("Accès refusé : IP non autorisée (whitelist requise dans Bybit)")
                    elif ret_code == 10017:
                        raise RuntimeError(
                            "Horodatage invalide : horloge locale désynchronisée (corrige l'heure système)"
                        )
                    elif ret_code == 10016:
                        # Rate limit: backoff + jitter puis retry
                        retry_after = response.headers.get("Retry-After")
                        delay = (float(retry_after) if retry_after 
                                else backoff_base * (2 ** (attempts - 1)))
                        delay += random.uniform(0, 0.25)
                        time.sleep(delay)
                        if attempts < max_attempts:
                            continue
                        raise RuntimeError("Limite de requêtes atteinte : ralentis ou réessaie plus tard")
                    else:
                        raise RuntimeError(f"Erreur API Bybit : retCode={ret_code} retMsg=\"{ret_msg}\"")
                
                # Enregistrer les métriques de succès
                latency = time.time() - start_time
                record_api_call(latency, success=True)
                
                return data.get("result", {})
            except (httpx.TimeoutException, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                # Timeouts spécifiques - retry avec backoff
                last_error = e
                if attempts >= max_attempts:
                    break
                delay = backoff_base * (2 ** (attempts - 1)) + random.uniform(0, 0.25)
                time.sleep(delay)
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                # Autres erreurs réseau/HTTP - retry avec backoff
                last_error = e
                if attempts >= max_attempts:
                    break
                delay = backoff_base * (2 ** (attempts - 1)) + random.uniform(0, 0.25)
                time.sleep(delay)
            except (ValueError, TypeError, KeyError) as e:
                # Erreurs de données/parsing - pas de retry
                last_error = e
                break
            except Exception as e:
                # Erreur inattendue - propager si c'est une erreur formatée connue
                if "Erreur" in str(e):
                    raise
                last_error = e
                break
        # Enregistrer les métriques d'erreur
        latency = time.time() - start_time
        record_api_call(latency, success=False)
        
        # Échec après retries
        raise RuntimeError(f"Erreur réseau/HTTP Bybit : {last_error}")
    
    def public_base_url(self) -> str:
        """
        Retourne l'URL de base publique pour les endpoints sans authentification.
        
        Returns:
            str: URL de base publique (testnet ou mainnet)
        """
        if self.testnet:
            return "https://api-testnet.bybit.com"
        else:
            return "https://api.bybit.com"
    
    def get_wallet_balance(self, account_type: str = "UNIFIED") -> dict:
        """
        Récupère le solde du portefeuille.
        
        Args:
            account_type (str): Type de compte (défaut: UNIFIED)
            
        Returns:
            dict: Données brutes du solde
        """
        return self._get_private("/v5/account/wallet-balance", {"accountType": account_type})


class BybitPublicClient:
    """Client public Bybit v5 (aucune clé requise)."""

    def __init__(self, testnet: bool = True, timeout: int = 10):
        self.testnet = testnet
        self.timeout = timeout

    def public_base_url(self) -> str:
        """Retourne l'URL de base publique (testnet ou mainnet)."""
        if self.testnet:
            return "https://api-testnet.bybit.com"
        return "https://api.bybit.com"


def get_bybit_client() -> BybitClient:
    """
    Crée et retourne une instance de BybitClient configurée avec les paramètres du fichier .env.
    
    Returns:
        BybitClient: Instance configurée du client Bybit
        
    Raises:
        RuntimeError: Si les clés API sont manquantes
    """
    settings = get_settings()
    
    if not settings['api_key'] or not settings['api_secret']:
        raise RuntimeError("Clés API manquantes : ajoute BYBIT_API_KEY et BYBIT_API_SECRET dans .env")
    
    return BybitClient(
        testnet=settings['testnet'],
        timeout=settings['timeout'],
        api_key=settings['api_key'],
        api_secret=settings['api_secret']
    )
