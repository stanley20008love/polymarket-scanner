"""Main Scanner Engine - Orchestrates all scanning modules"""
import asyncio
import logging
import time
import yaml
from datetime import datetime
from typing import Optional

from models import ScanResult, ArbitrageOpportunity, Market, MarketType
from client import PolymarketClient
from exclusive_outcome import ExclusiveOutcomeScanner
from ladder_contradiction import LadderContradictionScanner
from cross_market import CrossMarketScanner
from negrisk_adapter import NegRiskAdapter
from fee_calculator import FeeCalculator
from risk_manager import RiskManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("scanner")


class ScannerEngine:
    """Main scanning engine that coordinates all arbitrage detectors"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        
        # Initialize components
        api_config = self.config.get("api", {})
        fee_config = self.config.get("fees", {})
        risk_config = self.config.get("risk", {})
        scanner_config = self.config.get("scanner", {})
        
        self.client = PolymarketClient(api_config)
        self.fee_calculator = FeeCalculator(fee_config)
        self.risk_manager = RiskManager(risk_config)
        
        min_profit = scanner_config.get("min_profit_threshold", 0.02)
        
        self.exclusive_scanner = ExclusiveOutcomeScanner(self.fee_calculator, min_profit)
        self.ladder_scanner = LadderContradictionScanner(self.fee_calculator, min_profit)
        self.cross_market_scanner = CrossMarketScanner(self.fee_calculator, min_profit)
        self.negrisk_adapter = NegRiskAdapter(self.fee_calculator, min_profit)
        
        self._running = False
        self._scan_count = 0
        self._total_opportunities = 0
    
    def _load_config(self, path: str) -> dict:
        """Load configuration from YAML file"""
        try:
            with open(path, 'r') as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning(f"Config file not found: {path}, using defaults")
            return {}
    
    def scan_once(self) -> ScanResult:
        """Run a single scan cycle across all markets"""
        start_time = time.time()
        result = ScanResult()
        
        logger.info("=== Starting scan cycle ===")
        
        try:
            # Fetch all active markets
            markets = self.client.get_active_markets(limit=200)
            result.markets_scanned = len(markets)
            
            if not markets:
                result.errors.append("No markets fetched")
                return result
            
            logger.info(f"Scanning {len(markets)} markets...")
            
            # 1. Exclusive outcome arbitrage
            exclusive_opps = self.exclusive_scanner.scan_markets(markets)
            result.opportunities_found.extend(exclusive_opps)
            logger.info(f"Exclusive outcome: {len(exclusive_opps)} opportunities")
            
            # 2. Ladder contradiction (group by category)
            category_groups = {}
            for m in markets:
                cat = m.category or "unknown"
                category_groups.setdefault(cat, []).append(m)
            
            for cat, cat_markets in category_groups.items():
                if len(cat_markets) >= 2:
                    ladder_opps = self.ladder_scanner.scan_ladder_group(cat_markets)
                    result.opportunities_found.extend(ladder_opps)
            
            # 3. Cross-market arbitrage
            cross_opps = self.cross_market_scanner.scan_market_pairs(markets)
            result.opportunities_found.extend(cross_opps)
            logger.info(f"Cross-market: {len(cross_opps)} opportunities")
            
            # 4. NegRisk markets
            neg_risk_markets = [m for m in markets if m.market_type == MarketType.NEG_RISK]
            if neg_risk_markets:
                neg_groups = self.negrisk_adapter.group_neg_risk_markets(neg_risk_markets)
                for group_key, group_markets in neg_groups.items():
                    neg_opps = self.negrisk_adapter.scan_neg_risk_group(group_markets)
                    result.opportunities_found.extend(neg_opps)
                logger.info(f"NegRisk: {len(neg_risk_markets)} markets in {len(neg_groups)} groups")
            
            # Deduplicate and sort by profit
            result.opportunities_found = self._deduplicate(result.opportunities_found)
            result.opportunities_found.sort(key=lambda x: x.profit_percentage, reverse=True)
            
            # Log results
            for opp in result.opportunities_found[:5]:  # Top 5
                logger.info(
                    f"  TOP: {opp.arbitrage_type.value} | "
                    f"Profit: ${opp.expected_profit:.4f} ({opp.profit_percentage:.2%}) | "
                    f"Confidence: {opp.confidence:.2f} | "
                    f"{opp.description[:80]}"
                )
            
        except Exception as e:
            logger.error(f"Scan error: {e}")
            result.errors.append(str(e))
        
        result.scan_duration_ms = (time.time() - start_time) * 1000
        self._scan_count += 1
        self._total_opportunities += len(result.opportunities_found)
        
        logger.info(
            f"=== Scan complete: {result.markets_scanned} markets, "
            f"{len(result.opportunities_found)} opportunities, "
            f"{result.scan_duration_ms:.0f}ms ==="
        )
        
        return result
    
    def _deduplicate(self, opportunities: list[ArbitrageOpportunity]) -> list[ArbitrageOpportunity]:
        """Remove duplicate opportunities based on market IDs"""
        seen = set()
        unique = []
        for opp in opportunities:
            key = tuple(sorted(m.condition_id for m in opp.markets))
            if key not in seen:
                seen.add(key)
                unique.append(opp)
        return unique
    
    def get_status(self) -> dict:
        """Get current scanner status"""
        return {
            "running": self._running,
            "scan_count": self._scan_count,
            "total_opportunities": self._total_opportunities,
            "risk_status": self.risk_manager.get_status(),
            "last_scan": datetime.now().isoformat()
        }


if __name__ == "__main__":
    engine = ScannerEngine()
    result = engine.scan_once()
    print(f"\nScan Results: {result.markets_scanned} markets, {len(result.opportunities_found)} opportunities")
    for opp in result.opportunities_found:
        print(f"  - {opp.arbitrage_type.value}: ${opp.expected_profit:.4f} ({opp.profit_percentage:.2%})")
