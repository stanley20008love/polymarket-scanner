"""Volatility Surface Builder - Constructs and visualizes the full vol surface"""
import logging
from typing import Optional

import numpy as np
import pandas as pd

from black_scholes import BlackScholes
from sabr_calibrator import SABRCalibrator

logger = logging.getLogger(__name__)


class VolatilitySurface:
    """
    Builds a complete volatility surface from options market data.
    
    The surface maps (Strike, Time-to-Expiry) → Implied Volatility
    using SABR calibration for smooth interpolation.
    """
    
    def __init__(self, beta: float = 0.5, risk_free_rate: float = 0.05):
        self.bs = BlackScholes()
        self.sabr = SABRCalibrator(beta=beta)
        self.risk_free_rate = risk_free_rate
        self._calibrated_slices: dict[float, dict] = {}  # T → calibrated params
    
    def compute_implied_vols(self, options_data: pd.DataFrame) -> pd.DataFrame:
        """
        Compute implied volatilities from options market data.
        
        Expected columns: spot, strike, expiry_years, option_type, market_price
        """
        results = []
        
        for _, row in options_data.iterrows():
            S = row["spot"]
            K = row["strike"]
            T = row["expiry_years"]
            opt_type = row.get("option_type", "call")
            market_price = row["market_price"]
            
            iv = self.bs.implied_volatility(
                market_price, S, K, T, self.risk_free_rate, opt_type
            )
            
            results.append({
                "strike": K,
                "expiry_years": T,
                "option_type": opt_type,
                "market_price": market_price,
                "implied_vol": iv,
                "spot": S
            })
        
        df = pd.DataFrame(results)
        # Remove NaN IVs
        df = df.dropna(subset=["implied_vol"])
        
        logger.info(f"Computed {len(df)} implied volatilities from {len(options_data)} options")
        return df
    
    def calibrate_surface(self, iv_data: pd.DataFrame, spot: float) -> dict:
        """
        Calibrate SABR parameters for each expiry slice.
        
        Args:
            iv_data: DataFrame with columns: strike, expiry_years, implied_vol
            spot: Current spot price (used as forward)
        
        Returns:
            Dict mapping expiry → calibrated SABR params
        """
        self._calibrated_slices = {}
        
        for T, group in iv_data.groupby("expiry_years"):
            strikes = group["strike"].values
            vols = group["implied_vol"].values
            
            if len(strikes) < 3:
                logger.warning(f"Skipping T={T:.4f}: only {len(strikes)} strikes")
                continue
            
            params = self.sabr.calibrate(
                strikes=strikes,
                implied_vols=vols,
                forward=spot,
                time_to_expiry=T
            )
            
            if params:
                self._calibrated_slices[T] = params
                logger.info(
                    f"Calibrated T={T:.4f}: alpha={params['alpha']:.4f}, "
                    f"rho={params['rho']:.4f}, nu={params['nu']:.4f}, "
                    f"RMSE={params['rmse']:.6f}"
                )
            else:
                logger.warning(f"Calibration failed for T={T:.4f}")
        
        return self._calibrated_slices
    
    def get_volatility(self, K: float, T: float, forward: float) -> Optional[float]:
        """
        Get interpolated volatility at any (K, T) point.
        
        If exact T exists, use that slice's SABR params.
        Otherwise, interpolate between nearest calibrated slices.
        """
        if T in self._calibrated_slices:
            return self.sabr.surface_interpolation(
                self._calibrated_slices[T], forward, K, T
            )
        
        # Find nearest calibrated expiries for interpolation
        calibrated_Ts = sorted(self._calibrated_slices.keys())
        
        if not calibrated_Ts:
            return None
        
        if T <= calibrated_Ts[0]:
            return self.sabr.surface_interpolation(
                self._calibrated_slices[calibrated_Ts[0]], forward, K, T
            )
        
        if T >= calibrated_Ts[-1]:
            return self.sabr.surface_interpolation(
                self._calibrated_slices[calibrated_Ts[-1]], forward, K, T
            )
        
        # Linear interpolation between slices
        for i in range(len(calibrated_Ts) - 1):
            T1, T2 = calibrated_Ts[i], calibrated_Ts[i + 1]
            if T1 <= T <= T2:
                vol1 = self.sabr.surface_interpolation(
                    self._calibrated_slices[T1], forward, K, T
                )
                vol2 = self.sabr.surface_interpolation(
                    self._calibrated_slices[T2], forward, K, T
                )
                
                # Linear interpolation
                w = (T - T1) / (T2 - T1)
                return vol1 * (1 - w) + vol2 * w
        
        return None
    
    def generate_surface_grid(self, forward: float, 
                               K_range: tuple = None,
                               T_range: tuple = None,
                               n_K: int = 50, n_T: int = 20) -> pd.DataFrame:
        """
        Generate a regular grid of volatilities for visualization.
        
        Returns DataFrame with columns: strike, expiry_years, implied_vol
        """
        if not self._calibrated_slices:
            logger.warning("No calibrated slices available")
            return pd.DataFrame()
        
        calibrated_Ts = sorted(self._calibrated_slices.keys())
        
        if K_range is None:
            # Derive from calibrated data
            all_strikes = []
            for params in self._calibrated_slices.values():
                pass  # Would need original strikes
            K_range = (forward * 0.5, forward * 2.0)
        
        if T_range is None:
            T_range = (calibrated_Ts[0], calibrated_Ts[-1])
        
        strikes = np.linspace(K_range[0], K_range[1], n_K)
        expiries = np.linspace(T_range[0], T_range[1], n_T)
        
        rows = []
        for T in expiries:
            for K in strikes:
                vol = self.get_volatility(K, T, forward)
                if vol and np.isfinite(vol) and vol > 0:
                    rows.append({
                        "strike": K,
                        "expiry_years": T,
                        "implied_vol": vol,
                        "forward": forward
                    })
        
        df = pd.DataFrame(rows)
        logger.info(f"Generated surface grid: {len(df)} points")
        return df
    
    def get_surface_summary(self) -> dict:
        """Get summary statistics of the calibrated surface"""
        if not self._calibrated_slices:
            return {"status": "no data"}
        
        return {
            "num_slices": len(self._calibrated_slices),
            "expiries": sorted(self._calibrated_slices.keys()),
            "params": {
                f"T={T:.4f}": {
                    "alpha": p["alpha"],
                    "rho": p["rho"],
                    "nu": p["nu"],
                    "rmse": p["rmse"]
                }
                for T, p in self._calibrated_slices.items()
            }
        }
