"""Black-Scholes Option Pricing Model"""
import logging
import math
from typing import Optional

import numpy as np
from scipy.stats import norm

logger = logging.getLogger(__name__)


class BlackScholes:
    """
    Black-Scholes option pricing model for European options.
    
    Used for:
    - Pricing options on crypto assets (BTC, ETH)
    - Calculating implied volatility
    - Computing Greeks for risk management
    """
    
    @staticmethod
    def d1(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Calculate d1 parameter"""
        if T <= 0 or sigma <= 0:
            return 0.0
        return (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    
    @staticmethod
    def d2(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Calculate d2 parameter"""
        if T <= 0 or sigma <= 0:
            return 0.0
        return BlackScholes.d1(S, K, T, r, sigma) - sigma * math.sqrt(T)
    
    @staticmethod
    def call_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Calculate European call option price"""
        if T <= 0:
            return max(S - K, 0.0)
        if sigma <= 0:
            return max(S - K * math.exp(-r * T), 0.0)
        
        d1 = BlackScholes.d1(S, K, T, r, sigma)
        d2 = BlackScholes.d2(S, K, T, r, sigma)
        
        return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    
    @staticmethod
    def put_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Calculate European put option price"""
        if T <= 0:
            return max(K - S, 0.0)
        if sigma <= 0:
            return max(K * math.exp(-r * T) - S, 0.0)
        
        d1 = BlackScholes.d1(S, K, T, r, sigma)
        d2 = BlackScholes.d2(S, K, T, r, sigma)
        
        return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    
    @staticmethod
    def implied_volatility(market_price: float, S: float, K: float, T: float, 
                           r: float, option_type: str = "call", 
                           tol: float = 1e-6, max_iter: int = 100) -> Optional[float]:
        """
        Calculate implied volatility using Newton-Raphson method.
        
        Args:
            market_price: Observed market price of the option
            S: Current spot price
            K: Strike price
            T: Time to expiration (in years)
            r: Risk-free rate
            option_type: "call" or "put"
            tol: Convergence tolerance
            max_iter: Maximum iterations
        
        Returns:
            Implied volatility or None if convergence fails
        """
        if T <= 0 or market_price <= 0:
            return None
        
        # Initial guess
        sigma = 0.3  # Start with 30% vol
        
        price_func = BlackScholes.call_price if option_type == "call" else BlackScholes.put_price
        
        for i in range(max_iter):
            try:
                price = price_func(S, K, T, r, sigma)
                vega = BlackScholes.vega(S, K, T, r, sigma)
                
                if abs(vega) < 1e-10:
                    logger.debug("Vega too small, cannot converge")
                    return None
                
                diff = price - market_price
                
                if abs(diff) < tol:
                    return sigma
                
                sigma = sigma - diff / vega
                
                # Prevent negative or zero sigma
                if sigma <= 0.001:
                    sigma = 0.001
                    
            except Exception:
                return None
        
        logger.debug(f"IV did not converge after {max_iter} iterations")
        return None
    
    # === GREEKS ===
    
    @staticmethod
    def delta(S: float, K: float, T: float, r: float, sigma: float, 
              option_type: str = "call") -> float:
        """Calculate option delta"""
        if T <= 0 or sigma <= 0:
            if option_type == "call":
                return 1.0 if S > K else 0.0
            else:
                return -1.0 if S < K else 0.0
        
        d1 = BlackScholes.d1(S, K, T, r, sigma)
        if option_type == "call":
            return norm.cdf(d1)
        else:
            return norm.cdf(d1) - 1
    
    @staticmethod
    def gamma(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Calculate option gamma"""
        if T <= 0 or sigma <= 0:
            return 0.0
        d1 = BlackScholes.d1(S, K, T, r, sigma)
        return norm.pdf(d1) / (S * sigma * math.sqrt(T))
    
    @staticmethod
    def theta(S: float, K: float, T: float, r: float, sigma: float,
              option_type: str = "call") -> float:
        """Calculate option theta (daily)"""
        if T <= 0 or sigma <= 0:
            return 0.0
        d1 = BlackScholes.d1(S, K, T, r, sigma)
        d2 = BlackScholes.d2(S, K, T, r, sigma)
        
        term1 = -(S * norm.pdf(d1) * sigma) / (2 * math.sqrt(T))
        
        if option_type == "call":
            term2 = -r * K * math.exp(-r * T) * norm.cdf(d2)
        else:
            term2 = r * K * math.exp(-r * T) * norm.cdf(-d2)
        
        return (term1 + term2) / 365  # Daily theta
    
    @staticmethod
    def vega(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Calculate option vega (per 1% move in vol)"""
        if T <= 0 or sigma <= 0:
            return 0.0
        d1 = BlackScholes.d1(S, K, T, r, sigma)
        return S * norm.pdf(d1) * math.sqrt(T) / 100
    
    @staticmethod
    def rho(S: float, K: float, T: float, r: float, sigma: float,
            option_type: str = "call") -> float:
        """Calculate option rho (per 1% move in rate)"""
        if T <= 0 or sigma <= 0:
            return 0.0
        d2 = BlackScholes.d2(S, K, T, r, sigma)
        if option_type == "call":
            return K * T * math.exp(-r * T) * norm.cdf(d2) / 100
        else:
            return -K * T * math.exp(-r * T) * norm.cdf(-d2) / 100
    
    @staticmethod
    def all_greeks(S: float, K: float, T: float, r: float, sigma: float,
                   option_type: str = "call") -> dict:
        """Calculate all Greeks at once"""
        return {
            "delta": BlackScholes.delta(S, K, T, r, sigma, option_type),
            "gamma": BlackScholes.gamma(S, K, T, r, sigma),
            "theta": BlackScholes.theta(S, K, T, r, sigma, option_type),
            "vega": BlackScholes.vega(S, K, T, r, sigma),
            "rho": BlackScholes.rho(S, K, T, r, sigma, option_type),
        }
