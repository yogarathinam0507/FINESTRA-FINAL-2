import database as D

def portfolio(c, tid):
    t = c.execute("SELECT * FROM teams WHERE id=?", (tid,)).fetchone()
    hs = c.execute("SELECT h.*,k.price,k.industry,k.name FROM holdings h JOIN companies k ON k.symbol=h.symbol WHERE team_id=?", (tid,)).fetchall()
    inv = sum(h["avg"] * h["qty"] for h in hs)
    mv = sum(h["price"] * h["qty"] for h in hs)
    cap = float(D.get(c, "capital"))
    val = t["cash"] + mv
    return dict(team=t, holdings=hs, invested=inv, market=mv, value=val, pnl=val - cap, ret=(val / cap - 1) * 100, cap=cap)

def get_expenditure_tier(invested):
    """Categorizes total portfolio expenditure into tiers."""
    if invested < 300_000:
        return "below_3l"
    elif 300_000 <= invested < 500_000:
        return "3l_to_5l"
    elif 500_000 <= invested < 700_000:
        return "5l_to_7l"
    else:
        return "above_7l"

def score(c, tid):
    p = portfolio(c, tid)
    t = p["team"]
    invested = p["invested"]  # Total expenditure
    cash = t["cash"]
    portfolio_ret = p["ret"]
    
    tier = get_expenditure_tier(invested)
    
    # ==========================================
    # 1. Return Score (Max 60 Points)
    # ==========================================
    base_returns_map = {
        "below_3l": 10.0,
        "3l_to_5l": 21.0,
        "5l_to_7l": 28.0,
        "above_7l": 35.0
    }
    base_ret = base_returns_map[tier]
    
    if portfolio_ret >= 0:
        ret_adjustment = portfolio_ret * 3.0
        ret_score = base_ret + ret_adjustment
    else:
        ret_adjustment = abs(portfolio_ret) * 1.5
        ret_score = base_ret - ret_adjustment
        
    ret = round(max(0.0, min(60.0, ret_score)), 2)
    
    # ==========================================
    # 2. Cash Management Points (Max 10 Points)
    # ==========================================
    if cash <= 50_000:
        cash_score = 7.0
    elif 50_000 < cash <= 150_000:
        cash_score = 9.0
    elif 150_000 < cash <= 200_000:
        cash_score = 8.0
    else:
        # Deduct 1 point for each completed additional 50,000 above 2,00,000 starting from 8 points
        excess = cash - 200_000
        steps = int(excess // 50_000)
        cash_score = float(max(0, 8 - steps))
        
    cash_pts = round(max(0.0, min(10.0, cash_score)), 2)
        
    # ==========================================
    # 3. Diversification Points (Max 20 Points)
    # ==========================================
    holdings = p["holdings"]
    total_market_value = p["market"]
    
    div = 0.0
    if holdings and total_market_value > 0:
        sector_totals = {}
        for h in holdings:
            sec = h["industry"]
            val_h = h["price"] * h["qty"]
            sector_totals[sec] = sector_totals.get(sec, 0.0) + val_h
            
        sector_allocations = {sec: val / total_market_value for sec, val in sector_totals.items()}
        
        # Determine classification: High, Medium, or Low
        # High: Every sector allocation is <= 30% (0.30) and at least 3 sectors are meaningful (> 0 and <= 0.30)
        meaningful_sectors = sum(1 for alloc in sector_allocations.values() if 0 < alloc <= 0.30)
        all_within_30 = all(alloc <= 0.30 for alloc in sector_allocations.values())
        
        if all_within_30 and meaningful_sectors >= 3:
            classification = "high"
        elif sum(1 for alloc in sector_allocations.values() if alloc > 0.30) >= 2:
            classification = "medium"
        else:
            classification = "low"
            
        div_table = {
            "below_3l": {"high": 0.0, "medium": 0.0, "low": 0.0},
            "3l_to_5l": {"high": 10.0, "medium": 8.0, "low": 5.0},
            "5l_to_7l": {"high": 14.0, "medium": 10.0, "low": 7.0},
            "above_7l": {"high": 18.0, "medium": 13.0, "low": 9.0}
        }
        div = float(div_table[tier][classification])
        
    # ==========================================
    # 4. Beta Points (Max 10 Points)
    # ==========================================
    # Calculate market index return as average return across all companies
    comp_rows = c.execute("SELECT start_price, price FROM companies").fetchall()
    if comp_rows:
        market_returns = [(row["price"] / row["start_price"] - 1) * 100 for row in comp_rows if row["start_price"] > 0]
        market_index_ret = sum(market_returns) / len(market_returns) if market_returns else 0.0
    else:
        market_index_ret = 0.0
        
    # Calculate Beta safely handling zero or near-zero index returns
    if abs(market_index_ret) < 1e-5:
        portfolio_beta = 1.0
    else:
        portfolio_beta = portfolio_ret / market_index_ret
        
    beta_table = {
        "below_3l": {"high": 0.0, "mid": 0.0, "low": 0.0},
        "3l_to_5l": {"high": 7.0, "mid": 5.0, "low": 3.0},
        "5l_to_7l": {"high": 8.0, "mid": 6.0, "low": 4.0},
        "above_7l": {"high": 9.0, "mid": 7.0, "low": 5.0}
    }
    
    if portfolio_beta > 1.3:
        b_cat = "high"
    elif 0.8 <= portfolio_beta <= 1.3:
        b_cat = "mid"
    else:
        b_cat = "low"
        
    beta_score = float(beta_table[tier][b_cat])
        
    parts = dict(
        returns=ret,
        cash=cash_pts,
        diversification=div,
        beta=beta_score
    )
    
    total_score = round(sum(parts.values()), 2)
    
    return dict(
        total=total_score,
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
