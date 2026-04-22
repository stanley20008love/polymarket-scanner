"""Polymarket CLOB API Client - Market data fetching"""
import asyncio
import logging
from typing import Optional
from datetime import datetime

import requests

# aiohttp is optional - only needed for async operations
try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

from models import Market, OrderBook, MarketType

logger = logging.getLogger(__name__)


class PolymarketClient:
    """Client for interacting with Polymarket CLOB and Gamma APIs"""
    
    def __init__(self, config: dict):
        self.clob_url = config.get("polymarket_clob_url", "https://clob.polymarket.com")
        self.gamma_url = config.get("polymarket_gamma_url", "https://gamma-api.polymarket.com")
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "PolymarketScanner/1.0"
        })
        self._async_session = None
    
    async def _get_async_session(self):
        if not HAS_AIOHTTP:
            raise RuntimeError("aiohttp not installed - async operations not available")
        if self._async_session is None or self._async_session.closed:
            self._async_session = aiohttp.ClientSession(
                headers={"Accept": "application/json", "User-Agent": "PolymarketScanner/1.0"}
            )
        return self._async_session
    
    def get_active_markets(self, limit: int = 100, offset: int = 0) -> list:
        """Fetch active markets from Gamma API"""
        markets = []
        try:
            params = {
                "active": "true",
                "closed": "false",
                "limit": limit,
                "offset": offset,
                "order": "volume",
                "ascending": "false"
            }
            resp = self.session.get(f"{self.gamma_url}/markets", params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            
            for item in data:
                try:
                    market = self._parse_market(item)
                    if market and market.active:
                        markets.append(market)
                except Exception as e:
                    logger.debug(f"Failed to parse market: {e}")
                    continue
                    
            logger.info(f"Fetched {len(markets)} active markets")
        except Exception as e:
            logger.error(f"Failed to fetch markets: {e}")
        
        return markets
    
    async def get_active_markets_async(self, limit: int = 100, offset: int = 0) -> list:
        """Async version of get_active_markets"""
        if not HAS_AIOHTTP:
            # Fallback to sync
            return self.get_active_markets(limit, offset)
        
        markets = []
        try:
            session = await self._get_async_session()
            params = {
                "active": "true",
                "closed": "false",
                "limit": limit,
                "offset": offset,
                "order": "volume",
                "ascending": "false"
            }
            async with session.get(f"{self.gamma_url}/markets", params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp.raise_for_status()
                data = await resp.json()
                
                for item in data:
                    try:
                        market = self._parse_market(item)
                        if market and market.active:
                            markets.append(market)
                    except Exception as e:
                        logger.debug(f"Failed to parse market: {e}")
                        continue
                        
                logger.info(f"Fetched {len(markets)} active markets (async)")
        except Exception as e:
            logger.error(f"Failed to fetch markets (async): {e}")
        
        return markets
    
    def get_market_orderbook(self, token_id: str) -> Optional[OrderBook]:
        """Fetch order book for a specific token"""
        try:
            resp = self.session.get(
                f"{self.clob_url}/book",
                params={"token_id": token_id},
                timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
            
            bids = [(float(b["price"]), float(b["size"])) for b in data.get("bids", [])]
            asks = [(float(a["price"]), float(a["size"])) for a in data.get("asks", [])]
            
            return OrderBook(
                condition_id=token_id,
                outcome="",
                bids=sorted(bids, key=lambda x: -x[0]),
                asks=sorted(asks, key=lambda x: x[0]),
                timestamp=datetime.now()
            )
        except Exception as e:
            logger.debug(f"Failed to fetch orderbook for {token_id}: {e}")
            return None
    
    def get_market_prices(self, token_id: str) -> Optional[dict]:
        """Get current prices for a market token"""
        try:
            resp = self.session.get(
                f"{self.clob_url}/midpoint",
                params={"token_id": token_id},
                timeout=10
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.debug(f"Failed to fetch price for {token_id}: {e}")
            return None
    
    def get_neg_risk_markets(self, slug: str = None) -> list:
        """Fetch NegRisk markets (mutually exclusive outcome groups)"""
        markets = []
        try:
            params = {"active": "true", "closed": "false"}
            if slug:
                params["slug"] = slug
            
            resp = self.session.get(f"{self.gamma_url}/markets", params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            
            for item in data:
                try:
                    market = self._parse_market(item)
                    if market and market.active:
                        neg_risk = item.get("neg_risk", False)
                        if neg_risk:
                            market.market_type = MarketType.NEG_RISK
                            markets.append(market)
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"Failed to fetch NegRisk markets: {e}")
        
        return markets
    
    def _parse_market(self, item: dict) -> Optional[Market]:
        """Parse a market from Gamma API response"""
        try:
            outcomes = item.get("outcomes", "[]")
            if isinstance(outcomes, str):
                import json
                outcomes = json.loads(outcomes)
            
            outcome_prices = item.get("outcomePrices", "[]")
            if isinstance(outcome_prices, str):
                import json
                outcome_prices = json.loads(outcome_prices)
            
            outcome_prices = [float(p) for p in outcome_prices]
            
            return Market(
                condition_id=item.get("conditionId", ""),
                question=item.get("question", ""),
                outcomes=outcomes if isinstance(outcomes, list) else [outcomes],
                outcome_prices=outcome_prices,
                volume=float(item.get("volume", 0)),
                liquidity=float(item.get("liquidity", 0)),
                end_date=item.get("endDate"),
                active=item.get("active", False),
                market_type=MarketType.NEG_RISK if item.get("neg_risk", False) else MarketType.BINARY,
                slug=item.get("slug", ""),
                category=item.get("category", "")
            )
        except Exception as e:
            logger.debug(f"Market parse error: {e}")
            return None
    
    def close(self):
        """Clean up resources"""
        self.session.close()
    
    async def close_async(self):
        """Clean up async resources"""
        if HAS_AIOHTTP and self._async_session and not self._async_session.closed:
            await self._async_session.close()
