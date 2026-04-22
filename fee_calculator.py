"""Fee Calculator for Polymarket trades"""
import logging
from models import OrderSide, ArbitrageOpportunity

logger = logging.getLogger(__name__)


class FeeCalculator:
    """Calculates trading fees and net profits for Polymarket"""
    
    def __init__(self, config: dict):
        self.maker_fee = config.get("maker_fee", 0.0)       # 0% maker fee on Polymarket
        self.taker_fee = config.get("taker_fee", 0.02)       # 2% taker fee
        self.withdrawal_fee = config.get("withdrawal_fee", 0.0)
        self.neg_risk_fee = config.get("neg_risk_fee", 0.02) # Additional 2% for NegRisk
    
    def calculate_trade_fee(self, price: float, size: float, side: OrderSide, 
                            is_neg_risk: bool = False, is_maker: bool = True) -> float:
        """Calculate fee for a single trade"""
        notional = price * size
        
        if is_maker:
            fee_rate = self.maker_fee
        else:
            fee_rate = self.taker_fee
        
        if is_neg_risk:
            fee_rate += self.neg_risk_fee
        
        return notional * fee_rate
    
    def calculate_arbitrage_fees(self, opportunity: ArbitrageOpportunity, 
                                  is_neg_risk: bool = False) -> float:
        """Calculate total fees for an arbitrage opportunity"""
        total_fees = 0.0
        
        for leg in opportunity.legs:
            price = leg.get("price", 0)
            size = leg.get("size", 0)
            side = OrderSide.BUY if leg.get("side") == "buy" else OrderSide.SELL
            is_maker = leg.get("is_maker", True)
            
            fee = self.calculate_trade_fee(price, size, side, is_neg_risk, is_maker)
            total_fees += fee
        
        # Add withdrawal fee if we plan to withdraw profits
        if opportunity.expected_profit > 0:
            total_fees += self.withdrawal_fee
        
        return total_fees
    
    def calculate_net_profit(self, opportunity: ArbitrageOpportunity,
                             is_neg_risk: bool = False) -> float:
        """Calculate net profit after fees"""
        gross_profit = opportunity.expected_profit
        total_fees = self.calculate_arbitrage_fees(opportunity, is_neg_risk)
        net = gross_profit - total_fees
        
        logger.debug(
            f"Gross profit: ${gross_profit:.4f}, Fees: ${total_fees:.4f}, "
            f"Net: ${net:.4f}"
        )
        
        return net
    
    def calculate_break_even_prices(self, buy_price: float, size: float,
                                     is_neg_risk: bool = False) -> float:
        """Calculate the minimum sell price to break even after fees"""
        notional = buy_price * size
        buy_fee = self.calculate_trade_fee(buy_price, size, OrderSide.BUY, is_neg_risk)
        
        # We need: sell_notional - sell_fee - buy_notional - buy_fee >= 0
        # sell_price * size - sell_price * size * sell_fee_rate - notional - buy_fee >= 0
        sell_fee_rate = self.taker_fee + (self.neg_risk_fee if is_neg_risk else 0)
        
        # sell_price * size * (1 - sell_fee_rate) = notional + buy_fee
        break_even = (notional + buy_fee) / (size * (1 - sell_fee_rate))
        
        return break_even
    
    def estimate_slippage(self, orderbook_bids: list, orderbook_asks: list,
                          size: float, side: OrderSide) -> tuple[float, float]:
        """Estimate price impact/slippage for a given order size"""
        if side == OrderSide.BUY and orderbook_asks:
            total_cost = 0.0
            remaining = size
            for price, avail_size in orderbook_asks:
                fill = min(remaining, avail_size)
                total_cost += fill * price
                remaining -= fill
                if remaining <= 0:
                    break
            
            if remaining > 0:
                # Not enough liquidity
                avg_price = total_cost / (size - remaining) if (size - remaining) > 0 else float('inf')
                return avg_price, remaining  # Return avg price and unfilled amount
            
            avg_price = total_cost / size
            best_price = orderbook_asks[0][0]
            slippage = (avg_price - best_price) / best_price
            return avg_price, slippage
            
        elif side == OrderSide.SELL and orderbook_bids:
            total_revenue = 0.0
            remaining = size
            for price, avail_size in orderbook_bids:
                fill = min(remaining, avail_size)
                total_revenue += fill * price
                remaining -= fill
                if remaining <= 0:
                    break
            
            if remaining > 0:
                avg_price = total_revenue / (size - remaining) if (size - remaining) > 0 else 0
                return avg_price, remaining
            
            avg_price = total_revenue / size
            best_price = orderbook_bids[0][0]
            slippage = (best_price - avg_price) / best_price
            return avg_price, slippage
        
        return 0.0, 0.0
