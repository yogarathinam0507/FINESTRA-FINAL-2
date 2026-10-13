import random, math, json, time
import database as D

def sma(x, n): return sum(x[-n:]) / min(n, len(x)) if x else 0

def ema(x, n):
    if not x: return 0
    k = 2 / (n + 1); e = x[0]
    for p in x[1:]: e = p * k + e * (1 - k)
    return e

def rsi(x, n=14):
    if len(x) < 2: return 50.0
    d = [x[i] - x[i-1] for i in range(max(1, len(x) - n), len(x))]
    g = sum(v for v in d if v > 0); l = -sum(v for v in d if v < 0)
    return 100.0 if l == 0 and g > 0 else (50.0 if l == 0 else 100.0 - 100.0 / (1.0 + g / l))

def macd(x): return ema(x, 12) - ema(x, 26) if len(x) > 1 else 0

def analysis(closes):
    if not closes:
        return dict(rsi=50.0, macd=0.0, sma5=0.0, sma20=0.0, momentum=0.0, support=0.0, resistance=0.0, trend="Neutral", tech=50)
    r = rsi(closes); m = macd(closes); s5, s20 = sma(closes, 5), sma(closes, 20)
    mom = (closes[-1] / closes[-min(5, len(closes))] - 1.0) * 100.0 if len(closes) >= 2 else 0.0
    score = 50.0 + (10.0 if s5 > s20 else -10.0) + (10.0 if m > 0 else -10.0) + (5.0 if 50.0 < r < 70.0 else (-5.0 if r > 70.0 or r < 30.0 else 0.0))
    return dict(rsi=round(r, 1), macd=round(m, 2), sma5=round(s5, 2), sma20=round(s20, 2), momentum=round(mom, 2), 
                support=min(closes[-20:]) if len(closes) >= 20 else closes[0], 
                resistance=max(closes[-20:]) if len(closes) >= 20 else closes[-1],
                trend="Bullish" if s5 >= s20 else "Bearish", tech=max(0, min(100, int(score))))

def apply_news_shock(c, news_id):
    """CRITICAL FIX: Immediately calculates and applies news/event price shocks (manual, automatic, or mega events)
       at the exact second they trigger, updating company valuations and real-time candles instantly.
    """
    n = c.execute("SELECT * FROM news WHERE id=?", (news_id,)).fetchone()
    if not n: return

    try:
        impacts = json.loads(n["impacts"] or "{}")
    except Exception:
        impacts = {}

    try:
        sens = json.loads(n["sens"] or "{}")
    except Exception:
        sens = {}

    upd = int(D.get(c, "upd") or 0)
    cos = c.execute("SELECT * FROM companies").fetchall()
    
    # Check if mega event or broad market event
    is_mega = n.get("kind") in ("mega", "shock") or "All Sectors" in str(n.get("industry", "")) or "ALL" in impacts

    with D.tx(c):
        for co in cos:
            sym = co["symbol"]
            old_price = co["price"]
            pct = 0.0

            # 1. Check direct symbol sentiment or impact mapping
            if sym in sens:
                pct = float(sens[sym])
            elif sym in impacts:
                pct = float(impacts[sym])
            elif is_mega:
                direction = float(n.get("direction", 1) or 1)
                base_impact = float(n.get("impact", 5.0) or 5.0)
                pct = direction * (base_impact / 100.0)
            else:
                # 2. Check industry mapping
                raw_ind = str(n.get("industry", ""))
                n_industries = [i.strip() for i in raw_ind.split(",") if i.strip()]
                if co["industry"] in n_industries or not n_industries:
                    direction = float(n.get("direction", 1) or 1)
                    impact_val = float(n.get("impact", 2.0) or 2.0)
                    pct = direction * (impact_val / 100.0)

            if abs(pct) < 1e-6:
                continue

            # Bounded immediate price shock (-50% to +100%)
            pct = max(-0.50, min(1.00, float(pct)))
            new_price = max(1.0, round(old_price * (1.0 + pct), 2))

            # Update company valuation
            c.execute("UPDATE companies SET prev_price=?, price=?, trend=? WHERE symbol=?",
                      (old_price, new_price, "Bullish" if pct > 0 else "Bearish", sym))

            # Update current live candlestick (OHLC) in real-time
            candle = c.execute("SELECT * FROM price_history WHERE symbol=? AND upd=?", (sym, upd)).fetchone()
            if candle:
                new_h = max(candle["h"], new_price)
                new_l = min(candle["l"], new_price)
                c.execute("UPDATE price_history SET h=?, l=?, c=? WHERE symbol=? AND upd=?",
                          (new_h, new_l, new_price, sym, upd))
            else:
                c.execute("INSERT INTO price_history(symbol,upd,o,h,l,c,v) VALUES(?,?,?,?,?,?,?)",
                          (sym, upd, old_price, max(old_price, new_price), min(old_price, new_price), new_price, 0))

            # Audit trail
            c.execute("INSERT INTO audit(ts,actor,action,detail) VALUES(?,?,?,?)",
                      (time.time(), "news_shock_engine", "immediate_price_shock",
                       json.dumps(dict(news_id=news_id, symbol=sym, price_before=old_price, price_after=new_price, impact_pct=pct * 100))))

