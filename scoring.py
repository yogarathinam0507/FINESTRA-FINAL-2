import database as D

def portfolio(c, tid):
    t = c.execute("SELECT * FROM teams WHERE id=?", (tid,)).fetchone()
    hs = c.execute("SELECT h.*,k.price,k.industry,k.name FROM holdings h JOIN companies k ON k.symbol=h.symbol WHERE team_id=?", (tid,)).fetchall()
    inv = sum(h["avg"] * h["qty"] for h in hs)
    mv = sum(h["price"] * h["qty"] for h in hs)
    cap = float(D.get(c, "capital"))
    val = t["cash"] + mv
    return dict(team=t, holdings=hs, invested=inv, market=mv, value=val, pnl=val - cap, ret=(val / cap - 1) * 100, cap=cap)

def score(c, tid):
    p = portfolio(c, tid)
    t = p["team"]
    v = max(p["value"], 1)
    
    # 1. Return Points (Max 60 pts):
    # Baseline: 25 points for 0% return. +1 per +1% gain, -1 per -2% loss. Capped between 0 and 60.
    portfolio_ret = p["ret"]
    if portfolio_ret >= 0:
        ret_score = 25.0 + portfolio_ret
    else:
        ret_score = 25.0 + (portfolio_ret / 2.0)
    ret = round(max(0.0, min(60.0, ret_score)), 2)
    
    # 2. Cash Management Points (Max 10 pts):
    # 5% - 10% reserve -> 9 pts
    # 11% - 20% reserve -> 6 pts
    # Above 20% or below 5% -> 3 pts
    cr = (t["cash"] / v) * 100
    if 5.0 <= cr <= 10.0:
        cash = 9.0
    elif 11.0 <= cr <= 20.0:
        cash = 6.0
    else:
        cash = 3.0
        
    # 3. Diversification Points (Max 20 pts):
    # Starts at 0 before trading. Evaluated by max single-sector share of portfolio value.
    holdings = p["holdings"]
    trade_count = t["trades"] if "trades" in t.keys() else 0
    
    if trade_count == 0 or not holdings:
        div = 0.0
    else:
        sector_totals = {}
        total_portfolio_value = v
        for h in holdings:
            sec = h["industry"]
            val_h = h["price"] * h["qty"]
            sector_totals[sec] = sector_totals.get(sec, 0.0) + val_h
            
        max_sector_share = max(sector_totals.values()) / total_portfolio_value if total_portfolio_value > 0 else 0.0
        share_pct = max_sector_share * 100.0
        
        if share_pct <= 20.0:
            div = 18.5  # Range 17 - 20
        elif 20.0 < share_pct <= 40.0:
            div = 13.0  # Range 11 - 15
        else:
            div = 6.0   # Range 5 - 7
            
    # 4. Beta Points (Max 10 pts replacing Risk):
    # Default/starting point is 8 (Beta = 1.0). Scales based on portfolio beta performance relative to market index.
    if holdings:
        total_holding_val = sum(h["price"] * h["qty"] for h in holdings)
        if total_holding_val > 0:
            betas = {row["symbol"]: row["beta"] for row in c.execute("SELECT symbol, beta FROM companies").fetchall()}
            weighted_beta = sum((h["price"] * h["qty"] / total_holding_val) * betas.get(h["symbol"], 1.0) for h in holdings)
        else:
            weighted_beta = 1.0
    else:
        weighted_beta = 1.0
        
    if weighted_beta > 1.3 and portfolio_ret > 0:
        beta_score = 10.0
    elif 1.0 <= weighted_beta <= 1.25:
        beta_score = 9.0
    elif weighted_beta == 1.0:
        beta_score = 8.0  # Starting point
    elif 0.7 < weighted_beta < 1.0:
        beta_score = 6.0
    else:
        beta_score = 5.0
        
    parts = dict(
        returns=ret,
        cash=cash,
        diversification=div,
        beta=beta_score
    )
    
    # Total sums to exactly 100 max points (60 + 10 + 20 + 10)
    return dict(
        total=round(sum(parts.values()), 2),
        parts=parts,
        value=round(p["value"], 2),
        ret=round(p["ret"], 2)
    )

def leaderboard(c):
    rows = []
    for t in c.execute("SELECT id, name, status, prev_rank FROM teams WHERE status='approved'"):
        s = score(c, t["id"])
        rows.append(dict(id=t["id"], team=t["name"], status=t["status"], prev=t["prev_rank"], **s))
    rows.sort(key=lambda r: (-r["total"], -r["ret"], -r["value"], r["id"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = rows[i - 2]["rank"] if i > 1 and (r["total"], r["ret"], r["value"]) == (rows[i - 2]["total"], rows[i - 2]["ret"], rows[i - 2]["value"]) else i
        r["move"] = (r["prev"] - r["rank"]) if r["prev"] else 0
    return rows
