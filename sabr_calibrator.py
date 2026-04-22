"""SABR Volatility Model Calibrator"""
import logging
from typing import Optional

import numpy as np
from scipy.optimize import minimize

logger = logging.getLogger(__name__)


class SABRCalibrator:
    """
    SABR (Stochastic Alpha Beta Rho) volatility model calibrator.
    
    The SABR model captures the volatility smile/skew observed in options markets.
    It's widely used for:
    - Fitting the volatility surface
    - Interpolating/extrapolating volatilities
    - Pricing exotic options consistently with vanilla markets
    
    Hagan's approximation:
    sigma_impl(K,F,T) = alpha / (F*K)^((1-beta)/2) * 
        [1 + (1-beta)^2/24 * ln(F/K)^2 + (1-beta)^4/1920 * ln(F/K)^4] *
        z / x(z) * [1 + T * (rho*nu*alpha/(F*K)^((1-beta)/2) * 1/24 * 
        (2-3*rho^2)*nu^2/24 * alpha^2/(F*K)^(1-beta))]
    
    Parameters:
    - alpha: Controls overall vol level
    - beta: Controls backbone shape (0=normal, 1=lognormal)
    - rho: Correlation between spot and vol
    - nu: Volatility of volatility
    """
    
    def __init__(self, beta: float = 0.5):
        """
        Initialize SABR calibrator.
        
        Args:
            beta: Fixed beta parameter (commonly 0.5 for crypto)
        """
        self.beta = beta
    
    @staticmethod
    def sabr_volatility(alpha: float, beta: float, rho: float, nu: float,
                         F: float, K: float, T: float) -> float:
        """
        Calculate SABR implied volatility using Hagan's approximation.
        
        Args:
            alpha: SABR alpha parameter
            beta: SABR beta parameter
            rho: SABR rho parameter (correlation)
            nu: SABR nu parameter (vol of vol)
            F: Forward price
            K: Strike price
            T: Time to expiry in years
        
        Returns:
            Implied volatility
        """
        if T <= 0 or F <= 0 or K <= 0 or alpha <= 0:
            return 0.0
        
        try:
            z = (nu / alpha) * (F * K) ** ((1 - beta) / 2) * np.log(F / K)
            
            if abs(z) < 1e-8:
                # ATM approximation
                x = 1.0
            else:
                x = np.log((np.sqrt(1 - 2 * rho * z + z ** 2) + z - rho) / (1 - rho))
            
            FK_beta = (F * K) ** ((1 - beta) / 2)
            log_FK = np.log(F / K)
            
            # First term
            term1 = alpha / FK_beta
            
            # Second term (if not ATM)
            if abs(z) < 1e-8:
                term2 = 1.0
            else:
                term2 = z / x
            
            # Third term (correction)
            term3_num = (1 - beta) ** 2 / 24 * log_FK ** 2 + (1 - beta) ** 4 / 1920 * log_FK ** 4
            term3 = 1 + term3_num
            
            # Fourth term (time correction)
            term4_num1 = rho * beta * nu / (24 * alpha) * FK_beta
            term4_num2 = (2 - 3 * rho ** 2) / 24 * nu ** 2
            term4 = 1 + T * (term4_num1 + term4_num2)
            
            sigma = term1 * term2 * term3 * term4
            
            return max(sigma, 0.001)  # Floor at 0.1%
            
        except Exception as e:
            logger.debug(f"SABR calculation error: {e}")
            return 0.0
    
    def calibrate(self, strikes: np.ndarray, implied_vols: np.ndarray, 
                  forward: float, time_to_expiry: float,
                  initial_guess: Optional[tuple] = None) -> Optional[dict]:
        """
        Calibrate SABR parameters to market implied volatilities.
        
        Args:
            strikes: Array of strike prices
            implied_vols: Array of market implied volatilities
            forward: Forward price
            time_to_expiry: Time to expiry in years
            initial_guess: (alpha, rho, nu) starting point
        
        Returns:
            Dict with calibrated parameters and fit metrics, or None if calibration fails
        """
        if len(strikes) == 0 or len(implied_vols) == 0:
            return None
        
        if len(strikes) != len(implied_vols):
            logger.error("Strikes and vols must have same length")
            return None
        
        # Filter out invalid data
        valid_mask = (strikes > 0) & (implied_vols > 0) & np.isfinite(implied_vols)
        strikes = strikes[valid_mask]
        implied_vols = implied_vols[valid_mask]
        
        if len(strikes) < 3:
            logger.warning("Not enough valid data points for calibration")
            return None
        
        # Initial guess
        if initial_guess is None:
            # Rough initial estimate for alpha from ATM vol
            atm_idx = np.argmin(np.abs(strikes - forward))
            atm_vol = implied_vols[atm_idx]
            alpha_init = atm_vol * forward ** (1 - self.beta)
            rho_init = -0.3
            nu_init = 0.5
        else:
            alpha_init, rho_init, nu_init = initial_guess
        
        # Objective function: minimize squared errors
        def objective(params):
            alpha, rho, nu = params
            if alpha <= 0 or nu <= 0 or abs(rho) >= 1:
                return 1e10
            
            model_vols = np.array([
                self.sabr_volatility(alpha, self.beta, rho, nu, forward, K, time_to_expiry)
                for K in strikes
            ])
            
            errors = model_vols - implied_vols
            return np.sum(errors ** 2)
        
        # Bounds
        bounds = [
            (0.001, 10.0),    # alpha
            (-0.999, 0.999),  # rho
            (0.001, 5.0),     # nu
        ]
        
        try:
            result = minimize(
                objective,
                x0=[alpha_init, rho_init, nu_init],
                method='L-BFGS-B',
                bounds=bounds,
                options={'maxiter': 500, 'ftol': 1e-10}
            )
            
            if result.success or result.fun < 1e-4:
                alpha, rho, nu = result.x
                
                # Calculate fit metrics
                model_vols = np.array([
                    self.sabr_volatility(alpha, self.beta, rho, nu, forward, K, time_to_expiry)
                    for K in strikes
                ])
                
                residuals = model_vols - implied_vols
                rmse = np.sqrt(np.mean(residuals ** 2))
                max_error = np.max(np.abs(residuals))
                
                return {
                    "alpha": alpha,
                    "beta": self.beta,
                    "rho": rho,
                    "nu": nu,
                    "rmse": rmse,
                    "max_error": max_error,
                    "model_vols": model_vols,
                    "residuals": residuals,
                    "success": result.success
                }
            else:
                logger.warning(f"SABR calibration did not converge: {result.message}")
                return None
                
        except Exception as e:
            logger.error(f"SABR calibration error: {e}")
            return None
    
    def surface_interpolation(self, calibrated_params: dict, 
                               forward: float, K: float, T: float) -> float:
        """
        Interpolate volatility at any (K, T) point using calibrated SABR params.
        
        Args:
            calibrated_params: Dict from calibrate()
            forward: Forward price
            K: Strike price
            T: Time to expiry in years
        
        Returns:
            Interpolated implied volatility
        """
        return self.sabr_volatility(
            calibrated_params["alpha"],
            calibrated_params["beta"],
            calibrated_params["rho"],
            calibrated_params["nu"],
            forward, K, T
        )
