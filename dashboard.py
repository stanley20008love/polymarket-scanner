"""Streamlit Dashboard - Real-time visualization of scanning results (Lightweight)"""
import sys
import os
import time
import math
import logging
from datetime import datetime

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Try to import heavy dependencies - graceful fallback
HAS_SCIPY = False
try:
    import numpy as np
    from scipy.stats import norm
    HAS_SCIPY = True
except ImportError:
    pass

from models import ArbitrageType
from client import PolymarketClient
from fee_calculator import FeeCalculator
from risk_manager import RiskManager
from exclusive_outcome import ExclusiveOutcomeScanner
from ladder_contradiction import LadderContradictionScanner
from cross_market import CrossMarketScanner
from negrisk_adapter import NegRiskAdapter
from deribit_client import DeribitClient

logger = logging.getLogger(__name__)

# Page config
st.set_page_config(
    page_title="Polymarket Scanner + Vol Surface",
    page_icon="📊",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    .main-header { font-size: 2rem; font-weight: 700; }
    .metric-card {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        padding: 1.5rem;
        border-radius: 0.75rem;
        border: 1px solid #334155;
    }
    .profit-positive { color: #22c55e; font-weight: 700; }
    .profit-negative { color: #ef4444; font-weight: 700; }
</style>
""", unsafe_allow_html=True)


# === Lightweight Scanner (no scipy needed) ===
@st.cache_resource
def init_scanner_components():
    """Initialize scanner components"""
    import yaml
    config = {}
    try:
        with open("config.yaml", 'r') as f:
            config = yaml.safe_load(f) or {}
    except:
        pass
    
    api_config = config.get("api", {})
    fee_config = config.get("fees", {})
    risk_config = config.get("risk", {})
    scanner_config = config.get("scanner", {})
    
    client = PolymarketClient(api_config)
    fee_calc = FeeCalculator(fee_config)
    risk_mgr = RiskManager(risk_config)
    min_profit = scanner_config.get("min_profit_threshold", 0.02)
    
    return {
        "client": client,
        "fee_calc": fee_calc,
        "risk_mgr": risk_mgr,
        "min_profit": min_profit,
        "config": config,
    }


@st.cache_resource
def init_deribit():
    """Initialize Deribit client"""
    return DeribitClient()


@st.cache_data(ttl=60)
def run_scan():
    """Run a single scan and cache results for 60s"""
    from models import ScanResult, MarketType
    
    comps = init_scanner_components()
    client = comps["client"]
    fee_calc = comps["fee_calc"]
    min_profit = comps["min_profit"]
    
    result = ScanResult()
    
    try:
        # Fetch active markets
        markets = client.get_active_markets(limit=200)
        result.markets_scanned = len(markets)
        
        if not markets:
            result.errors.append("No markets fetched")
            return result
        
        # Initialize scanners
        exclusive = ExclusiveOutcomeScanner(fee_calc, min_profit)
        ladder = LadderContradictionScanner(fee_calc, min_profit)
        cross = CrossMarketScanner(fee_calc, min_profit)
        negrisk = NegRiskAdapter(fee_calc, min_profit)
        
        # 1. Exclusive outcome
        result.opportunities_found.extend(exclusive.scan_markets(markets))
        
        # 2. Ladder contradiction (group by category)
        from collections import defaultdict
        category_groups = defaultdict(list)
        for m in markets:
            category_groups[m.category or "unknown"].append(m)
        
        for cat, cat_markets in category_groups.items():
            if len(cat_markets) >= 2:
                result.opportunities_found.extend(ladder.scan_ladder_group(cat_markets))
        
        # 3. Cross-market
        result.opportunities_found.extend(cross.scan_market_pairs(markets))
        
        # 4. NegRisk
        neg_risk_markets = [m for m in markets if m.market_type == MarketType.NEG_RISK]
        if neg_risk_markets:
            neg_groups = negrisk.group_neg_risk_markets(neg_risk_markets)
            for group_key, group_markets in neg_groups.items():
                result.opportunities_found.extend(negrisk.scan_neg_risk_group(group_markets))
        
        # Sort by profit
        result.opportunities_found.sort(key=lambda x: x.profit_percentage, reverse=True)
        
    except Exception as e:
        result.errors.append(str(e))
    
    return result


# === Simple Black-Scholes without scipy (pure math) ===
def bs_call_price(S, K, T, r, sigma):
    """Black-Scholes call price using math stdlib only"""
    if T <= 0 or sigma <= 0:
        return max(S - K, 0)
    d1 = (math.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*math.sqrt(T))
    d2 = d1 - sigma*math.sqrt(T)
    # Approximate CDF using error function
    from math import erf, sqrt
    N = lambda x: 0.5 * (1 + erf(x/sqrt(2)))
    return S * N(d1) - K * math.exp(-r*T) * N(d2)

def bs_put_price(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0:
        return max(K - S, 0)
    d1 = (math.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*math.sqrt(T))
    d2 = d1 - sigma*math.sqrt(T)
    from math import erf, sqrt
    N = lambda x: 0.5 * (1 + erf(x/sqrt(2)))
    return K * math.exp(-r*T) * N(-d2) - S * N(-d1)


# === SIDEBAR ===
st.sidebar.title("⚙️ Configuration")
st.sidebar.markdown("---")

auto_refresh = st.sidebar.checkbox("Auto-refresh", value=False)
refresh_interval = st.sidebar.slider("Refresh interval (s)", 10, 120, 30)

st.sidebar.markdown("---")
st.sidebar.subheader("Scanner Settings")
min_profit = st.sidebar.slider("Min profit threshold (%)", 0.5, 10.0, 2.0, 0.5) / 100
max_positions = st.sidebar.slider("Max open positions", 1, 20, 5)

st.sidebar.markdown("---")
st.sidebar.subheader("Vol Surface")
vol_currency = st.sidebar.selectbox("Currency", ["BTC", "ETH"], index=0)

st.sidebar.markdown("---")
scipy_status = "✅ Available" if HAS_SCIPY else "⚠️ Not installed (lightweight mode)"
st.sidebar.info(f"Scanner Mode: READ-ONLY\nScipy: {scipy_status}")

# === MAIN CONTENT ===
st.title("📊 Polymarket Scanner + Options Vol Surface")
st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Tabs
tab1, tab2, tab3, tab4 = st.tabs([
    "🔍 Arbitrage Scanner",
    "📈 Volatility Surface",
    "⚡ Gamma Scalping",
    "📋 Risk Dashboard"
])

# === TAB 1: ARBITRAGE SCANNER ===
with tab1:
    st.subheader("Polymarket Arbitrage Opportunities")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with st.spinner("Scanning markets..."):
        result = run_scan()
    
    with col1:
        st.metric("Markets Scanned", result.markets_scanned)
    with col2:
        st.metric("Opportunities Found", len(result.opportunities_found))
    with col3:
        best_profit = max((o.profit_percentage for o in result.opportunities_found), default=0)
        st.metric("Best Profit", f"{best_profit:.2%}")
    with col4:
        st.metric("Scan Time", f"{result.scan_duration_ms:.0f}ms")
    
    st.markdown("---")
    
    if result.opportunities_found:
        opp_data = []
        for opp in result.opportunities_found:
            opp_data.append({
                "Type": opp.arbitrage_type.value.replace("_", " ").title(),
                "Net Profit ($)": f"${opp.expected_profit:.4f}",
                "Profit %": f"{opp.profit_percentage:.2%}",
                "Investment ($)": f"${opp.investment_required:.4f}",
                "Confidence": f"{opp.confidence:.0%}",
                "Description": opp.description[:100],
            })
        
        st.dataframe(
            pd.DataFrame(opp_data),
            use_container_width=True,
            hide_index=True
        )
        
        fig = go.Figure()
        types = list(set(o.arbitrage_type.value for o in result.opportunities_found))
        for arb_type in types:
            type_opps = [o for o in result.opportunities_found if o.arbitrage_type.value == arb_type]
            fig.add_trace(go.Bar(
                name=arb_type.replace("_", " ").title(),
                x=[f"#{i+1}" for i in range(len(type_opps))],
                y=[o.profit_percentage * 100 for o in type_opps],
            ))
        
        fig.update_layout(
            title="Profit by Arbitrage Type",
            xaxis_title="Opportunity",
            yaxis_title="Profit %",
            template="plotly_dark"
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No arbitrage opportunities found in this scan. Markets appear efficient.")
    
    if result.errors:
        st.error(f"Errors: {', '.join(result.errors)}")

# === TAB 2: VOLATILITY SURFACE ===
with tab2:
    st.subheader(f"{vol_currency} Options Volatility Surface")
    
    deribit = init_deribit()
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown("#### Market Summary")
        summary = deribit.get_summary(vol_currency)
        
        st.metric("Index Price", f"${summary.get('index_price', 0):,.0f}")
        st.metric("Historical Vol", f"{summary.get('historical_volatility', 0):.1%}")
        st.metric("Active Instruments", summary.get('active_instruments', 0))
    
    with col2:
        st.markdown("#### Implied Volatility Surface")
        
        with st.spinner("Fetching options data from Deribit..."):
            chain = deribit.get_options_chain(vol_currency)
        
        if not chain.empty and "iv" in chain.columns:
            display_chain = chain[chain["iv"].notna()].copy()
            
            if not display_chain.empty:
                fig = go.Figure(data=[go.Scatter3d(
                    x=display_chain["strike"],
                    y=display_chain["expiry_years"],
                    z=display_chain["iv"],
                    mode='markers',
                    marker=dict(
                        size=5,
                        color=display_chain["iv"],
                        colorscale='Viridis',
                        colorbar=dict(title="IV"),
                    ),
                    text=display_chain["instrument_name"],
                    hovertemplate="<b>%{text}</b><br>Strike: %{x}<br>Expiry: %{y:.3f}yr<br>IV: %{z:.1%}<extra></extra>"
                )])
                
                fig.update_layout(
                    scene=dict(
                        xaxis_title="Strike",
                        yaxis_title="Time to Expiry (yr)",
                        zaxis_title="Implied Vol",
                    ),
                    template="plotly_dark",
                    height=500
                )
                st.plotly_chart(fig, use_container_width=True)
                
                nearest_expiry = display_chain["expiry_years"].min()
                near_chain = display_chain[display_chain["expiry_years"] == nearest_expiry]
                
                if not near_chain.empty:
                    calls = near_chain[near_chain["option_type"] == "call"]
                    puts = near_chain[near_chain["option_type"] == "put"]
                    
                    fig2 = go.Figure()
                    if not calls.empty:
                        fig2.add_trace(go.Scatter(
                            x=calls["strike"], y=calls["iv"],
                            mode='markers+lines', name='Calls',
                            marker=dict(color='#22c55e')
                        ))
                    if not puts.empty:
                        fig2.add_trace(go.Scatter(
                            x=puts["strike"], y=puts["iv"],
                            mode='markers+lines', name='Puts',
                            marker=dict(color='#ef4444')
                        ))
                    
                    fig2.update_layout(
                        title=f"Vol Smile - Nearest Expiry ({nearest_expiry:.3f}yr)",
                        xaxis_title="Strike",
                        yaxis_title="Implied Vol",
                        template="plotly_dark"
                    )
                    st.plotly_chart(fig2, use_container_width=True)
            else:
                st.warning("No IV data available from Deribit")
        else:
            st.warning("Could not fetch options chain. Deribit API may be rate-limited.")

# === TAB 3: GAMMA SCALPING ===
with tab3:
    st.subheader("Gamma Scalping Analysis")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown("#### Parameters")
        spot = st.number_input("Spot Price", value=65000.0, step=1000.0)
        strike = st.number_input("Strike Price", value=65000.0, step=1000.0)
        expiry_days = st.number_input("Days to Expiry", value=30, min_value=1)
        implied_vol = st.slider("Implied Vol (%)", 10, 200, 60) / 100
        realized_vol = st.slider("Expected Realized Vol (%)", 10, 200, 75) / 100
        opt_type = st.selectbox("Option Type", ["call", "put"])
        position_size = st.number_input("Position Size (contracts)", value=1.0, step=0.5)
        
        T = expiry_days / 365.0
    
    with col2:
        if not HAS_SCIPY:
            st.warning("⚠️ Scipy not installed. Using simplified Black-Scholes (no Greeks/Gamma scalping).")
            st.info("Install scipy for full features: `pip install scipy numpy`")
        
        # Simple analysis even without scipy
        call_p = bs_call_price(spot, strike, T, 0.05, implied_vol)
        put_p = bs_put_price(spot, strike, T, 0.05, implied_vol)
        option_price = call_p if opt_type == "call" else put_p
        
        daily_move = realized_vol * spot / math.sqrt(252)
        
        st.markdown("#### Quick Analysis")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Option Price", f"${option_price:.2f}")
            vol_edge = realized_vol - implied_vol
            st.metric("Vol Edge", f"{vol_edge:.2%}")
        with c2:
            st.metric("Expected Daily Move", f"${daily_move:.2f}")
            st.metric("Implied Daily Move", f"${implied_vol * spot / math.sqrt(252):.2f}")
        with c3:
            st.metric("Days to Expiry", expiry_days)
            st.metric("Total Cost", f"${option_price * position_size * 100:.2f}")
        
        if HAS_SCIPY:
            from gamma_scalping import GammaScalper
            scalper = GammaScalper()
            if st.button("Full Gamma Analysis", type="primary"):
                analysis = scalper.analyze_opportunity(
                    S=spot, K=strike, T=T,
                    sigma_implied=implied_vol,
                    sigma_realized=realized_vol,
                    position_size=position_size,
                    option_type=opt_type
                )
                st.markdown(f"### {analysis['recommendation']}")
                st.metric("Net Daily P&L", f"${analysis['net_daily_pnl']:.4f}")
                st.metric("Profit Ratio", f"{analysis['profit_ratio']:.2f}x")
                st.metric("Breakeven Vol", f"{analysis['breakeven_vol']:.1%}")

# === TAB 4: RISK DASHBOARD ===
with tab4:
    st.subheader("Risk Management Dashboard")
    
    comps = init_scanner_components()
    risk_status = comps["risk_mgr"].get_status()
    
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Daily P&L", f"${risk_status['daily_pnl']:.2f}")
    with c2:
        st.metric("Daily Loss", f"${risk_status['daily_loss']:.2f}")
    with c3:
        st.metric("Open Positions", f"{risk_status['open_positions']}/{risk_status['max_open_positions']}")
    with c4:
        st.metric("Total Exposure", f"${risk_status['total_exposure']:.2f}")
    
    st.markdown("---")
    
    st.markdown("### Risk Limits")
    limits_data = {
        "Parameter": ["Max Daily Loss", "Max Open Positions", "Max Single Bet %", "Stop Loss %", "Max Position Size"],
        "Limit": [f"${risk_status['max_daily_loss']}", f"{risk_status['max_open_positions']}", "10%", "15%", "$100"],
        "Used": [f"${risk_status['daily_loss']:.2f}", f"{risk_status['open_positions']}", "-", "-", "-"],
        "Remaining": [f"${risk_status['remaining_daily_capacity']:.2f}", f"{risk_status['max_open_positions'] - risk_status['open_positions']}", "-", "-", "-"]
    }
    st.dataframe(pd.DataFrame(limits_data), use_container_width=True, hide_index=True)
    
    st.markdown("---")
    st.markdown("### System Info")
    st.json({
        "Scipy Available": HAS_SCIPY,
        "Python Version": sys.version.split()[0],
        "Scanner Mode": "READ-ONLY",
    })

# Auto-refresh
if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()
