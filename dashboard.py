"""Streamlit Dashboard - Real-time visualization of scanning results"""
import sys
import os
import time
import logging
from datetime import datetime

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import ArbitrageType
from main import ScannerEngine
from black_scholes import BlackScholes
from sabr_calibrator import SABRCalibrator
from surface_builder import VolatilitySurface
from gamma_scalping import GammaScalper
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
    .status-running { color: #22c55e; }
    .status-stopped { color: #ef4444; }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def init_scanner():
    """Initialize scanner engine"""
    return ScannerEngine()


@st.cache_resource
def init_vol_surface():
    """Initialize volatility surface builder"""
    return VolatilitySurface()


@st.cache_resource
def init_deribit():
    """Initialize Deribit client"""
    return DeribitClient()


@st.cache_resource
def init_gamma_scalper():
    """Initialize gamma scalper"""
    return GammaScalper()


@st.cache_data(ttl=60)
def run_scan():
    """Run a single scan and cache results for 60s"""
    engine = init_scanner()
    return engine.scan_once()


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
vol_beta = st.sidebar.slider("SABR Beta", 0.0, 1.0, 0.5, 0.1)

st.sidebar.markdown("---")
st.sidebar.info("Scanner Mode: READ-ONLY\nNo trades executed")

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
        # Opportunities table
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
        
        # Profit distribution chart
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
        
        st.markdown("#### SABR Parameters")
        st.info(f"Beta = {vol_beta}")
    
    with col2:
        st.markdown("#### Implied Volatility Surface")
        
        # Get options chain
        with st.spinner("Fetching options data from Deribit..."):
            chain = deribit.get_options_chain(vol_currency)
        
        if not chain.empty and "iv" in chain.columns:
            # Filter for display
            display_chain = chain[chain["iv"].notna()].copy()
            
            if not display_chain.empty:
                # 3D Surface plot
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
                
                # Vol smile for nearest expiry
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
            st.info("The scanner will retry on next refresh.")

# === TAB 3: GAMMA SCALPING ===
with tab3:
    st.subheader("Gamma Scalping Analysis")
    
    scalper = init_gamma_scalper()
    bs = BlackScholes()
    
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
        
        if st.button("Analyze Opportunity", type="primary"):
            analysis = scalper.analyze_opportunity(
                S=spot, K=strike, T=T,
                sigma_implied=implied_vol,
                sigma_realized=realized_vol,
                position_size=position_size,
                option_type=opt_type
            )
            st.session_state['analysis'] = analysis
    
    with col2:
        if 'analysis' in st.session_state:
            a = st.session_state['analysis']
            
            st.markdown(f"### {a['recommendation']}")
            st.markdown("---")
            
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Option Price", f"${a['option_price']:.2f}")
                st.metric("Vol Edge", f"{a['vol_edge']:.2%}")
            with c2:
                st.metric("Gamma P&L/Day", f"${a['gamma_pnl_daily']:.4f}")
                st.metric("Theta Cost/Day", f"${a['theta_cost_daily']:.4f}")
            with c3:
                st.metric("Net Daily P&L", f"${a['net_daily_pnl']:.4f}")
                st.metric("Profit Ratio", f"{a['profit_ratio']:.2f}x")
            
            st.markdown("---")
            
            # Greeks display
            g = a['greeks']
            greeks_fig = go.Figure(data=[
                go.Bar(name='Value', x=list(g.keys()), y=list(g.values()),
                       marker_color=['#3b82f6', '#22c55e', '#ef4444', '#f59e0b', '#8b5cf6'])
            ])
            greeks_fig.update_layout(title="Greeks", template="plotly_dark")
            st.plotly_chart(greeks_fig, use_container_width=True)
            
            st.metric("Breakeven Realized Vol", f"{a['breakeven_vol']:.1%}")
            st.metric("Total Projected P&L", f"${a['total_projected_pnl']:.4f}")
            st.metric("ROI", f"{a['roi']:.1%}")
            
            # Simulation
            if st.button("Run Monte Carlo Simulation"):
                with st.spinner("Simulating..."):
                    sim = scalper.simulate_scalping(
                        S0=spot, K=strike, T=T,
                        sigma_implied=implied_vol,
                        sigma_realized=realized_vol,
                        option_type=opt_type,
                        position_size=position_size
                    )
                    
                    st.metric("Simulated Total P&L", f"${sim['total_pnl']:.4f}")
                    st.metric("Simulated ROI", f"{sim['roi']:.1%}")
                    
                    # Price path
                    path_fig = go.Figure()
                    path_fig.add_trace(go.Scatter(
                        y=sim['price_path'][:200],
                        mode='lines', name='Price Path',
                        line=dict(color='#3b82f6', width=1)
                    ))
                    path_fig.add_hline(y=strike, line_dash="dash", 
                                       annotation_text=f"Strike ${strike:,.0f}")
                    path_fig.update_layout(title="Simulated Price Path", template="plotly_dark")
                    st.plotly_chart(path_fig, use_container_width=True)
        else:
            st.info("Set parameters and click 'Analyze Opportunity' to see results")

# === TAB 4: RISK DASHBOARD ===
with tab4:
    st.subheader("Risk Management Dashboard")
    
    engine = init_scanner()
    risk_status = engine.risk_manager.get_status()
    
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
    
    # Risk limits
    st.markdown("### Risk Limits")
    limits_data = {
        "Parameter": ["Max Daily Loss", "Max Open Positions", "Max Single Bet %", "Stop Loss %", "Max Position Size"],
        "Limit": [f"${risk_status['max_daily_loss']}", f"{risk_status['max_open_positions']}", "10%", "15%", "$100"],
        "Used": [f"${risk_status['daily_loss']:.2f}", f"{risk_status['open_positions']}", "-", "-", "-"],
        "Remaining": [f"${risk_status['remaining_daily_capacity']:.2f}", f"{risk_status['max_open_positions'] - risk_status['open_positions']}", "-", "-", "-"]
    }
    st.dataframe(pd.DataFrame(limits_data), use_container_width=True, hide_index=True)
    
    st.markdown("---")
    st.markdown("### System Status")
    status = engine.get_status()
    st.json({
        "Scanner Running": status["running"],
        "Total Scans": status["scan_count"],
        "Total Opportunities Found": status["total_opportunities"],
        "Last Scan": status["last_scan"]
    })

# Auto-refresh
if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()
