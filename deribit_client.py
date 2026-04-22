"""Deribit API Client - Options market data"""
import logging
import json
from typing import Optional
from datetime import datetime

import requests
import pandas as pd

logger = logging.getLogger(__name__)


class DeribitClient:
    """
    Client for Deribit's REST API to fetch crypto options data.
    
    Deribit is the primary exchange for BTC and ETH options.
    Free API provides:
    - Option instruments and ticker data
    - Order book snapshots
    - Historical volatility
    - Index prices
    
    No authentication required for public data endpoints.
    """
    
    def __init__(self, config: dict = None):
        config = config or {}
        self.base_url = config.get("deribit_url", "https://www.deribit.com/api/v2")
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "VolSurfaceScanner/1.0"
        })
        self._instruments_cache: dict = {}
    
    def _api_call(self, method: str, params: dict = None) -> Optional[dict]:
        """Make a Deribit API v2 call"""
        try:
            url = f"{self.base_url}/public/{method}"
            resp = self.session.get(url, params=params or {}, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("success"):
                return data.get("result")
            else:
                error = data.get("error", {})
                logger.warning(f"Deribit API error: {error.get('message', 'unknown')}")
                return None
        except Exception as e:
            logger.error(f"Deribit API call failed ({method}): {e}")
            return None
    
    def get_index_price(self, currency: str = "BTC") -> Optional[float]:
        """Get current index price"""
        result = self._api_call("get_index_price", {"currency": currency})
        if result:
            return float(result.get("index_price", 0))
        return None
    
    def get_option_instruments(self, currency: str = "BTC") -> list:
        """Get all available option instruments"""
        if currency in self._instruments_cache:
            return self._instruments_cache[currency]
        
        result = self._api_call("get_instruments", {
            "currency": currency,
            "kind": "option",
            "expired": "false"
        })
        
        if result:
            self._instruments_cache[currency] = result
            logger.info(f"Fetched {len(result)} {currency} option instruments")
            return result
        
        return []
    
    def get_option_ticker(self, instrument_name: str) -> Optional[dict]:
        """Get ticker data for a specific option"""
        result = self._api_call("ticker", {"instrument_name": instrument_name})
        return result
    
    def get_options_chain(self, currency: str = "BTC") -> pd.DataFrame:
        """
        Get the full options chain with current market data.
        
        Returns DataFrame with: instrument_name, strike, expiry, option_type,
        bid, ask, mid, mark_price, underlying_price, iv, volume, open_interest
        """
        instruments = self.get_option_instruments(currency)
        
        if not instruments:
            return pd.DataFrame()
        
        rows = []
        for inst in instruments:
            try:
                name = inst.get("instrument_name", "")
                # Parse instrument name: BTC-28MAR25-80000-C
                parts = name.split("-")
                if len(parts) != 4:
                    continue
                
                underlying = parts[0]
                expiry_str = parts[1]
                strike = float(parts[2])
                option_type = "call" if parts[3] == "C" else "put"
                
                # Calculate time to expiry
                try:
                    expiry_date = datetime.strptime(expiry_str, "%d%b%y")
                    now = datetime.now()
                    T = max((expiry_date - now).days / 365.0, 0.001)
                except ValueError:
                    # Try alternative date format
                    T = 0.1
                
                row = {
                    "instrument_name": name,
                    "currency": underlying,
                    "strike": strike,
                    "expiry": expiry_str,
                    "expiry_date": expiry_date if 'expiry_date' in dir() else None,
                    "expiry_years": T,
                    "option_type": option_type,
                    "is_active": inst.get("is_active", False),
                    "contract_size": inst.get("contract_size", 1),
                    "tick_size": inst.get("tick_size", 0.0005),
                }
                
                rows.append(row)
                
            except Exception as e:
                logger.debug(f"Failed to parse instrument {inst.get('instrument_name', '?')}: {e}")
                continue
        
        df = pd.DataFrame(rows)
        
        if df.empty:
            return df
        
        # Fetch tickers for active instruments (batch) - limit to avoid rate limits
        active = df[df["is_active"] == True] if "is_active" in df.columns else df
        logger.info(f"Fetching tickers for {len(active)} active instruments...")
        
        ticker_data = []
        for _, row in active.head(50).iterrows():  # Limit to 50 to avoid rate limits
            try:
                ticker = self.get_option_ticker(row["instrument_name"])
                if ticker:
                    ticker_data.append({
                        "instrument_name": row["instrument_name"],
                        "bid": ticker.get("best_bid_price"),
                        "ask": ticker.get("best_ask_price"),
                        "mid": ticker.get("mid_price"),
                        "mark_price": ticker.get("mark_price"),
                        "underlying_price": ticker.get("underlying_price"),
                        "iv": ticker.get("mark_iv"),
                        "volume": ticker.get("stats", {}).get("volume", 0) if isinstance(ticker.get("stats"), dict) else 0,
                        "open_interest": ticker.get("open_interest", 0),
                        "last_price": ticker.get("last_price"),
                    })
            except Exception as e:
                logger.debug(f"Ticker fetch failed for {row['instrument_name']}: {e}")
                continue
        
        if ticker_data:
            ticker_df = pd.DataFrame(ticker_data)
            df = df.merge(ticker_df, on="instrument_name", how="left")
        
        logger.info(f"Options chain: {len(df)} instruments, {len(ticker_data)} with market data")
        return df
    
    def get_historical_volatility(self, currency: str = "BTC") -> Optional[float]:
        """Get current historical (realized) volatility"""
        result = self._api_call("get_historical_volatility", {"currency": currency})
        if result and len(result) > 0:
            # Returns [1w, 1m, 3m, 6m, 1y] volatilities
            try:
                val = result[-2]
                return float(val) / 100 if val else None
            except (IndexError, TypeError, ValueError):
                return None
        return None
    
    def get_summary(self, currency: str = "BTC") -> dict:
        """Get a summary of the current options market"""
        try:
            index_price = self.get_index_price(currency)
        except Exception:
            index_price = None
        
        try:
            hist_vol = self.get_historical_volatility(currency)
        except Exception:
            hist_vol = None
        
        try:
            instruments = self.get_option_instruments(currency)
        except Exception:
            instruments = []
        
        active_instruments = [i for i in instruments if i.get("is_active", False)]
        
        return {
            "currency": currency,
            "index_price": index_price,
            "historical_volatility": hist_vol,
            "total_instruments": len(instruments),
            "active_instruments": len(active_instruments),
            "timestamp": datetime.now().isoformat()
        }
