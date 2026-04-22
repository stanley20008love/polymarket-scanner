"""Polymarket Arbitrage Scanner - Data Models"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime


class MarketType(Enum):
    BINARY = "binary"
    MULTI_OUTCOME = "multi_outcome"
    NEG_RISK = "neg_risk"


class ArbitrageType(Enum):
    EXCLUSIVE_OUTCOME = "exclusive_outcome"
    LADDER_CONTRADICTION = "ladder_contradiction"
    CROSS_MARKET = "cross_market"
    NEG_RISK_HEDGE = "neg_risk_hedge"


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class Market:
    """Represents a Polymarket market"""
    condition_id: str
    question: str
    outcomes: list[str] = field(default_factory=list)
    outcome_prices: list[float] = field(default_factory=list)
    volume: float = 0.0
    liquidity: float = 0.0
    end_date: Optional[str] = None
    active: bool = True
    market_type: MarketType = MarketType.BINARY
    slug: str = ""
    category: str = ""
    
    @property
    def total_probability(self) -> float:
        """Sum of all outcome probabilities"""
        return sum(self.outcome_prices)


@dataclass
class OrderBook:
    """Order book for a market outcome"""
    condition_id: str
    outcome: str
    bids: list[tuple[float, float]] = field(default_factory=list)  # (price, size)
    asks: list[tuple[float, float]] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def best_bid(self) -> Optional[float]:
        return self.bids[0][0] if self.bids else None
    
    @property
    def best_ask(self) -> Optional[float]:
        return self.asks[0][0] if self.asks else None
    
    @property
    def spread(self) -> Optional[float]:
        if self.best_bid and self.best_ask:
            return self.best_ask - self.best_bid
        return None


@dataclass
class ArbitrageOpportunity:
    """Detected arbitrage opportunity"""
    arbitrage_type: ArbitrageType
    markets: list[Market]
    expected_profit: float
    profit_percentage: float
    investment_required: float
    confidence: float  # 0-1
    description: str = ""
    detected_at: datetime = field(default_factory=datetime.now)
    legs: list[dict] = field(default_factory=list)
    
    @property
    def is_profitable(self) -> bool:
        return self.expected_profit > 0 and self.profit_percentage > 0.02


@dataclass
class TradeExecution:
    """Record of a trade execution"""
    condition_id: str
    side: OrderSide
    price: float
    size: float
    outcome: str
    timestamp: datetime = field(default_factory=datetime.now)
    tx_hash: Optional[str] = None
    status: str = "pending"


@dataclass
class Position:
    """Open position in a market"""
    condition_id: str
    outcome: str
    entry_price: float
    size: float
    current_price: float
    pnl: float = 0.0
    opened_at: datetime = field(default_factory=datetime.now)
    
    @property
    def value(self) -> float:
        return self.size * self.current_price
    
    @property
    def unrealized_pnl(self) -> float:
        return (self.current_price - self.entry_price) * self.size


@dataclass
class ScanResult:
    """Results of a scan cycle"""
    timestamp: datetime = field(default_factory=datetime.now)
    markets_scanned: int = 0
    opportunities_found: list[ArbitrageOpportunity] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    scan_duration_ms: float = 0.0
