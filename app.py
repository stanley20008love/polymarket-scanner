"""Flask Web Dashboard - Polymarket Scanner"""
import os
from flask import Flask, render_template_string, jsonify
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Polymarket Scanner + Options Vol Surface</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; }
        .header { background: linear-gradient(135deg, #1e293b, #0f172a); padding: 2rem; border-bottom: 2px solid #22c55e; text-align: center; }
        .header h1 { font-size: 2rem; color: #22c55e; }
        .header p { color: #94a3b8; margin-top: 0.5rem; }
        .container { max-width: 1200px; margin: 0 auto; padding: 2rem; }
        .tabs { display: flex; gap: 1rem; margin-bottom: 2rem; }
        .tab { padding: 0.75rem 1.5rem; background: #1e293b; border: 1px solid #334155; border-radius: 0.5rem; cursor: pointer; color: #94a3b8; transition: all 0.2s; }
        .tab.active, .tab:hover { background: #22c55e; color: #0f172a; border-color: #22c55e; }
        .metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 2rem; }
        .metric { background: #1e293b; padding: 1.5rem; border-radius: 0.75rem; border: 1px solid #334155; text-align: center; }
        .metric .label { font-size: 0.875rem; color: #94a3b8; margin-bottom: 0.5rem; }
        .metric .value { font-size: 1.75rem; font-weight: 700; color: #22c55e; }
        .card { background: #1e293b; padding: 1.5rem; border-radius: 0.75rem; border: 1px solid #334155; margin-bottom: 1rem; }
        .card h3 { color: #22c55e; margin-bottom: 1rem; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 0.75rem; text-align: left; border-bottom: 1px solid #334155; }
        th { color: #94a3b8; font-size: 0.875rem; }
        .positive { color: #22c55e; }
        .negative { color: #ef4444; }
        .status-online { color: #22c55e; font-size: 1.25rem; }
        .footer { text-align: center; padding: 2rem; color: #64748b; font-size: 0.875rem; }
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 Polymarket Scanner + Options Vol Surface</h1>
        <p class="status-online">✅ Service ONLINE | Mode: READ-ONLY | {{ timestamp }}</p>
    </div>
    <div class="container">
        <div class="metrics">
            <div class="metric">
                <div class="label">Markets Scanned</div>
                <div class="value">{{ markets_scanned }}</div>
            </div>
            <div class="metric">
                <div class="label">Opportunities Found</div>
                <div class="value">{{ opportunities_count }}</div>
            </div>
            <div class="metric">
                <div class="label">Best Profit</div>
                <div class="value positive">{{ best_profit }}</div>
            </div>
            <div class="metric">
                <div class="label">Scanner Status</div>
                <div class="value">ACTIVE</div>
            </div>
        </div>
        
        <div class="tabs">
            <div class="tab active" onclick="showTab('scanner')">🔍 Arbitrage Scanner</div>
            <div class="tab" onclick="showTab('vol')">📈 Vol Surface</div>
            <div class="tab" onclick="showTab('gamma')">⚡ Gamma Scalping</div>
            <div class="tab" onclick="showTab('risk')">📋 Risk Dashboard</div>
        </div>
        
        <div id="scanner" class="tab-content">
            <div class="card">
                <h3>Arbitrage Opportunities</h3>
                {% if opportunities %}
                <table>
                    <thead><tr><th>Type</th><th>Net Profit</th><th>Profit %</th><th>Confidence</th><th>Description</th></tr></thead>
                    <tbody>
                    {% for opp in opportunities %}
                    <tr>
                        <td>{{ opp.type }}</td>
                        <td class="positive">${{ opp.profit }}</td>
                        <td class="positive">{{ opp.pct }}%</td>
                        <td>{{ opp.confidence }}%</td>
                        <td>{{ opp.desc }}</td>
                    </tr>
                    {% endfor %}
                    </tbody>
                </table>
                {% else %}
                <p>No arbitrage opportunities found. Markets appear efficient.</p>
                {% endif %}
                {% if errors %}
                <p class="negative">Errors: {{ errors }}</p>
                {% endif %}
            </div>
        </div>
        
        <div id="vol" class="tab-content" style="display:none">
            <div class="card">
                <h3>{{ currency }} Options Volatility Surface</h3>
                <p>Index Price: ${{ index_price | int }} | Historical Vol: {{ hist_vol }}%</p>
                <p>Active Instruments: {{ active_instruments }}</p>
                <p style="color:#94a3b8;margin-top:1rem;">Volatility surface chart available in interactive mode.</p>
            </div>
        </div>
        
        <div id="gamma" class="tab-content" style="display:none">
            <div class="card">
                <h3>Gamma Scalping Analysis</h3>
                <p>Configure parameters in the interactive dashboard for full analysis.</p>
                <p>Black-Scholes calculator available for quick option pricing.</p>
            </div>
        </div>
        
        <div id="risk" class="tab-content" style="display:none">
            <div class="card">
                <h3>Risk Management Dashboard</h3>
                <p>Daily P&L: $0.00 | Daily Loss: $0.00 | Open Positions: 0/5</p>
                <p>Total Exposure: $0.00 | Max Daily Loss: $50.00</p>
            </div>
        </div>
    </div>
    <div class="footer">Polymarket Scanner v1.0 | READ-ONLY Mode | Python {{ python_version }}</div>
    <script>
    function showTab(name) {
        document.querySelectorAll('.tab-content').forEach(el => el.style.display = 'none');
        document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
        document.getElementById(name).style.display = 'block';
        event.target.classList.add('active');
    }
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    from datetime import datetime
    scan_data = {"markets_scanned": 0, "opportunities_count": 0, "best_profit": "0%", "opportunities": [], "errors": []}
    vol_data = {"currency": "BTC", "index_price": 0, "hist_vol": 0, "active_instruments": 0}
    
    try:
        from client import PolymarketClient
        from fee_calculator import FeeCalculator
        from exclusive_outcome import ExclusiveOutcomeScanner
        client = PolymarketClient({})
        fee_calc = FeeCalculator({})
        markets = client.get_active_markets(limit=200)
        scan_data["markets_scanned"] = len(markets)
        
        scanner = ExclusiveOutcomeScanner(fee_calc, 0.02)
        opps = scanner.scan_markets(markets)
        scan_data["opportunities_count"] = len(opps)
        
        if opps:
            best = max(opps, key=lambda x: x.profit_percentage)
            scan_data["best_profit"] = f"{best.profit_percentage:.2%}"
            scan_data["opportunities"] = [
                {"type": o.arbitrage_type.value.replace("_", " ").title(), 
                 "profit": f"{o.expected_profit:.4f}", 
                 "pct": f"{o.profit_percentage:.2%}",
                 "confidence": f"{o.confidence:.0%}",
                 "desc": o.description[:80]}
                for o in opps[:20]
            ]
    except Exception as e:
        scan_data["errors"] = str(e)
    
    try:
        from deribit_client import DeribitClient
        deribit = DeribitClient()
        summary = deribit.get_summary("BTC")
        vol_data["index_price"] = summary.get("index_price") or 0
        vol_data["hist_vol"] = f"{(summary.get('historical_volatility') or 0)*100:.1f}"
        vol_data["active_instruments"] = summary.get("active_instruments") or 0
    except Exception:
        pass
    
    return render_template_string(HTML_TEMPLATE,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        markets_scanned=scan_data["markets_scanned"],
        opportunities_count=scan_data["opportunities_count"],
        best_profit=scan_data["best_profit"],
        opportunities=scan_data["opportunities"],
        errors=scan_data["errors"],
        currency=vol_data["currency"],
        index_price=vol_data["index_price"],
        hist_vol=vol_data["hist_vol"],
        active_instruments=vol_data["active_instruments"],
        python_version=sys.version.split()[0]
    )

@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "polymarket-scanner"})

@app.route("/api/scan")
def api_scan():
    try:
        from client import PolymarketClient
        from fee_calculator import FeeCalculator
        from exclusive_outcome import ExclusiveOutcomeScanner
        client = PolymarketClient({})
        fee_calc = FeeCalculator({})
        markets = client.get_active_markets(limit=200)
        scanner = ExclusiveOutcomeScanner(fee_calc, 0.02)
        opps = scanner.scan_markets(markets)
        return jsonify({"markets_scanned": len(markets), "opportunities": len(opps), "status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e), "status": "error"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8501))
    app.run(host="0.0.0.0", port=port)
