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
    cap = p["cap"]
    v = max(p["value"], 1)
    
    # 1. Returns Score: Base 30 points for 0% return. Negative returns reduce from 30, positive increase above 30.
    ret_score = 30.0 + p["ret"]
    ret = max(0.0, min(50.0, ret_score))
    
    # 2. Cash Management Score: Target 10% to 40% cash buffer (optimal 25%)
    cr = t["cash"] / v
    cash = 10 if 0.1 <= cr <= 0.4 else max(0, 10 - abs(cr - 0.25) * 20)
    
    # 3. Discipline Score: Dynamically reacts to trading activity, brokerage drag, and penalties
    trade_count = t.get("trades", 0)
    if trade_count > 0:
        brokerage_ratio = (t.get("brokerage", 0.0) / cap) * 100
        penalty_ratio = (t.get("penalties", 0.0) / cap) * 100
        disc = max(0.0, 20.0 - (brokerage_ratio * 10.0) - (penalty_ratio * 10.0))
    else:
        disc = 0.0
    disc = min(20.0, disc)
    
    # 4. Risk Score: Dynamic based on portfolio concentration and position exposure
    holdings = p["holdings"]
    if holdings:
        w = [h["price"] * h["qty"] for h in holdings]
        total_holding_value = sum(w)
        conc = max(w) / total_holding_value if total_holding_value > 0 else 1.0
        risk = 15.0 * (1.0 - conc)  # Penalize high asset concentration
        lev = total_holding_value / v if v > 0 else 0
        if lev > 1.0:
            risk *= max(0.0, 1.0 - (lev - 1.0) * 0.2)
    else:
        risk = 0.0
    risk = max(0.0, min(15.0, risk))
    
    # 5. Diversification Score: Evaluated strictly by the number of unique companies invested in
    num_companies = len(holdings)
    target_companies = 5.0  # Target 5 unique stocks for full diversification points
    div = min(15.0, (num_companies / target_companies) * 15.0)
    
    parts = dict(
        returns=round(ret, 2),
        cash=round(cash, 2),
        discipline=round(disc, 2),
        risk=round(risk, 2),
        diversification=round(div, 2)
    )
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
