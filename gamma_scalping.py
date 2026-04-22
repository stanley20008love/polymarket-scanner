"""Gamma Scalping Strategy - Delta-neutral options trading"""
import logging
from typing import Optional
from datetime import datetime

import numpy as np

from black_scholes import BlackScholes

logger = logging.getLogger(__name__)


class GammaScalper:
    """
    Gamma scalping strategy implementation.
    
    Core idea:
    1. Buy options (long gamma)
    2. Delta-hedge by trading the underlying
    3. Profit from realized volatility > implied volatility
    
    When the underlying moves:
    - Long gamma positions gain delta
    - We sell underlying to stay delta-neutral
    - When it moves back, we buy cheaper
    - Net effect: we "scalp" the oscillation
    
    Key metrics:
    - Gamma P&L = 0.5 * Gamma * (dS)^2
    - Theta cost = -Theta * dt
    - Net P&L = Gamma P&L + Theta cost
    """
    
    def __init__(self, risk_free_rate: float = 0.05):
        self.bs = BlackScholes()
        self.r = risk_free_rate
        self._positions: list[dict] = []
        self._hedge_history: list[dict] = []
    
    def analyze_opportunity(self, S: float, K: float, T: float, sigma_implied: float,
                            sigma_realized: float, position_size: float = 1.0,
                            option_type: str = "call") -> dict:
        """
        Analyze a gamma scalping opportunity.
        
        Args:
            S: Current spot price
            K: Strike price
            T: Time to expiry (years)
            sigma_implied: Implied volatility (what you pay)
            sigma_realized: Expected realized volatility (what you earn)
            position_size: Number of contracts
            option_type: "call" or "put"
        
        Returns:
            Analysis dict with Greeks, P&L projections, and recommendation
        """
        # Price the option
        if option_type == "call":
            option_price = self.bs.call_price(S, K, T, self.r, sigma_implied)
        else:
            option_price = self.bs.put_price(S, K, T, self.r, sigma_implied)
        
        # Calculate Greeks
        greeks = self.bs.all_greeks(S, K, T, self.r, sigma_implied, option_type)
        
        # Gamma P&L per day (assuming realized vol)
        # Expected daily move = sigma_realized * S / sqrt(252)
        daily_move = sigma_realized * S / np.sqrt(252)
        
        # Gamma P&L = 0.5 * Gamma * (dS)^2 * position_size
        gamma_pnl_daily = 0.5 * greeks["gamma"] * daily_move ** 2 * position_size * 100  # per contract
        
        # Theta cost per day
        theta_cost_daily = abs(greeks["theta"]) * position_size * 100
        
        # Net daily P&L
        net_daily_pnl = gamma_pnl_daily - theta_cost_daily
        
        # Breakeven realized vol
        # Gamma P&L = Theta → 0.5 * Gamma * (sigma_be * S / sqrt(252))^2 = Theta
        if greeks["gamma"] > 0:
            breakeven_vol = np.sqrt(abs(greeks["theta"]) * 2 * 252 / (greeks["gamma"] * S ** 2))
        else:
            breakeven_vol = float('inf')
        
        # Profit ratio
        vol_edge = sigma_realized - sigma_implied
        profit_ratio = gamma_pnl_daily / theta_cost_daily if theta_cost_daily > 0 else float('inf')
        
        # Total projected P&L over the option's life
        days_to_expiry = T * 365
        total_projected_pnl = net_daily_pnl * days_to_expiry * 0.5  # Discount for gamma decay
        total_cost = option_price * position_size * 100
        
        return {
            "option_price": option_price,
            "option_type": option_type,
            "strike": K,
            "expiry_years": T,
            "greeks": greeks,
            "gamma_pnl_daily": gamma_pnl_daily,
            "theta_cost_daily": theta_cost_daily,
            "net_daily_pnl": net_daily_pnl,
            "breakeven_vol": breakeven_vol,
            "implied_vol": sigma_implied,
            "realized_vol": sigma_realized,
            "vol_edge": vol_edge,
            "profit_ratio": profit_ratio,
            "total_projected_pnl": total_projected_pnl,
            "total_cost": total_cost,
            "roi": total_projected_pnl / total_cost if total_cost > 0 else 0,
            "recommendation": self._generate_recommendation(
                vol_edge, profit_ratio, breakeven_vol, sigma_realized
            )
        }
    
    def calculate_hedge_order(self, current_delta: float, target_delta: float = 0.0,
                               spot: float = 0.0, position_multiplier: float = 1.0) -> dict:
        """
        Calculate the hedge order needed to achieve target delta.
        
        Args:
            current_delta: Current portfolio delta
            target_delta: Desired delta (usually 0 for delta-neutral)
            spot: Current spot price
            position_multiplier: Size adjustment
        
        Returns:
            Hedge order details
        """
        delta_diff = current_delta - target_delta
        shares_to_trade = -delta_diff * position_multiplier * 100  # Convert to shares
        
        action = "BUY" if shares_to_trade > 0 else "SELL"
        notional = abs(shares_to_trade) * spot
        
        return {
            "action": action,
            "shares": abs(shares_to_trade),
            "price": spot,
            "notional": notional,
            "current_delta": current_delta,
            "target_delta": target_delta,
            "delta_after_hedge": target_delta
        }
    
    def simulate_scalping(self, S0: float, K: float, T: float, sigma_implied: float,
                           sigma_realized: float, option_type: str = "call",
                           n_steps: int = 252, position_size: float = 1.0) -> dict:
        """
        Monte Carlo simulation of gamma scalping strategy.
        
        Simulates price paths at realized vol and tracks P&L from
        delta rebalancing vs theta decay.
        """
        dt = T / n_steps
        np.random.seed(42)
        
        # Generate price path
        dW = np.random.normal(0, np.sqrt(dt), n_steps)
        log_returns = (0.0 - 0.5 * sigma_realized ** 2) * dt + sigma_realized * dW
        prices = S0 * np.exp(np.cumsum(log_returns))
        prices = np.insert(prices, 0, S0)
        
        total_gamma_pnl = 0.0
        total_theta_cost = 0.0
        total_hedge_cost = 0.0
        
        current_delta = self.bs.delta(S0, K, T, self.r, sigma_implied, option_type) * position_size * 100
        
        for i in range(1, len(prices)):
            S_prev = prices[i - 1]
            S_curr = prices[i]
            t_remaining = T - i * dt
            
            if t_remaining <= 0:
                break
            
            # Price change
            dS = S_curr - S_prev
            
            # Gamma P&L
            gamma = self.bs.gamma(S_prev, K, t_remaining + dt, self.r, sigma_implied)
            gamma_pnl = 0.5 * gamma * dS ** 2 * position_size * 100
            
            # Theta cost
            theta = self.bs.theta(S_prev, K, t_remaining + dt, self.r, sigma_implied, option_type)
            theta_cost = abs(theta * dt * position_size * 100)
            
            # Rebalance: calculate new delta and hedge
            new_delta = self.bs.delta(S_curr, K, t_remaining, self.r, sigma_implied, option_type) * position_size * 100
            hedge_shares = -(new_delta - current_delta)
            hedge_cost = hedge_shares * dS  # Approximate hedge cost
            
            total_gamma_pnl += gamma_pnl
            total_theta_cost += theta_cost
            total_hedge_cost += hedge_cost
            current_delta = new_delta
        
        # Option payoff at expiry
        S_final = prices[-1]
        if option_type == "call":
            payoff = max(S_final - K, 0) * position_size * 100
        else:
            payoff = max(K - S_final, 0) * position_size * 100
        
        option_premium = (self.bs.call_price(S0, K, T, self.r, sigma_implied) 
                          if option_type == "call" 
                          else self.bs.put_price(S0, K, T, self.r, sigma_implied))
        option_cost = option_premium * position_size * 100
        
        total_pnl = total_gamma_pnl - total_theta_cost + payoff - option_cost + total_hedge_cost
        
        return {
            "total_gamma_pnl": total_gamma_pnl,
            "total_theta_cost": total_theta_cost,
            "total_hedge_cost": total_hedge_cost,
            "option_payoff": payoff,
            "option_cost": option_cost,
            "total_pnl": total_pnl,
            "roi": total_pnl / option_cost if option_cost > 0 else 0,
            "final_price": S_final,
            "price_path": prices.tolist()
        }
    
    def _generate_recommendation(self, vol_edge: float, profit_ratio: float,
                                  breakeven_vol: float, realized_vol: float) -> str:
        """Generate a trading recommendation"""
        if vol_edge > 0.10 and profit_ratio > 1.5:
            return "STRONG BUY - High vol edge and favorable gamma/theta ratio"
        elif vol_edge > 0.05 and profit_ratio > 1.0:
            return "BUY - Positive vol edge, gamma covers theta"
        elif vol_edge > 0 and profit_ratio > 0.8:
            return "WEAK BUY - Marginal edge, monitor closely"
        elif vol_edge > 0:
            return "HOLD - Positive edge but theta too expensive"
        else:
            return "PASS - No volatility edge (realized < implied)"
