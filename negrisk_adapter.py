"""NegRisk Adapter - Handles Polymarket's NegRisk (negative risk) market structure"""
import logging
from typing import Optional
from collections import defaultdict

from models import Market, ArbitrageOpportunity, ArbitrageType, MarketType
from fee_calculator import FeeCalculator

logger = logging.getLogger(__name__)


class NegRiskAdapter:
    """
    Adapter for Polymarket's NegRisk markets.
    
    NegRisk markets are groups of mutually exclusive outcomes where:
    - Each outcome token can be bought/sold independently
    - The "NO" token for each outcome is a composite of all other outcomes
    - This creates unique arbitrage opportunities not present in simple binary markets
    
    Key insight: In NegRisk markets, buying all outcome YES tokens should cost $1.00
    If total < $1.00, buying all outcomes guarantees profit.
    If total > $1.00, selling all outcomes guarantees profit.
    """
    
    def __init__(self, fee_calculator: FeeCalculator, min_profit_threshold: float = 0.02):
        self.fee_calculator = fee_calculator
        self.min_profit_threshold = min_profit_threshold
    
    def group_neg_risk_markets(self, markets: list[Market]) -> dict[str, list[Market]]:
        """Group NegRisk markets by their parent event/slug"""
        groups: dict[str, list[Market]] = defaultdict(list)
        
        for market in markets:
            if market.market_type == MarketType.NEG_RISK:
                # Use slug prefix as group key
                slug_parts = market.slug.split("-")
                if len(slug_parts) > 2:
                    group_key = "-".join(slug_parts[:3])  # Use first 3 parts as group
                else:
                    group_key = market.slug
                
                groups[group_key].append(market)
        
        return dict(groups)
    
    def scan_neg_risk_group(self, markets: list[Market]) -> list[ArbitrageOpportunity]:
        """Scan a group of NegRisk markets for arbitrage"""
        if len(markets) < 2:
            return []
        
        opportunities = []
        
        # Strategy 1: All YES sum < $1.00 → Buy all outcomes
        opp = self._scan_buy_all_yes(markets)
        if opp and opp.is_profitable:
            opportunities.append(opp)
        
        # Strategy 2: All YES sum > $1.00 → Sell all outcomes (buy all NO)
        opp = self._scan_sell_all_yes(markets)
        if opp and opp.is_profitable:
            opportunities.append(opp)
        
        # Strategy 3: Pairwise contradictions within the group
        pair_opps = self._scan_pairwise_contradictions(markets)
        opportunities.extend(pair_opps)
        
        return opportunities
    
    def _scan_buy_all_yes(self, markets: list[Market]) -> Optional[ArbitrageOpportunity]:
        """If sum of all YES prices < $1.00, buy all outcomes for guaranteed profit"""
        yes_prices = []
        for m in markets:
            if m.outcome_prices:
                yes_prices.append(m.outcome_prices[0])
            else:
                return None  # Missing price data
        
        total = sum(yes_prices)
        gap = 1.0 - total
        
        if gap <= 0:
            return None
        
        investment = total
        gross_profit = gap
        
        # Calculate fees (NegRisk markets have additional fees)
        legs = []
        total_fees = 0.0
        for i, market in enumerate(markets):
            price = yes_prices[i]
            leg = {
                "market_condition_id": market.condition_id,
                "outcome": market.outcomes[0] if market.outcomes else "YES",
                "side": "buy",
                "price": price,
                "size": 1.0,
                "is_maker": True,
                "is_neg_risk": True
            }
            legs.append(leg)
            fee = self.fee_calculator.calculate_trade_fee(price, 1.0, is_neg_risk=True)
            total_fees += fee
        
        net_profit = gross_profit - total_fees
        profit_pct = net_profit / investment if investment > 0 else 0
        
        if profit_pct < self.min_profit_threshold:
            return None
        
        confidence = self._calculate_neg_risk_confidence(markets, gap, len(markets))
        
        return ArbitrageOpportunity(
            arbitrage_type=ArbitrageType.NEG_RISK_HEDGE,
            markets=markets,
            expected_profit=net_profit,
            profit_percentage=profit_pct,
            investment_required=investment,
            confidence=confidence,
            description=(
                f"NegRisk buy-all: {len(markets)} outcomes sum to ${total:.4f}. "
                f"Gap: ${gap:.4f}, Net profit: ${net_profit:.4f} ({profit_pct:.2%})"
            ),
            legs=legs
        )
    
    def _scan_sell_all_yes(self, markets: list[Market]) -> Optional[ArbitrageOpportunity]:
        """If sum of all YES prices > $1.00, sell all outcomes (buy all NO) for profit"""
        yes_prices = []
        for m in markets:
            if m.outcome_prices:
                yes_prices.append(m.outcome_prices[0])
            else:
                return None
        
        total = sum(yes_prices)
        
        if total <= 1.0:
            return None
        
        # Sell all YES = buy all NO
        # Cost of buying all NO: sum of (1 - yes_price) for each outcome
        no_cost = sum(1 - p for p in yes_prices)
        guaranteed_payout = len(markets) - 1  # All but one NO will pay $1
        
        gross_profit = guaranteed_payout - no_cost
        
        if gross_profit <= 0:
            return None
        
        legs = []
        total_fees = 0.0
        for i, market in enumerate(markets):
            no_price = 1 - yes_prices[i]
            leg = {
                "market_condition_id": market.condition_id,
                "outcome": market.outcomes[1] if len(market.outcomes) > 1 else "NO",
                "side": "buy",
                "price": no_price,
                "size": 1.0,
                "is_maker": True,
                "is_neg_risk": True
            }
            legs.append(leg)
            fee = self.fee_calculator.calculate_trade_fee(no_price, 1.0, is_neg_risk=True)
            total_fees += fee
        
        net_profit = gross_profit - total_fees
        investment = no_cost
        profit_pct = net_profit / investment if investment > 0 else 0
        
        if profit_pct < self.min_profit_threshold:
            return None
        
        confidence = self._calculate_neg_risk_confidence(markets, total - 1.0, len(markets))
        
        return ArbitrageOpportunity(
            arbitrage_type=ArbitrageType.NEG_RISK_HEDGE,
            markets=markets,
            expected_profit=net_profit,
            profit_percentage=profit_pct,
            investment_required=investment,
            confidence=confidence,
            description=(
                f"NegRisk sell-all: {len(markets)} outcomes sum to ${total:.4f} (>$1.00). "
                f"Buy all NO for ${no_cost:.4f}, guaranteed ${guaranteed_payout:.2f}. "
                f"Net profit: ${net_profit:.4f}"
            ),
            legs=legs
        )
    
    def _scan_pairwise_contradictions(self, markets: list[Market]) -> list[ArbitrageOpportunity]:
        """Check for pairwise contradictions within NegRisk group"""
        opportunities = []
        
        for i in range(len(markets)):
            for j in range(i + 1, len(markets)):
                if not markets[i].outcome_prices or not markets[j].outcome_prices:
                    continue
                
                # In mutually exclusive outcomes, only one can be YES
                # If P(A=YES) + P(B=YES) > 1.0, there's a contradiction
                combined_prob = markets[i].outcome_prices[0] + markets[j].outcome_prices[0]
                
                if combined_prob > 1.0:
                    contradiction = combined_prob - 1.0
                    # Buy A_NO + B_NO for guaranteed profit
                    a_no = 1 - markets[i].outcome_prices[0]
                    b_no = 1 - markets[j].outcome_prices[0]
                    cost = a_no + b_no
                    guaranteed = 1.0  # At least one NO must pay out
                    
                    gross_profit = guaranteed - cost
                    
                    legs = [
                        {
                            "market_condition_id": markets[i].condition_id,
                            "outcome": markets[i].outcomes[1] if len(markets[i].outcomes) > 1 else "NO",
                            "side": "buy",
                            "price": a_no,
                            "size": 1.0,
                            "is_maker": True,
                            "is_neg_risk": True
                        },
                        {
                            "market_condition_id": markets[j].condition_id,
                            "outcome": markets[j].outcomes[1] if len(markets[j].outcomes) > 1 else "NO",
                            "side": "buy",
                            "price": b_no,
                            "size": 1.0,
                            "is_maker": True,
                            "is_neg_risk": True
                        }
                    ]
                    
                    total_fees = sum(
                        self.fee_calculator.calculate_trade_fee(l["price"], l["size"], is_neg_risk=True)
                        for l in legs
                    )
                    
                    net_profit = gross_profit - total_fees
                    profit_pct = net_profit / cost if cost > 0 else 0
                    
                    if profit_pct >= self.min_profit_threshold:
                        opportunities.append(ArbitrageOpportunity(
                            arbitrage_type=ArbitrageType.NEG_RISK_HEDGE,
                            markets=[markets[i], markets[j]],
                            expected_profit=net_profit,
                            profit_percentage=profit_pct,
                            investment_required=cost,
                            confidence=self._calculate_neg_risk_confidence(
                                [markets[i], markets[j]], contradiction, 2
                            ),
                            description=(
                                f"NegRisk pairwise: P({markets[i].question[:20]}...) + "
                                f"P({markets[j].question[:20]}...) = {combined_prob:.4f} > 1.0. "
                                f"Buy both NO for ${cost:.4f}."
                            ),
                            legs=legs
                        ))
        
        return opportunities
    
    def _calculate_neg_risk_confidence(self, markets: list[Market], gap: float, 
                                        num_outcomes: int) -> float:
        """Calculate confidence for NegRisk arbitrage"""
        confidence = 0.5
        
        # More outcomes = more reliable pricing discrepancies
        if num_outcomes >= 5:
            confidence += 0.1
        
        # Larger gap = higher confidence
        if gap > 0.05:
            confidence += 0.2
        elif gap > 0.03:
            confidence += 0.15
        elif gap > 0.01:
            confidence += 0.1
        
        # Average liquidity
        avg_liq = sum(m.liquidity for m in markets) / len(markets)
        if avg_liq > 5000:
            confidence += 0.1
        
        return min(confidence, 0.9)
