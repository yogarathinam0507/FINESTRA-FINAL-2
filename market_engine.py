import random, math, json, database as D

def sma(x, n): return sum(x[-n:]) / min(n, len(x)) if x else 0

def ema(x, n):
    k = 2 / (n + 1); e = x[0]
    for p in x[1:]: e = p * k + e * (1 - k)
    return e

def rsi(x, n=14):
    if len(x) < 2: return 50
    d = [x[i] - x[i-1] for i in range(max(1, len(x) - n), len(x))]
    g = sum(v for v in d if v > 0); l = -sum(v for v in d if v < 0)
    return 100 if l == 0 and g > 0 else 50 if l == 0 else 100 - 100 / (1 + g / l)

def macd(x): return ema(x, 12) - ema(x, 26) if len(x) > 1 else 0

def analysis(closes):
    r = rsi(closes); m = macd(closes); s5, s20 = sma(closes, 5), sma(closes, 20)
    mom = (closes[-1] / closes[-min(5, len(closes))] - 1) * 100 if closes else 0
    score = 50 + (10 if s5 > s20 else -10) + (10 if m > 0 else -10) + (5 if 50 < r < 70 else -5 if r > 70 or r < 30 else 0)
    return dict(rsi=round(r, 1), macd=round(m, 2), sma5=round(s5, 2), sma20=round(s20, 2), momentum=round(mom, 2), 
                support=min(closes[-20:]) if closes else 0, resistance=max(closes[-20:]) if closes else 0,
                trend="Bullish" if s5 >= s20 else "Bearish", tech=max(0, min(100, score)))

def step(c, upd, cap=0.06, factor=1.0):
    """One official market update: guarantees price updates and handles multi-industry news cascades (2-3 for surprise, 1-2 for manual)."""
    rnd = random.Random(1000 + upd)
    cos = c.execute("SELECT * FROM companies").fetchall()
    
    # Fetch all released news active in this update window
    news = c.execute("SELECT * FROM news WHERE released=1 AND ? - released_upd < duration", (upd,)).fetchall()
    if any(n.get("kind") == "mega" for n in news): cap = max(cap, 0.15)
    
    mkt = rnd.gauss(0, 0.008)
    key = lambda x: x["symbol"] if x["industry"] == "Commodity-Linked" else x["industry"]
    ind = {key(x): rnd.gauss(0, 0.005 if x["industry"] != "Commodity-Linked" else 0.009) for x in cos}
    tot = 0
    
    for co in cos:
        hist = [r[0] for r in c.execute("SELECT c FROM price_history WHERE symbol=? ORDER BY upd", (co["symbol"],))]
        a = analysis(hist)
        mom = (a["momentum"] / 100) * 0.15
        
        def mult(n):
            sn = json.loads(n["sens"]) if n["sens"] else {}
            if co["symbol"] in sn:
                return sn[co["symbol"]]
            
            # Multi-industry cascade parsing supporting comma-separated industries (1-2 for manual, 2-3 for surprise)
            raw_ind = n.get("industry", "")
            n_industries = [i.strip() for i in raw_ind.split(",") if i.strip()]
            
            if co["industry"] in n_industries:
                # Primary industry gets full impact, secondary industries get spillover weight
                return 1.2 if co["industry"] == n_industries[0] else 0.7
            return 0.35 # Baseline market spillover
            
        # Compute total impact from all active manual and surprise news affecting this company/industry
        imp = 0.0
        for n in news:
            symbols = [s.strip() for s in n.get("symbols", "").split(",") if s.strip()]
            raw_ind = n.get("industry", "")
            n_industries = [i.strip() for i in raw_ind.split(",") if i.strip()]
            
            matches_symbol = co["symbol"] in symbols
            matches_industry = co["industry"] in n_industries
            
            if matches_symbol or matches_industry:
                direction = float(n.get("direction", 1))
                impact_val = float(n.get("impact", 0.0))
                imp += direction * impact_val / 100.0 * mult(n)
                
        # Fundamental drift to keep companies moving
        drift = (co["fund"] - 50) / 100 * 0.0005
        
        # Ensure minimum volatility so prices never freeze completely
        noise = rnd.gauss(0, 0.006 * max(0.5, co["vol"]))
        r = co["beta"] * mkt + ind[key(co)] + drift + mom + imp + noise
        r = max(-cap * factor, min(cap * factor, r * factor))
        
        o = co["price"]
        cl = round(max(1.0, o * (1 + r)), 2)
        hi = round(max(o, cl) * (1 + abs(rnd.gauss(0, 0.003))), 2)
        lo = round(min(o, cl) * (1 - abs(rnd.gauss(0, 0.003))), 2)
        
        c.execute("INSERT INTO price_history(symbol,upd,o,h,l,c,v) VALUES(?,?,?,?,?,?,?)", (co["symbol"], upd, o, hi, lo, cl, 0))
        c.execute("UPDATE companies SET prev_price=price, price=?, trend=?, tech=? WHERE symbol=?", (cl, a["trend"], a["tech"], co["symbol"]))
        tot += cl / co["start_price"]
        
    return round(tot / len(cos) * 1000, 2)

def index(c):
    r = c.execute("SELECT AVG(price/start_price)*1000 FROM companies").fetchone()[0]
    return round(r or 1000, 2)
