"""Exclusive Outcome Arbitrage Scanner - Detects when sum of outcomes < $1"""
import logging
from typing import Optional

from models import Market, ArbitrageOpportunity, ArbitrageType
from fee_calculator import FeeCalculator

logger = logging.getLogger(__name__)


class ExclusiveOutcomeScanner:
    """
    Scans for arbitrage in mutually exclusive outcome markets.
    
    In a binary market: if YES + NO < 1.0, buy both for guaranteed profit.
    In a multi-outcome market: if sum of all outcomes < 1.0, buy all.
    
    Example: YES = $0.48, NO = $0.48 → Total = $0.96 → Buy both for $0.96, guaranteed $1.00 = $0.04 profit
    """
    
    def __init__(self, fee_calculator: FeeCalculator, min_profit_threshold: float = 0.02):
        self.fee_calculator = fee_calculator
        self.min_profit_threshold = min_profit_threshold
    
    def scan_market(self, market: Market) -> Optional[ArbitrageOpportunity]:
        """Scan a single market for exclusive outcome arbitrage"""
        if not market.outcome_prices or len(market.outcome_prices) < 2:
            return None
        
        total_prob = market.total_probability
        
        # The gap is our potential profit per $1
        gap = 1.0 - total_prob
        
        if gap <= 0:
            # No arbitrage - outcomes sum to >= 1.0
            return None
        
        logger.debug(f"Market '{market.question[:50]}...' gap: ${gap:.4f} (total: ${total_prob:.4f})")
        
        # Calculate investment and profit
        investment = total_prob  # Cost to buy one of each outcome
        gross_profit = gap       # Guaranteed payout minus cost
        
        # Calculate fees for each leg
        legs = []
        total_fees = 0.0
        for i, (outcome, price) in enumerate(zip(market.outcomes, market.outcome_prices)):
            size = 1.0  # Buy $1 worth of each outcome
            leg = {
                "market_condition_id": market.condition_id,
                "outcome": outcome,
                "side": "buy",
                "price": price,
                "size": size,
                "is_maker": True  # Assume maker orders
            }
            legs.append(leg)
            
            fee = self.fee_calculator.calculate_trade_fee(
                price, size, is_neg_risk=(market.market_type.value == "neg_risk")
            )
            total_fees += fee
        
        net_profit = gross_profit - total_fees
        profit_percentage = net_profit / investment if investment > 0 else 0
        
        if profit_percentage < self.min_profit_threshold:
            return None
        
        # Calculate confidence based on liquidity and gap size
        confidence = self._calculate_confidence(market, gap)
        
        opportunity = ArbitrageOpportunity(
            arbitrage_type=ArbitrageType.EXCLUSIVE_OUTCOME,
            markets=[market],
            expected_profit=net_profit,
            profit_percentage=profit_percentage,
            investment_required=investment,
            confidence=confidence,
            description=self._generate_description(market, gap, net_profit),
            legs=legs
        )
        
        return opportunity
    
    def scan_markets(self, markets: list[Market]) -> list[ArbitrageOpportunity]:
        """Scan multiple markets for exclusive outcome arbitrage"""
        opportunities = []
        
        for market in markets:
            try:
                opp = self.scan_market(market)
                if opp and opp.is_profitable:
                    opportunities.append(opp)
                    logger.info(
                        f"FOUND: Exclusive outcome arb in '{market.question[:40]}...' "
                        f"Net profit: ${opp.expected_profit:.4f} ({opp.profit_percentage:.2%})"
                    )
            except Exception as e:
                logger.debug(f"Error scanning market {market.condition_id}: {e}")
                continue
        
        # Sort by profit percentage descending
        opportunities.sort(key=lambda x: x.profit_percentage, reverse=True)
        return opportunities
    
    def _calculate_confidence(self, market: Market, gap: float) -> float:
        """Calculate confidence score for the arbitrage opportunity"""
        confidence = 0.5  # Base confidence
        
        # Higher liquidity = higher confidence
        if market.liquidity > 10000:
            confidence += 0.2
        elif market.liquidity > 1000:
            confidence += 0.1
        
        # Larger gap = higher confidence (less likely to be measurement error)
        if gap > 0.05:
            confidence += 0.15
        elif gap > 0.03:
            confidence += 0.1
        elif gap > 0.01:
            confidence += 0.05
        
        # Higher volume = higher confidence (market is active)
        if market.volume > 100000:
            confidence += 0.1
        elif market.volume > 10000:
            confidence += 0.05
        
        return min(confidence, 0.95)  # Cap at 0.95
    
    def _generate_description(self, market: Market, gap: float, net_profit: float) -> str:
        """Generate human-readable description"""
        prices_str = ", ".join(
            f"{o}=${p:.4f}" for o, p in zip(market.outcomes, market.outcome_prices)
        )
        return (
            f"Exclusive outcome arb: Sum of outcomes = ${market.total_probability:.4f}, "
            f"Gap = ${gap:.4f}, Net profit = ${net_profit:.4f}. "
            f"Prices: [{prices_str}]"
        )
