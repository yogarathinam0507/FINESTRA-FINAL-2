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
    """One official market update: generates a price + OHLC candle for all 20 stocks with balanced sector drift."""
    rnd = random.Random(1000 + upd)
    cos = c.execute("SELECT * FROM companies").fetchall()
    news = c.execute("SELECT * FROM news WHERE released=1 AND ? - released_upd < duration", (upd,)).fetchall()
    if any(n["kind"] == "mega" for n in news): cap = max(cap, 0.15)
    
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
            return sn[co["symbol"]] if co["symbol"] in sn else (1.2 if co["industry"] == n["industry"] else 0.6)
            
        imp = sum(n["direction"] * n["impact"] / 100 * mult(n) for n in news if co["symbol"] in n["symbols"].split(","))
        
        # Fixed: Reduced and re-centered fundamental drift to prevent banking sector runaway compounding
        drift = (co["fund"] - 50) / 100 * 0.0005
        
        r = co["beta"] * mkt + ind[key(co)] + drift + mom + imp + rnd.gauss(0, 0.006 * co["vol"])
        r = max(-cap * factor, min(cap * factor, r * factor))
        
        o = co["price"]
        cl = round(max(1, o * (1 + r)), 2)
        hi = round(max(o, cl) * (1 + abs(rnd.gauss(0, 0.003))), 2)
        lo = round(min(o, cl) * (1 - abs(rnd.gauss(0, 0.003))), 2)
        
        c.execute("INSERT INTO price_history(symbol,upd,o,h,l,c,v) VALUES(?,?,?,?,?,?,?)", (co["symbol"], upd, o, hi, lo, cl, 0))
        c.execute("UPDATE companies SET prev_price=price, price=?, trend=?, tech=? WHERE symbol=?", (cl, a["trend"], a["tech"], co["symbol"]))
        tot += cl / co["start_price"]
        
    return round(tot / len(cos) * 1000, 2)

def index(c):
    r = c.execute("SELECT AVG(price/start_price)*1000 FROM companies").fetchone()[0]
    return round(r or 1000, 2)
