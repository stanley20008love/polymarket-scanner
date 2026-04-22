"""Risk Manager - Position sizing and risk controls"""
import logging
from datetime import datetime, date
from typing import Optional

from models import ArbitrageOpportunity, Position, TradeExecution

logger = logging.getLogger(__name__)


class RiskManager:
    """Manages risk controls, position sizing, and exposure limits"""
    
    def __init__(self, config: dict):
        self.max_daily_loss = config.get("max_daily_loss", 50.0)
        self.max_open_positions = config.get("max_open_positions", 5)
        self.max_single_bet_pct = config.get("max_single_bet_percentage", 0.1)
        self.stop_loss_pct = config.get("stop_loss_percentage", 0.15)
        self.max_position_size = config.get("max_position_size", 100)
        
        self._daily_pnl: float = 0.0
        self._daily_loss: float = 0.0
        self._positions: list[Position] = []
        self._last_reset: date = date.today()
    
    def _reset_if_new_day(self):
        """Reset daily counters if it's a new day"""
        today = date.today()
        if today != self._last_reset:
            logger.info(f"New day detected. Resetting daily P&L from {self._daily_pnl:.2f}")
            self._daily_pnl = 0.0
            self._daily_loss = 0.0
            self._last_reset = today
    
    def can_take_trade(self, opportunity: ArbitrageOpportunity, 
                       bankroll: float = 500.0) -> tuple[bool, str]:
        """Check if a trade is allowed under risk rules"""
        self._reset_if_new_day()
        
        # Check daily loss limit
        if self._daily_loss >= self.max_daily_loss:
            return False, f"Daily loss limit reached: ${self._daily_loss:.2f} >= ${self.max_daily_loss:.2f}"
        
        # Check max open positions
        if len(self._positions) >= self.max_open_positions:
            return False, f"Max open positions reached: {len(self._positions)} >= {self.max_open_positions}"
        
        # Check position size relative to bankroll
        max_size = bankroll * self.max_single_bet_pct
        if opportunity.investment_required > max_size:
            return False, f"Investment ${opportunity.investment_required:.2f} exceeds max single bet ${max_size:.2f}"
        
        # Check absolute position size
        if opportunity.investment_required > self.max_position_size:
            return False, f"Investment ${opportunity.investment_required:.2f} exceeds max position size ${self.max_position_size:.2f}"
        
        # Check confidence level
        if opportunity.confidence < 0.5:
            return False, f"Confidence {opportunity.confidence:.2f} below minimum 0.50"
        
        # Check if the opportunity is actually profitable
        if not opportunity.is_profitable:
            return False, "Opportunity is not profitable after fees"
        
        return True, "Trade approved"
    
    def calculate_position_size(self, opportunity: ArbitrageOpportunity,
                                 bankroll: float = 500.0) -> float:
        """Calculate optimal position size using Kelly-like criterion"""
        # Simplified Kelly: f = (bp - q) / b
        # where b = net odds, p = probability of profit, q = 1 - p
        profit_pct = opportunity.profit_percentage
        confidence = opportunity.confidence
        
        if profit_pct <= 0 or confidence <= 0:
            return 0.0
        
        # Kelly fraction (half-Kelly for safety)
        kelly = (profit_pct * confidence - (1 - confidence)) / profit_pct
        half_kelly = kelly / 2
        
        # Apply constraints
        max_by_bankroll = bankroll * self.max_single_bet_pct
        position_size = min(half_kelly * bankroll, max_by_bankroll, self.max_position_size)
        
        # Minimum viable trade size
        position_size = max(position_size, 5.0)  # $5 minimum
        
        return round(position_size, 2)
    
    def add_position(self, position: Position):
        """Track a new position"""
        self._positions.append(position)
        logger.info(f"Added position: {position.outcome} @ ${position.entry_price:.4f}, size: {position.size}")
    
    def close_position(self, condition_id: str, close_price: float) -> Optional[float]:
        """Close a position and record P&L"""
        for i, pos in enumerate(self._positions):
            if pos.condition_id == condition_id:
                pnl = (close_price - pos.entry_price) * pos.size
                self._daily_pnl += pnl
                if pnl < 0:
                    self._daily_loss += abs(pnl)
                
                self._positions.pop(i)
                logger.info(f"Closed position: P&L = ${pnl:.4f}")
                return pnl
        
        return None
    
    def check_stop_losses(self, current_prices: dict[str, float]) -> list[str]:
        """Check if any positions hit stop-loss, return condition_ids to close"""
        to_close = []
        for pos in self._positions:
            if pos.condition_id in current_prices:
                current = current_prices[pos.condition_id]
                loss_pct = (pos.entry_price - current) / pos.entry_price
                if loss_pct >= self.stop_loss_pct:
                    logger.warning(f"Stop-loss triggered for {pos.condition_id}: {loss_pct:.2%}")
                    to_close.append(pos.condition_id)
        return to_close
    
    @property
    def daily_pnl(self) -> float:
        self._reset_if_new_day()
        return self._daily_pnl
    
    @property
    def open_positions(self) -> list[Position]:
        return self._positions.copy()
    
    @property
    def total_exposure(self) -> float:
        return sum(p.size * p.entry_price for p in self._positions)
    
    def get_status(self) -> dict:
        """Get current risk status"""
        self._reset_if_new_day()
        return {
            "daily_pnl": self._daily_pnl,
            "daily_loss": self._daily_loss,
            "max_daily_loss": self.max_daily_loss,
            "open_positions": len(self._positions),
            "max_open_positions": self.max_open_positions,
            "total_exposure": self.total_exposure,
            "remaining_daily_capacity": max(0, self.max_daily_loss - self._daily_loss)
        }