def step(c, upd, cap=0.06, factor=1.0):
    """Executes one official market update tick (every 45 seconds). 
       Combines normalized, bounded components:
       - 50% Fundamentals and Technical indicators
       - 30% Actual team buying/selling order-flow pressure
       - 20% Geometric Brownian Motion (GBM)
    """
    rnd = random.Random(1000 + upd)
    cos = c.execute("SELECT * FROM companies").fetchall()
    
    news = c.execute("SELECT * FROM news WHERE released=1 AND ? - released_upd < duration", (upd,)).fetchall()
    is_mega = any(n.get("kind") in ("mega", "shock") or "All Sectors" in str(n.get("industry", "")) for n in news)
    if is_mega: 
        cap = max(cap, 0.20)
    
    # Fetch team order flow pressures (30% weight component)
    orders_pressure = {}
    ord_rows = c.execute("SELECT symbol, side, SUM(qty) as tot_qty FROM orders GROUP BY symbol, side").fetchall()
    for r in ord_rows:
        sym = r["symbol"]
        qty = r["tot_qty"] or 0
        score_dir = 1.0 if r["side"] == "BUY" else -1.0
        orders_pressure[sym] = orders_pressure.get(sym, 0.0) + (qty * score_dir)

    tot = 0
    for co in cos:
        sym = co["symbol"]
        old_price = co["price"]
        
        hist = [r[0] for r in c.execute("SELECT c FROM price_history WHERE symbol=? ORDER BY upd", (sym,))]
        a = analysis(hist)
        
        # Component 1: Fundamentals & Technicals (50% weight)
        fund_score = float(co["fund"] or 50.0)
        tech_score = float(a["tech"] or 50.0)
        fund_tech_combined = (0.6 * fund_score) + (0.4 * tech_score) # 0 to 100 scale
        fund_tech_return = (fund_tech_combined - 50.0) / 500.0  # Normalized bounded return (-0.10 to +0.10)
        
        # Component 2: Team Order Flow Pressure (30% weight)
        net_flow = orders_pressure.get(sym, 0.0)
        flow_return = max(-0.05, min(0.05, net_flow / 50000.0)) # Normalized bounded return
        
        # Component 3: Geometric Brownian Motion (GBM) (20% weight)
        beta = float(co["beta"] or 1.0)
        mu = 0.001 * beta
        sigma = float(co["vol"] or 0.02) * factor
        dt = 1.0
        z = rnd.gauss(0, 1)
        gbm_return = (mu - 0.5 * (sigma ** 2)) * dt + sigma * math.sqrt(dt) * z
        gbm_return = max(-0.08, min(0.08, gbm_return))
        
        # Weighted combination (50% Fund/Tech, 30% Order Flow, 20% GBM)
        combined_return = (0.50 * fund_tech_return) + (0.30 * flow_return) + (0.20 * gbm_return)
        
        # Add active news impact if any
        imp = 0.0
        for n in news:
            symbols = [s.strip() for s in str(n.get("symbols", "")).split(",") if s.strip()]
            raw_ind = str(n.get("industry", ""))
            n_industries = [i.strip() for i in raw_ind.split(",") if i.strip()]
            
            try:
                sn = json.loads(n["sens"] or "{}")
            except Exception:
                sn = {}
            
            mult = 1.0
            if is_mega or "All Sectors" in raw_ind:
                mult = 1.0
            elif sym in sn:
                mult = sn[sym]
            elif co["industry"] in n_industries:
                mult = 1.2 if co["industry"] == n_industries[0] else 0.75
            else:
                mult = 0.30

            if sym in symbols or co["industry"] in n_industries or is_mega or "All Sectors" in raw_ind:
                direction = float(n.get("direction", 1) or 1)
                impact_val = float(n.get("impact", 0.0) or 0.0)
                imp += direction * (impact_val / 100.0) * mult

        total_return = max(-cap * factor, min(cap * factor, combined_return + imp))
        cl = round(max(1.0, old_price * (1.0 + total_return)), 2)
        hi = round(max(old_price, cl) * (1.0 + abs(rnd.gauss(0, 0.003))), 2)
        lo = round(min(old_price, cl) * (1.0 - abs(rnd.gauss(0, 0.003))), 2)
        
        c.execute("INSERT INTO price_history(symbol,upd,o,h,l,c,v) VALUES(?,?,?,?,?,?,?)", (sym, upd, old_price, hi, lo, cl, 0))
        c.execute("UPDATE companies SET prev_price=price, price=?, trend=?, tech=? WHERE symbol=?", (cl, a["trend"], a["tech"], sym))
        tot += cl / co["start_price"]
        
    return round(tot / len(cos) * 1000, 2)

def index(c):
    res = c.execute("SELECT AVG(price/start_price)*1000 FROM companies").fetchone()[0]
    return round(res or 1000, 2)
