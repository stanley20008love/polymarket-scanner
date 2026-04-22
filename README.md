# Polymarket Arbitrage Scanner + Options Volatility Surface

Real-time arbitrage detection for Polymarket prediction markets and options volatility surface modeling for crypto derivatives.

## Features

### Polymarket Arbitrage Scanner
- **Exclusive Outcome Detection**: Finds markets where sum of outcomes < $1.00
- **Ladder Contradiction**: Detects pricing contradictions across threshold levels
- **Cross-Market Arbitrage**: Finds inconsistencies between related markets
- **NegRisk Adapter**: Handles Polymarket's negative risk market structure

### Options Volatility Surface
- **Black-Scholes Pricing**: Full European option pricing with Greeks
- **SABR Calibration**: Stochastic volatility model for smile fitting
- **Surface Builder**: Complete volatility surface construction and interpolation
- **Gamma Scalping**: Delta-neutral strategy analysis and Monte Carlo simulation

### Dashboard
- Real-time Streamlit web interface
- Interactive Plotly charts
- Risk management dashboard

## Deployment

Deployed on Zeabur with Docker.

## API Keys (Optional)

- Polymarket CLOB API keys: Only needed for trade execution (scanning works without)
- Deribit API keys: Only needed for options trading (market data is public)
