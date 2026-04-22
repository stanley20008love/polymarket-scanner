"""Cross-Market Arbitrage Scanner - Detects pricing inconsistencies across related markets"""
import logging
from typing import Optional
import re

from models import OrderSide, Market, ArbitrageOpportunity, ArbitrageType
from fee_calculator import FeeCalculator

logger = logging.getLogger(__name__)


class CrossMarketScanner:
    """
    Scans for arbitrage between different markets that reference the same underlying event.
    
    Example: 
    Market A: "Will Trump win 2024?" YES = $0.55
    Market B: "Will Trump lose 2024?" YES = $0.50
    → Buy A YES ($0.55) + B YES ($0.50) = $1.05 for guaranteed $1.00 = LOSS
    → But if A NO = $0.45 and B YES = $0.50, buy A NO + B YES = $0.95 → guaranteed $1.00
    """
    
    def __init__(self, fee_calculator: FeeCalculator, min_profit_threshold: float = 0.02):
        self.fee_calculator = fee_calculator
        self.min_profit_threshold = min_profit_threshold
    
    def scan_market_pairs(self, markets: list[Market]) -> list[ArbitrageOpportunity]:
        """Find cross-market arbitrage between all market pairs"""
        opportunities = []
        
        # Group markets by topic/keywords for efficient scanning
        market_groups = self._group_by_topic(markets)
        
        for topic, group_markets in market_groups.items():
            if len(group_markets) < 2:
                continue
            
            # Check all pairs within the group
            for i in range(len(group_markets)):
                for j in range(i + 1, len(group_markets)):
                    try:
                        opp = self._check_cross_market(group_markets[i], group_markets[j])
                        if opp and opp.is_profitable:
                            opportunities.append(opp)
                    except Exception as e:
                        logger.debug(f"Error checking cross-market pair: {e}")
                        continue
        
        opportunities.sort(key=lambda x: x.profit_percentage, reverse=True)
        return opportunities
    
    def _check_cross_market(self, market_a: Market, market_b: Market) -> Optional[ArbitrageOpportunity]:
        """Check two markets for cross-market arbitrage"""
        if not market_a.outcome_prices or not market_b.outcome_prices:
            return None
        
        if len(market_a.outcome_prices) < 2 or len(market_b.outcome_prices) < 2:
            return None
        
        # Strategy 1: Buy A_YES + B_YES (if they cover complementary outcomes)
        # If A and B are truly complementary, one must be YES
        cost_complement = market_a.outcome_prices[0] + market_b.outcome_prices[0]
        
        # Strategy 2: Buy A_YES + B_NO (if they represent same event)
        cost_same = market_a.outcome_prices[0] + market_b.outcome_prices[1]
        
        # Strategy 3: Buy A_NO + B_YES (inverse of Strategy 2)
        cost_inverse = market_a.outcome_prices[1] + market_b.outcome_prices[0]
        
        # Find the minimum cost strategy that guarantees $1 payout
        strategies = [
            ("complementary", cost_complement, 
             [("buy", market_a, 0), ("buy", market_b, 0)]),
            ("same_direction", cost_same, 
             [("buy", market_a, 0), ("buy", market_b, 1)]),
            ("inverse_direction", cost_inverse, 
             [("buy", market_a, 1), ("buy", market_b, 0)]),
        ]
        
        best_opp = None
        best_profit = 0
        
        for strategy_name, cost, legs_spec in strategies:
            if cost >= 1.0:
                continue
            
            gross_profit = 1.0 - cost
            
            # Build legs
            legs = []
            total_fees = 0.0
            for action, market, outcome_idx in legs_spec:
                price = market.outcome_prices[outcome_idx]
                outcome = market.outcomes[outcome_idx] if outcome_idx < len(market.outcomes) else f"Outcome_{outcome_idx}"
                
                leg = {
                    "market_condition_id": market.condition_id,
                    "outcome": outcome,
                    "side": "buy",
                    "price": price,
                    "size": 1.0,
                    "is_maker": True,
                    "strategy": strategy_name
                }
                legs.append(leg)
                
                fee = self.fee_calculator.calculate_trade_fee(price, 1.0, OrderSide.BUY, is_neg_risk=False)
                total_fees += fee
            
            net_profit = gross_profit - total_fees
            profit_pct = net_profit / cost if cost > 0 else 0
            
            if profit_pct > best_profit and profit_pct >= self.min_profit_threshold:
                best_profit = profit_pct
                confidence = self._calculate_confidence(market_a, market_b, net_profit)
                
                best_opp = ArbitrageOpportunity(
                    arbitrage_type=ArbitrageType.CROSS_MARKET,
                    markets=[market_a, market_b],
                    expected_profit=net_profit,
                    profit_percentage=profit_pct,
                    investment_required=cost,
                    confidence=confidence,
                    description=(
                        f"Cross-market arb ({strategy_name}): "
                        f"'{market_a.question[:30]}...' + '{market_b.question[:30]}...' "
                        f"Cost=${cost:.4f}, Net profit=${net_profit:.4f}"
                    ),
                    legs=legs
                )
        
        return best_opp
    
    def _group_by_topic(self, markets: list[Market]) -> dict[str, list[Market]]:
        """Group markets by common topics/keywords"""
        groups: dict[str, list[Market]] = {}
        
        for market in markets:
            keywords = self._extract_keywords(market.question)
            
            # Use the first significant keyword as group key
            for kw in keywords:
                if len(kw) > 3:  # Skip short words
                    if kw not in groups:
                        groups[kw] = []
                    groups[kw].append(market)
                    break  # Only add to first matching group
        
        # Filter groups with only one market
        return {k: v for k, v in groups.items() if len(v) >= 2}
    
    def _extract_keywords(self, text: str) -> list[str]:
        """Extract significant keywords from market question"""
        stop_words = {"will", "the", "a", "an", "in", "on", "at", "by", "for", 
                      "of", "to", "and", "or", "is", "are", "be", "it", "this",
                      "that", "before", "after", "above", "below", "more", "less"}
        
        # Remove punctuation and split
        words = re.findall(r'\b\w+\b', text.lower())
        keywords = [w for w in words if w not in stop_words and len(w) > 2]
        
        return keywords
    
    def _calculate_confidence(self, market_a: Market, market_b: Market, 
                              net_profit: float) -> float:
        """Calculate confidence for cross-market arbitrage"""
        confidence = 0.3  # Lower base confidence (cross-market is riskier)
        
        # Higher profit = more room for error
        if net_profit > 0.05:
            confidence += 0.2
        elif net_profit > 0.03:
            confidence += 0.15
        elif net_profit > 0.01:
            confidence += 0.1
        
        # Liquidity check
        min_liquidity = min(market_a.liquidity, market_b.liquidity)
        if min_liquidity > 5000:
            confidence += 0.15
        elif min_liquidity > 1000:
            confidence += 0.1
        
        return min(confidence, 0.85)
