#!/usr/bin/env python3
"""
Module de récupération de données Bybit pour la watchlist.

Ce module contient uniquement les fonctions pour récupérer les données
depuis l'API Bybit (REST et WebSocket) :
- Funding rates et volumes
- Spreads (bid/ask)
- Gestion des retCodes et pagination
- Rate limiting et gestion d'erreurs réseau
"""

import httpx
from typing import Dict, List, Optional
from http_utils import get_rate_limiter
from http_client_manager import get_http_client
from utils import compute_spread_with_mid_price


class WatchlistDataFetcher:
    """
    Classe dédiée à la récupération de données depuis l'API Bybit.
    
    Responsabilités :
    - Récupération des funding rates et volumes
    - Récupération des spreads
    - Gestion des erreurs API et réseau
    - Pagination et rate limiting
    """
    
    def __init__(self, logger=None):
        """
        Initialise le récupérateur de données.
        
        Args:
            logger: Logger pour les messages (optionnel)
        """
        self.logger = logger
    
    def fetch_funding_map(self, base_url: str, category: str, timeout: int = 10) -> Dict[str, Dict]:
        """
        Récupère les taux de funding pour une catégorie donnée.
        
        Args:
            base_url: URL de base de l'API Bybit
            category: Catégorie (linear ou inverse)
            timeout: Timeout pour les requêtes HTTP
            
        Returns:
            Dict[str, Dict]: Dictionnaire {symbol: {funding, volume, next_funding_time}}
            
        Raises:
            RuntimeError: En cas d'erreur HTTP ou API
        """
        funding_map = {}
        cursor = ""
        page_index = 0
        
        rate_limiter = get_rate_limiter()
        while True:
            # Construire l'URL avec pagination
            url = f"{base_url}/v5/market/tickers"
            params = {
                "category": category,
                "limit": 1000  # Limite maximum supportée par l'API Bybit
            }
            if cursor:
                params["cursor"] = cursor
                
            try:
                page_index += 1
                # Respecter le rate limit avant chaque appel
                rate_limiter.acquire()
                client = get_http_client(timeout=timeout)
                response = client.get(url, params=params)
                
                # Vérifier le statut HTTP
                if response.status_code >= 400:
                    raise RuntimeError(
                        f"Erreur HTTP Bybit GET {url} | category={category} limit={params.get('limit')} "
                        f"cursor={params.get('cursor', '-')} timeout={timeout}s page={page_index} "
                        f"collected={len(funding_map)} | status={response.status_code} "
                        f"detail=\"{response.text[:200]}\""
                    )
                
                data = response.json()
                
                # Vérifier le retCode
                if data.get("retCode") != 0:
                    ret_code = data.get("retCode")
                    ret_msg = data.get("retMsg", "")
                    raise RuntimeError(
                        f"Erreur API Bybit GET {url} | category={category} limit={params.get('limit')} "
                        f"cursor={params.get('cursor', '-')} timeout={timeout}s page={page_index} "
                        f"collected={len(funding_map)} | retCode={ret_code} retMsg=\"{ret_msg}\""
                    )
                
                result = data.get("result", {})
                tickers = result.get("list", [])
                
                # Extraire les funding rates, volumes et temps de funding
                for ticker in tickers:
                    symbol = ticker.get("symbol", "")
                    funding_rate = ticker.get("fundingRate")
                    volume_24h = ticker.get("volume24h")
                    next_funding_time = ticker.get("nextFundingTime")
                    
                    if symbol and funding_rate is not None:
                        try:
                            funding_map[symbol] = {
                                "funding": float(funding_rate),
                                "volume": float(volume_24h) if volume_24h is not None else 0.0,
                                "next_funding_time": next_funding_time
                            }
                        except (ValueError, TypeError):
                            # Ignorer si les données ne sont pas convertibles en float
                            pass
                
                # Vérifier s'il y a une page suivante
                next_page_cursor = result.get("nextPageCursor")
                if not next_page_cursor:
                    break
                cursor = next_page_cursor
                    
            except httpx.RequestError as e:
                raise RuntimeError(
                    f"Erreur réseau Bybit GET {url} | category={category} limit={params.get('limit')} "
                    f"cursor={params.get('cursor', '-')} timeout={timeout}s page={page_index} "
                    f"collected={len(funding_map)} | error={e}"
                )
            except Exception as e:
                if "Erreur" in str(e):
                    raise
                else:
                    raise RuntimeError(
                        f"Erreur inconnue Bybit GET {url} | category={category} limit={params.get('limit')} "
                        f"cursor={params.get('cursor', '-')} timeout={timeout}s page={page_index} "
                        f"collected={len(funding_map)} | error={e}"
                    )
        
        return funding_map
    
    def fetch_spread_data(self, base_url: str, symbols: List[str], timeout: int = 10, category: str = "linear") -> Dict[str, float]:
        """
        Récupère les spreads via /v5/market/tickers paginé, puis filtre localement.
        
        Args:
            base_url: URL de base de l'API Bybit
            symbols: Liste cible des symboles à retourner
            timeout: Timeout HTTP
            category: "linear" ou "inverse"
            
        Returns:
            Dict[str, float]: map {symbol: spread_pct}
        """
        wanted = set(symbols)
        found: Dict[str, float] = {}
        url = f"{base_url}/v5/market/tickers"
        params = {"category": category, "limit": 1000}
        cursor = ""
        page_index = 0
        rate_limiter = get_rate_limiter()
        
        while True:
            page_index += 1
            if cursor:
                params["cursor"] = cursor
            else:
                params.pop("cursor", None)
                
            try:
                rate_limiter.acquire()
                client = get_http_client(timeout=timeout)
                resp = client.get(url, params=params)
                
                if resp.status_code >= 400:
                    raise RuntimeError(
                        f"Erreur HTTP Bybit GET {url} | category={category} page={page_index} "
                        f"limit={params.get('limit')} cursor={params.get('cursor','-')} status={resp.status_code} "
                        f"detail=\"{resp.text[:200]}\""
                    )
                
                data = resp.json()
                if data.get("retCode") != 0:
                    raise RuntimeError(
                        f"Erreur API Bybit GET {url} | category={category} page={page_index} "
                        f"retCode={data.get('retCode')} retMsg=\"{data.get('retMsg','')}\""
                    )
                
                result = data.get("result", {})
                tickers = result.get("list", [])
                
                for t in tickers:
                    sym = t.get("symbol")
                    if sym in wanted:
                        bid1 = t.get("bid1Price")
                        ask1 = t.get("ask1Price")
                        try:
                            if bid1 is not None and ask1 is not None:
                                b = float(bid1)
                                a = float(ask1)
                                if b > 0 and a > 0:
                                    mid = (a + b) / 2
                                    if mid > 0:
                                        found[sym] = (a - b) / mid
                        except (ValueError, TypeError):
                            # Erreur de conversion numérique - ignorer silencieusement
                            pass
                
                # Fin pagination
                next_cursor = result.get("nextPageCursor")
                # Arrêt anticipé si on a tout trouvé
                if len(found) >= len(wanted):
                    break
                if not next_cursor:
                    break
                cursor = next_cursor
                
            except (httpx.RequestError, httpx.TimeoutException, httpx.HTTPStatusError) as e:
                if self.logger:
                    self.logger.error(
                        f"Erreur réseau spread paginé page={page_index} category={category}: {type(e).__name__}: {e}"
                    )
                break
            except (ValueError, TypeError, KeyError) as e:
                if self.logger:
                    self.logger.warning(
                        f"Erreur données spread paginé page={page_index} category={category}: {type(e).__name__}: {e}"
                    )
                break
            except Exception as e:
                if self.logger:
                    self.logger.error(
                        f"Erreur inattendue spread paginé page={page_index} category={category}: {type(e).__name__}: {e}"
                    )
                break
        
        # Fallback unitaire pour les symboles manquants
        missing = [s for s in symbols if s not in found]
        for s in missing:
            try:
                val = self._fetch_single_spread(base_url, s, timeout, category)
                if val is not None:
                    found[s] = val
            except (httpx.RequestError, ValueError, TypeError):
                # Erreurs réseau ou conversion - ignorer silencieusement pour le fallback
                pass
        
        return found
    
    def _fetch_single_spread(self, base_url: str, symbol: str, timeout: int, category: str) -> Optional[float]:
        """
        Récupère le spread pour un seul symbole.
        
        Args:
            base_url: URL de base de l'API Bybit
            symbol: Symbole à analyser
            timeout: Timeout pour les requêtes HTTP
            category: Catégorie des symboles ("linear" ou "inverse")
            
        Returns:
            Spread en pourcentage ou None si erreur
        """
        try:
            url = f"{base_url}/v5/market/tickers"
            params = {"category": category, "symbol": symbol}
            
            rate_limiter = get_rate_limiter()
            rate_limiter.acquire()
            client = get_http_client(timeout=timeout)
            response = client.get(url, params=params)
            
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Erreur HTTP Bybit GET {url} | category={category} symbol={symbol} "
                    f"timeout={timeout}s status={response.status_code} detail=\"{response.text[:200]}\""
                )
            
            data = response.json()
            
            if data.get("retCode") != 0:
                ret_code = data.get("retCode")
                ret_msg = data.get("retMsg", "")
                raise RuntimeError(
                    f"Erreur API Bybit GET {url} | category={category} symbol={symbol} "
                    f"timeout={timeout}s retCode={ret_code} retMsg=\"{ret_msg}\""
                )
            
            result = data.get("result", {})
            tickers = result.get("list", [])
            
            if not tickers:
                return None
            
            ticker = tickers[0]
            bid1_price = ticker.get("bid1Price")
            ask1_price = ticker.get("ask1Price")
            
            if bid1_price is not None and ask1_price is not None:
                spread_pct = compute_spread_with_mid_price(bid1_price, ask1_price)
                if spread_pct > 0:  # Seulement si le calcul a réussi
                    return spread_pct
            
            return None
            
        except Exception:
            return None
