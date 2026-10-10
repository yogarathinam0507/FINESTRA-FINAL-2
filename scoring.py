import database as D
def portfolio(c, tid):
    t=c.execute("SELECT * FROM teams WHERE id=?",(tid,)).fetchone()
    hs=c.execute("SELECT h.*,k.price,k.industry,k.name FROM holdings h JOIN companies k ON k.symbol=h.symbol WHERE team_id=?",(tid,)).fetchall()
    inv=sum(h["avg"]*h["qty"] for h in hs); mv=sum(h["price"]*h["qty"] for h in hs); cap=float(D.get(c,"capital"))
    val=t["cash"]+mv
    return dict(team=t,holdings=hs,invested=inv,market=mv,value=val,pnl=val-cap,ret=(val/cap-1)*100,cap=cap)
def score(c, tid):
    p=portfolio(c,tid); t=p["team"]; cap=p["cap"]; v=max(p["value"],1)
    ret=max(0,min(50,(p["ret"]+10)/30*50))                       # -10%..+20% maps to 0..50
    cr=t["cash"]/v; cash=10 if .1<=cr<=.4 else max(0,10-abs(cr-.25)*20)   # target 10-40% cash
    disc=min(20,max(0,20-(t["brokerage"]/cap*100)*8-t["penalties"]/cap*100*10)) if t["trades"]>0 else 0   # brokerage drag & penalties; a team that never trades earns no discipline credit
    w=[h["price"]*h["qty"] for h in p["holdings"]]; conc=max(w)/sum(w) if w else 1
    risk=10*(1-max(0,conc-.25)/.75) if w else 0                      # no positions = no risk management to reward (no free points)
    lev=sum(w)/v if w else 0; risk*=1-min(1,max(0,lev-1)/4)*0.6   # leveraged exposure reduces risk-control points
    inds={h["industry"] for h in p["holdings"]}; div=min(10,len(inds)/4*10)
    parts=dict(returns=round(ret,2),cash=round(cash,2),discipline=round(disc,2),risk=round(risk,2),diversification=round(div,2))
    return dict(total=round(sum(parts.values()),2),parts=parts,value=round(p["value"],2),ret=round(p["ret"],2))
def leaderboard(c):
    rows=[]
    for t in c.execute("SELECT id,name,status,prev_rank FROM teams WHERE status='approved'"):          # only active teams are ranked
        s=score(c,t["id"]); rows.append(dict(id=t["id"],team=t["name"],status=t["status"],prev=t["prev_rank"],**s))
    rows.sort(key=lambda r:(-r["total"],-r["ret"],-r["value"],r["id"]))                                  # strictly by calculated points; id only keeps the order stable
    for i,r in enumerate(rows,1):
        r["rank"]=rows[i-2]["rank"] if i>1 and (r["total"],r["ret"],r["value"])==(rows[i-2]["total"],rows[i-2]["ret"],rows[i-2]["value"]) else i      # equal scores share a rank
        r["move"]=(r["prev"]-r["rank"]) if r["prev"] else 0
    return rows
