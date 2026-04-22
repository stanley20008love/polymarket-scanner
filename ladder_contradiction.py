"""Ladder Contradiction Scanner - Detects pricing contradictions across price ladder levels"""
import logging
from typing import Optional

from models import Market, ArbitrageOpportunity, ArbitrageType
from fee_calculator import FeeCalculator

logger = logging.getLogger(__name__)


class LadderContradictionScanner:
    """
    Scans for contradictions in ladder-style prediction markets.
    
    In a ladder market (e.g., "BTC above $100k", "BTC above $80k", "BTC above $60k"),
    if a higher threshold is priced higher than a lower threshold, there's a contradiction.
    
    Example: "BTC > $100k" at $0.30 but "BTC > $80k" at $0.25 → Contradiction!
    If BTC > $100k, it must also be > $80k. So P(BTC>80k) >= P(BTC>100k).
    """
    
    def __init__(self, fee_calculator: FeeCalculator, min_profit_threshold: float = 0.02):
        self.fee_calculator = fee_calculator
        self.min_profit_threshold = min_profit_threshold
    
    def scan_ladder_group(self, markets: list[Market]) -> list[ArbitrageOpportunity]:
        """
        Scan a group of ladder markets for contradictions.
        Markets should be related (same underlying event, different thresholds).
        """
        if len(markets) < 2:
            return []
        
        # Sort by implied threshold (we'll try to detect from question text)
        sorted_markets = self._sort_by_threshold(markets)
        
        opportunities = []
        
        for i in range(len(sorted_markets) - 1):
            lower_market = sorted_markets[i]      # Lower threshold
            higher_market = sorted_markets[i + 1]  # Higher threshold
            
            opp = self._check_pair(lower_market, higher_market)
            if opp and opp.is_profitable:
                opportunities.append(opp)
        
        return opportunities
    
    def _check_pair(self, lower: Market, higher: Market) -> Optional[ArbitrageOpportunity]:
        """
        Check a pair of ladder markets for contradiction.
        
        If higher threshold is priced higher than lower threshold:
        Buy the lower threshold YES and sell the higher threshold YES
        (or buy higher NO and lower YES)
        """
        if not lower.outcome_prices or not higher.outcome_prices:
            return None
        
        # Get YES prices
        lower_yes = lower.outcome_prices[0] if lower.outcome_prices else 0
        higher_yes = higher.outcome_prices[0] if higher.outcome_prices else 0
        
        # Contradiction: higher threshold has higher YES price than lower threshold
        if higher_yes <= lower_yes:
            return None  # No contradiction - this is normal
        
        # The contradiction amount
        contradiction = higher_yes - lower_yes
        
        # Strategy: Buy lower YES at lower_yes, sell higher YES at higher_yes
        # If the event happens at the higher threshold, both settle to $1
        # If only at lower threshold, lower YES = $1, higher YES = $0
        # If neither, both = $0
        
        # Best case: Both settle YES → Profit from spread
        # Worst case: Only lower settles → Profit from lower YES, loss on higher short
        # Contradiction case: Higher settles but lower doesn't → Guaranteed profit
        
        # Simple arbitrage: Buy lower YES and higher NO
        # Cost: lower_yes + (1 - higher_yes) = 1 + lower_yes - higher_yes
        # If lower happens: lower YES = $1, higher NO could be $0 or $1
        # Guaranteed: At least one of {lower YES, higher NO} must pay $1
        
        cost = lower_yes + (1 - higher_yes)  # Buy lower YES + Buy higher NO
        guaranteed_payout = 1.0  # At least $1 guaranteed
        
        if cost >= guaranteed_payout:
            return None
        
        gross_profit = guaranteed_payout - cost
        
        # Calculate fees
        legs = [
            {
                "market_condition_id": lower.condition_id,
                "outcome": lower.outcomes[0] if lower.outcomes else "YES",
                "side": "buy",
                "price": lower_yes,
                "size": 1.0,
                "is_maker": True
            },
            {
                "market_condition_id": higher.condition_id,
                "outcome": higher.outcomes[-1] if higher.outcomes and len(higher.outcomes) > 1 else "NO",
                "side": "buy",
                "price": 1 - higher_yes,
                "size": 1.0,
                "is_maker": True
            }
        ]
        
        total_fees = sum(
            self.fee_calculator.calculate_trade_fee(leg["price"], leg["size"], is_neg_risk=False)
            for leg in legs
        )
        
        net_profit = gross_profit - total_fees
        profit_percentage = net_profit / cost if cost > 0 else 0
        
        if profit_percentage < self.min_profit_threshold:
            return None
        
        confidence = self._calculate_confidence(lower, higher, contradiction)
        
        return ArbitrageOpportunity(
            arbitrage_type=ArbitrageType.LADDER_CONTRADICTION,
            markets=[lower, higher],
            expected_profit=net_profit,
            profit_percentage=profit_percentage,
            investment_required=cost,
            confidence=confidence,
            description=(
                f"Ladder contradiction: '{lower.question[:40]}...' YES=${lower_yes:.4f} vs "
                f"'{higher.question[:40]}...' YES=${higher_yes:.4f}. "
                f"Buy lower YES + higher NO for ${cost:.4f}, guaranteed $1.00."
            ),
            legs=legs
        )
    
    def _sort_by_threshold(self, markets: list[Market]) -> list[Market]:
        """Attempt to sort markets by their implied threshold (lower first)"""
        import re
        
        def extract_number(market: Market) -> float:
            # Try to extract a dollar amount or percentage from the question
            numbers = re.findall(r'\$?([\d,]+\.?\d*)%?', market.question)
            if numbers:
                try:
                    return float(numbers[0].replace(',', ''))
                except ValueError:
                    pass
            # Fall back to price ordering (lower YES price → lower threshold)
            return market.outcome_prices[0] if market.outcome_prices else 0
        
        return sorted(markets, key=extract_number)
    
    def _calculate_confidence(self, lower: Market, higher: Market, contradiction: float) -> float:
        """Calculate confidence for ladder contradiction"""
        confidence = 0.4  # Base confidence (lower than exclusive outcome)
        
        # Larger contradiction = higher confidence
        if contradiction > 0.10:
            confidence += 0.2
        elif contradiction > 0.05:
            confidence += 0.15
        elif contradiction > 0.02:
            confidence += 0.1
        
        # Higher liquidity
        avg_liquidity = (lower.liquidity + higher.liquidity) / 2
        if avg_liquidity > 5000:
            confidence += 0.15
        elif avg_liquidity > 1000:
            confidence += 0.1
        
        # Higher volume
        avg_volume = (lower.volume + higher.volume) / 2
        if avg_volume > 50000:
            confidence += 0.1
        
        return min(confidence, 0.9)
