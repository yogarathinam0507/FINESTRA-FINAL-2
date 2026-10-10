import time, database as D
class TradeError(Exception): pass
def mode(c): return "normal"          # Round 1 has no intraday phase
def brokerage_rate(c): return float(D.get(c, "brk_normal"))/100
def leverage(c): return 1.0
def margin(c, team_id):
    """Margin snapshot. equity=cash+holdings value; exposure=holdings value; buying power = L*equity - exposure."""
    t=c.execute("SELECT cash FROM teams WHERE id=?",(team_id,)).fetchone()
    mv=c.execute("SELECT COALESCE(SUM(h.qty*k.price),0) FROM holdings h JOIN companies k ON k.symbol=h.symbol WHERE h.team_id=?",(team_id,)).fetchone()[0]
    L=leverage(c); cash=t["cash"]; eq=cash+mv; bp=max(0.0, L*eq-mv)
    return dict(mode=mode(c), leverage=L, cash=round(cash,2), equity=round(eq,2), exposure=round(mv,2), borrowed=round(max(0,-cash),2),
        buying_power=round(bp,2), margin_available=round(bp,2), exposure_ratio=round(mv/eq,2) if eq>0 else 0, max_leverage=L)
def max_buy_qty(c, team_id, price, inventory):
    m=margin(c,team_id); r=brokerage_rate(c)
    if m["leverage"]<=1: q=max(0,m["cash"])/(price*(1+r))
    else: q=m["buying_power"]/(price*(1+m["leverage"]*r))
    return int(max(0,min(inventory,q)))
def quote(c, symbol, side, qty, team_id=None):
    co=c.execute("SELECT * FROM companies WHERE symbol=?",(symbol,)).fetchone()
    if not co: raise TradeError("Unknown stock")
    val=round(co["price"]*qty,2); r=brokerage_rate(c); b=round(val*r,2)
    q=dict(price=co["price"],value=val,brokerage=b,rate=r*100,mode=mode(c),total=val+b if side=="BUY" else val-b,buy_total=round(val+b,2),sell_total=round(val-b,2),inventory=co["inventory"])
    if team_id:
        m=margin(c,team_id); h=c.execute("SELECT qty FROM holdings WHERE team_id=? AND symbol=?",(team_id,symbol)).fetchone()
        q.update(margin=m, held=h["qty"] if h else 0, max_buy=max_buy_qty(c,team_id,co["price"],co["inventory"]), margin_required=round(val/m["leverage"],2))
    return q
def execute(c, team_id, symbol, side, qty, client_id):
    if D.get(c,"status")!="running" or D.get(c,"stage_cur") not in ("test","r1"): raise TradeError("Trading is not open")
    if not isinstance(qty,int) or isinstance(qty,bool) or qty<=0: raise TradeError("Quantity must be a positive whole number")
    if side not in ("BUY","SELL"): raise TradeError("Invalid side")
    c.execute("BEGIN IMMEDIATE")
    try:
        if c.execute("SELECT 1 FROM orders WHERE client_id=?",(client_id,)).fetchone(): raise TradeError("Duplicate order ignored")
        t=c.execute("SELECT * FROM teams WHERE id=?",(team_id,)).fetchone()
        if not t or t["status"]!="approved": raise TradeError("Team is not active")
        co=c.execute("SELECT * FROM companies WHERE symbol=?",(symbol,)).fetchone()
        if not co or co["status"]!="Open": raise TradeError("Stock not available")
        q=quote(c,symbol,side,qty); h=c.execute("SELECT * FROM holdings WHERE team_id=? AND symbol=?",(team_id,symbol)).fetchone()
        if side=="BUY":
            if co["inventory"]<qty: raise TradeError("Insufficient market inventory")
            m=margin(c,team_id); L=m["leverage"]
            if L<=1:
                if t["cash"]<q["total"]: raise TradeError("Insufficient cash")
            else:  # leveraged intraday: post-trade exposure must stay within L x post-trade equity
                eq_after=m["equity"]-q["brokerage"]
                if eq_after<=0 or m["exposure"]+q["value"]>L*eq_after+1e-6:
                    raise TradeError(f"Margin limit exceeded ({L:g}x). Max you can buy now: {max_buy_qty(c,team_id,co['price'],co['inventory'])} shares")
            nq=(h["qty"] if h else 0)+qty; avg=((h["avg"]*h["qty"] if h else 0)+q["value"])/nq
            c.execute("INSERT INTO holdings VALUES(?,?,?,?) ON CONFLICT(team_id,symbol) DO UPDATE SET qty=?,avg=?",(team_id,symbol,nq,avg,nq,avg))
            c.execute("UPDATE companies SET inventory=inventory-?,volume=volume+? WHERE symbol=?",(qty,qty,symbol))
            c.execute("UPDATE teams SET cash=cash-?,brokerage=brokerage+?,trades=trades+1 WHERE id=?",(q["total"],q["brokerage"],team_id))
        else:
            if not h or h["qty"]<qty: raise TradeError("Insufficient holdings")
            c.execute("UPDATE holdings SET qty=qty-? WHERE team_id=? AND symbol=?",(qty,team_id,symbol))
            c.execute("DELETE FROM holdings WHERE qty=0")
            c.execute("UPDATE companies SET inventory=inventory+?,volume=volume+? WHERE symbol=?",(qty,qty,symbol))
            c.execute("UPDATE teams SET cash=cash+?,brokerage=brokerage+?,trades=trades+1 WHERE id=?",(q["total"],q["brokerage"],team_id))
        c.execute("INSERT INTO orders(client_id,team_id,symbol,side,qty,price,brokerage,mode,upd,ts) VALUES(?,?,?,?,?,?,?,?,?,?)",(client_id,team_id,symbol,side,qty,q["price"],q["brokerage"],q["mode"],int(D.get(c,"upd")),time.time()))
        c.execute("COMMIT"); return q
    except Exception:
        c.execute("ROLLBACK"); raise
