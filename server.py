import asyncio, json, math, os, secrets, socket, time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
import database as D, auth, seed_data, market_engine as M, trading_engine as T, scoring as S, schedule, flow, r2_engine as R2

BASE = os.path.dirname(os.path.abspath(__file__))
app = FastAPI(title="FINestra @Doms, AU")
C = D.conn(); D.init(C); seed_data.seed(C)
if not C.execute("SELECT 1 FROM r2_news").fetchone() or (D.get(C, "stage_cur") in (None, "", "idle", "test", "r1", "trans1") and any(C.execute("SELECT COUNT(*) FROM r2_news WHERE rnd=?", (r_,)).fetchone()[0] != R2.SEED.N_NOW + R2.SEED.N_FUT for r_ in (1, 2, 3))): R2.gen_news(C)
clients = set()
R1_STAGES = ("test", "r1")

def clock(c=C):
    el = float(D.get(c, "elapsed"))
    if D.get(c, "status") == "running": el += (time.time() - float(D.get(c, "run_since"))) * float(D.get(c, "time_scale"))
    h = D.get(c, "hold_at")
    if h not in (None, ""): el = min(el, float(h))
    D.put(c, "elapsed_now", el); return el

def audit(actor, action, detail=""): C.execute("INSERT INTO audit(ts,actor,action,detail) VALUES(?,?,?,?)", (time.time(), actor, action, detail))

async def broadcast(kind="update", sounds=None):
    msg = json.dumps({"type": kind, "upd": int(D.get(C, "upd")), "stage": D.get(C, "stage_cur"), "sounds": sounds or []})
    for ws in list(clients):
        try: await ws.send_text(msg)
        except Exception: clients.discard(ws)

async def push(kind="update"):
    snd = R2.SOUNDS[:]; R2.SOUNDS.clear(); await broadcast(kind, snd)

def need(req: Request, *roles):
    s = auth.who(C, req.headers.get("x-token"))
    if not s or s["role"] not in roles: raise HTTPException(401, "Not authorised")
    if s["role"] == "team" and not C.execute("SELECT 1 FROM teams WHERE id=?", (s["ref"],)).fetchone(): raise HTTPException(401, "Team no longer exists")
    return s

# ---------- event flow ----------
def mcfg(name):
    t = float(D.get(C, "tick_sec"))
    if name == "r1": return (t, float(D.get(C, "final_tick")), float(D.get(C, "r1_sec")) - float(D.get(C, "final5_sec")), float(D.get(C, "r1_sec")))
    return (t, t, float(D.get(C, "test_sec")), float(D.get(C, "test_sec")))

def cur_stage():
    st = D.get(C, "status")
    return "ended" if st == "ended" else ("idle" if st == "idle" else D.get(C, "stage_cur"))

def state():
    el = clock(); st = D.get(C, "status"); name = cur_stage(); tot = flow.total(C)
    s0, e0 = flow.bounds(C, name) if name in flow.ORDER else ((tot, tot) if name == "ended" else (0, 0)); rel = el - s0
    ph = flow.phase(C, name, rel) if name in flow.ORDER else name; pe = e0
    if name in ("a1", "a2", "a3"):
        ns, ds = float(D.get(C, "news_sec")), float(D.get(C, "disc_sec")); pe = s0 + (ns if ph == "newsletter" else ns + ds if ph == "discussion" else e0 - s0)
    hold = D.get(C, "hold_at") not in (None, "") and name == "trans1"
    out = dict(waiting=hold, status=st, stage=name, label=flow.LABELS.get(name, name), phase=ph, round=flow.ROUND_OF.get(name), stage_start=s0, stage_end=e0, phase_end=pe, stage_remaining=max(0, e0 - el),
        elapsed=el, total=tot, scale=float(D.get(C, "time_scale")), test=name == "test", index=M.index(C), brokerage=T.brokerage_rate(C) * 100, update=int(D.get(C, "upd")),
        r1_done=bool(D.get(C, "r1_results")), disclaimer="SIMULATION DATA – NOT REAL SECURITIES", r2_round=int(D.get(C, "r2_round", 0)))
    if name in R1_STAGES:
        tick, itick, ia, total = mcfg(name); upd = int(D.get(C, "upd")); mx = schedule.max_update(tick, itick, ia, total); f5 = name == "r1" and rel >= ia
        nat = s0 + schedule.update_time(upd + 1, tick, itick, ia) if upd < mx and st in ("running", "paused") else None
        out.update(max_update=mx, next_at=nat, next_update_in=None if nat is None else max(0, nat - el), interval=itick if f5 else tick, final5=f5)
    else: out.update(final5=False, next_at=None, next_update_in=None, max_update=0, interval=0)
    ne = []
    if name in R1_STAGES and st in ("running", "paused"):
        for n in C.execute("SELECT kind,release_t FROM news WHERE released=0 AND release_t IS NOT NULL AND release_t>? AND release_t<=? ORDER BY release_t LIMIT 3", (rel, rel + 120 * float(D.get(C, "time_scale")))):
            ne.append(dict(type="mega" if n["kind"] == "mega" else "event", at=s0 + n["release_t"]))
    out["next_events"] = ne
    return out

def stocks():
    return [dict(r) for r in C.execute("SELECT symbol,name,industry,price,prev_price,inventory,issued,volume,beta,vol,fund,tech,trend,status,start_price FROM companies")]

def market_reset():
    cap = D.get(C, "capital")
    with D.tx(C):
        for t in ("holdings", "orders", "price_history", "leaderboard_snapshots"): C.execute(f"DELETE FROM {t}")
        C.execute("UPDATE teams SET cash=?,brokerage=0,penalties=0,trades=0,prev_rank=0", (cap,))
        C.execute("UPDATE companies SET price=start_price,prev_price=start_price,inventory=issued,volume=0,trend='Neutral'")
        C.execute("INSERT INTO price_history(symbol,upd,o,h,l,c,v) SELECT symbol,0,start_price,start_price,start_price,start_price,0 FROM companies")
        C.execute("UPDATE news SET released=0,released_upd=NULL"); D.put(C, "upd", 0); D.put(C, "final5_on", "0")
        D.put(C, "chart_epoch", int(float(D.get(C, "chart_epoch") or 0)) + 1)

def freeze_r1():
    lb = S.leaderboard(C); D.put(C, "r1_results", json.dumps(lb)); C.execute("INSERT INTO leaderboard_snapshots(upd,data) VALUES(?,?)", (int(D.get(C, "upd")), json.dumps(lb)))
    audit("system", "round1_frozen", json.dumps([(r["rank"], r["team"], r["value"]) for r in lb]))

def enter_stage(n, prev, start):
    if prev in flow.R2_STAGES: R2.close_round(C, flow.ROUND_OF[prev], start)
    if n == "test": market_reset(); seed_data.assign_news_times(C, "test")
    elif n == "r1": market_reset(); seed_data.assign_news_times(C, "r1"); R2.SOUNDS.append("bell")
    elif n == "trans1":
        freeze_r1()
        if flow.stage_at(C, clock())[0] == "trans1": D.put(C, "elapsed", start); D.put(C, "run_since", time.time()); D.put(C, "hold_at", start)
    elif n == "r2pre": R2.init(C); R2.start_round(C, 0, start); R2.SOUNDS.append("bell")
    elif n in ("a1", "a2", "a3"): R2.start_round(C, flow.ROUND_OF[n], start); R2.SOUNDS.append("bell")
    audit("system", "stage", f"{prev} -> {n}")

def market_tick(name, el, start, rel):
    tick, itick, ia, total = mcfg(name); upd = int(D.get(C, "upd")); ch = False
    for n in C.execute("SELECT id,kind FROM news WHERE released=0 AND release_t IS NOT NULL AND release_t<=?", (rel,)).fetchall():
        C.execute("UPDATE news SET released=1,released_upd=? WHERE id=?", (upd, n["id"])); ch = True
        if n["kind"] in ("shock", "mega"): R2.SOUNDS.append("alert")
        # IMMEDIATE PRICE SHOCK UPON AUTOMATIC/SCHEDULED NEWS RELEASE
        M.apply_news_shock(C, n["id"])
    if name == "r1" and rel >= ia and D.get(C, "final5_on") != "1": D.put(C, "final5_on", "1"); R2.SOUNDS.append("warn"); ch = True
    due = schedule.due_updates(rel, tick, itick, ia, total)
    while upd < due:
        upd += 1; D.put(C, "upd", upd); M.step(C, upd, factor=math.sqrt(itick / tick) if name == "r1" and schedule.is_intraday_update(upd, tick, ia) else 1.0); ch = True
        for i, r in enumerate(S.leaderboard(C), 1): C.execute("UPDATE teams SET prev_rank=? WHERE id=?", (i, r["id"]))
        C.execute("INSERT INTO leaderboard_snapshots(upd,data) VALUES(?,?)", (upd, json.dumps(S.leaderboard(C))))
    return ch

def finish():
    prev = D.get(C, "stage_cur"); el = min(clock(), flow.total(C))
    if prev in flow.R2_STAGES: R2.close_round(C, flow.ROUND_OF[prev], el)
    if prev in R1_STAGES and prev == "r1": freeze_r1()
    D.put(C, "elapsed", el); D.put(C, "status", "ended"); D.put(C, "stage_cur", "ended")
    if C.execute("SELECT 1 FROM r2_accounts").fetchone(): D.put(C, "r2_final", json.dumps(R2.leaderboard(C)))
    audit("system", "event_end"); R2.SOUNDS.append("bell")

def tick_once():
    if D.get(C, "status") != "running": return False
    el = clock(); name, start, end = flow.stage_at(C, el); cur = D.get(C, "stage_cur"); ch = False; seq = flow.ORDER + ["ended"]
    if name != cur:
        for n in seq[(seq.index(cur) + 1 if cur in seq else 0):seq.index(name) + 1]:
            if n == "ended": finish(); return True
            enter_stage(n, D.get(C, "stage_cur"), flow.bounds(C, n)[0]); D.put(C, "stage_cur", n)
        ch = True
    if name in R1_STAGES: ch |= market_tick(name, el, start, el - start)
    elif name in flow.R2_STAGES:
        ch |= R2.tick(C, el, name, start); rnd = flow.ROUND_OF[name]
        if flow.phase(C, name, el - start) == "auction" and R2.round_done(C, rnd):
            D.put(C, "elapsed", end); D.put(C, "run_since", time.time()); audit("system", "auction_early_end", f"{name}: all teams completed session")
            R2.feed(C, "All teams have completed and no swap is pending – the auction round ends early", rnd); tick_once(); ch = True
    return ch

async def loop():
    while True:
        await asyncio.sleep(0.5)
        try:
            if tick_once() or R2.SOUNDS: await push()
        except Exception as e: print("loop error", repr(e))

@app.on_event("startup")
async def _s(): asyncio.create_task(loop())

# ---------- auth ----------
@app.post("/api/organizer/login")
async def org_login(b: dict):
    u = C.execute("SELECT * FROM users WHERE username=?", (b.get("username", ""),)).fetchone()
    if not u or not auth.check_pw(b.get("password", ""), u["pw_hash"], u["salt"]): raise HTTPException(401, "Invalid username or password")
    audit(u["username"], "login"); return {"token": auth.new_session(C, "organizer", u["username"])}

@app.post("/api/organizer/password")
async def org_pw(b: dict, req: Request):
    s = need(req, "organizer")
    if len(b.get("new", "")) < 6: raise HTTPException(400, "Password must be at least 6 characters")
    u = C.execute("SELECT * FROM users WHERE username=?", (s["ref"],)).fetchone()
    if not auth.check_pw(b.get("old", ""), u["pw_hash"], u["salt"]): raise HTTPException(401, "Current password wrong")
    h, sa = auth.hash_pw(b["new"]); C.execute("UPDATE users SET pw_hash=?,salt=? WHERE id=?", (h, sa, u["id"])); audit(s["ref"], "password_change"); return {"ok": True}

@app.post("/api/team/register")
async def register(b: dict):
    g = lambda *ks: next((str(b[k]).strip() for k in ks if b.get(k) not in (None, "")), "")
    name = g("name", "team_name", "teamName"); leader = g("leader", "leader_name", "team_leader", "teamLeader", "leaderName")
    if not name or not leader: raise HTTPException(400, "Team name and team leader name are required")
    try: members = max(1, int(float(b.get("members") or 1)))
    except Exception: members = 1
    rc = D.get(C, "reg_code", "")
    if rc and b.get("code") != rc: raise HTTPException(403, "Invalid team registration code")
    if C.execute("SELECT 1 FROM teams WHERE name=?", (name,)).fetchone(): raise HTTPException(409, "Team name already registered")
    n = (C.execute("SELECT MAX(CAST(SUBSTR(id,2) AS INTEGER)) FROM teams").fetchone()[0] or 0) + 1; tid = f"T{n:03d}"
    while C.execute("SELECT 1 FROM teams WHERE id=?", (tid,)).fetchone(): n += 1; tid = f"T{n:03d}"
    rec = secrets.token_hex(3).upper()
    C.execute("INSERT INTO teams(id,name,leader,college,members,recovery,cash) VALUES(?,?,?,?,?,?,?)", (tid, name, leader, str(b.get("college") or ""), members, rec, float(D.get(C, "capital"))))
    return {"token": auth.new_session(C, "team", tid), "team_id": tid, "recovery_code": rec}

@app.post("/api/team/recover")
async def recover(b: dict):
    t = C.execute("SELECT * FROM teams WHERE id=? AND recovery=?", ((b.get("team_id") or "").upper(), (b.get("code") or "").upper())).fetchone()
    if not t or t["status"] == "deactivated": raise HTTPException(401, "Invalid Team ID or recovery code")
    return {"token": auth.new_session(C, "team", t["id"]), "team_id": t["id"]}

@app.post("/api/spectator/login")
async def spec(b: dict):
    if (b.get("code") or "").strip() != D.get(C, "spectator_code"): raise HTTPException(401, "Invalid spectator code")
    return {"token": auth.new_session(C, "spectator")}

@app.get("/api/me")
async def me(req: Request): return need(req, "organizer", "team", "spectator")

# ---------- shared data ----------
@app.get("/api/state")
async def st(req: Request): need(req, "organizer", "team", "spectator"); return {**state(), "stocks": stocks()}

@app.get("/api/leaderboard")
async def lb(req: Request):
    s = need(req, "organizer", "team", "spectator"); rows = S.leaderboard(C)
    return [{k: r[k] for k in ("rank", "team", "value", "ret", "total", "status", "move")} for r in rows] if s["role"] != "organizer" else rows

@app.get("/api/news")
async def news(req: Request):
    s = need(req, "organizer", "team", "spectator")
    q = "SELECT * FROM news" + ("" if s["role"] == "organizer" else " WHERE released=1") + " ORDER BY released DESC,released_upd DESC,id"
    out = []
    for n in C.execute(q):
        d = dict(n)
        if s["role"] != "organizer": [d.pop(k, None) for k in ("direction", "impact", "release_upd", "severity", "sens", "release_t")]
        out.append(d)
    return out

@app.get("/api/chart/{symbol}")
async def chart(symbol: str, req: Request, since: int = None):
    need(req, "organizer", "team", "spectator")
    co = C.execute("SELECT * FROM companies WHERE symbol=?", (symbol,)).fetchone()
    if not co: raise HTTPException(404, "Unknown stock")
    rows = [dict(r) for r in C.execute("SELECT upd,o,h,l,c,v FROM price_history WHERE symbol=? ORDER BY upd", (symbol,))]
    vol = {r[0]: r[1] for r in C.execute("SELECT upd,SUM(qty) FROM orders WHERE symbol=? GROUP BY upd", (symbol,))}
    for r in rows: r["v"] = r["v"] or vol.get(r["upd"], 0)
    closes = [r["c"] for r in rows]; sma5 = [M.sma(closes[:i + 1], 5) for i in range(len(closes))]; sma20 = [M.sma(closes[:i + 1], 20) for i in range(len(closes))]
    last = rows[-1]["upd"] if rows else 0; full = since is None or since > last or since < 0; i0 = 0 if full else next((i for i, r in enumerate(rows) if r["upd"] >= since), len(rows))
    f = co["fund"]; rev = round(co["start_price"] * co["issued"] / 1e4, 1)
    fund = dict(Revenue=f"₹{rev} Cr (simulated)", Revenue_growth=f"{round((f-50)/4,1)}%", EBITDA_margin=f"{round(f/4,1)}%", ROE=f"{round(f/5,1)}%", ROCE=f"{round(f/6,1)}%", Debt_Equity=round((100-f)/60, 2),
        PE=round(co["price"] / max(1, f / 10), 1), PB=round(co["price"] / max(1, f * 4), 2), Dividend_yield=f"{round(f/50,2)}%", Beta=co["beta"], Fundamental_score=f)
    return dict(symbol=symbol, epoch=int(float(D.get(C, "chart_epoch") or 0)), full=full, last=last, candles=rows[i0:], sma5=sma5[i0:], sma20=sma20[i0:], analysis=M.analysis(closes), fundamentals=fund,
        note="Technical indicators are simulation-based analytical tools and do not guarantee future price movements.")

# ---------- team ----------
@app.get("/api/team/portfolio")
async def tp(req: Request):
    s = need(req, "team"); p = S.portfolio(C, s["ref"]); t = p["team"]
    hs = [dict(symbol=h["symbol"], company=h["name"], qty=h["qty"], avg=round(h["avg"], 2), price=h["price"], invested=round(h["avg"] * h["qty"], 2), market=round(h["price"] * h["qty"], 2), pnl=round((h["price"] - h["avg"]) * h["qty"], 2)) for h in p["holdings"]]
    orders = [dict(r) for r in C.execute("SELECT symbol,side,qty,price,brokerage,mode,upd FROM orders WHERE team_id=? ORDER BY id DESC LIMIT 50", (s["ref"],))]
    return dict(margin=T.margin(C, s["ref"]), mode=T.mode(C), team_id=t["id"], name=t["name"], status=t["status"], cash=round(t["cash"], 2), invested=round(p["invested"], 2), value=round(p["value"], 2), pnl=round(p["pnl"], 2), ret=round(p["ret"], 2),
        brokerage=round(t["brokerage"], 2), penalties=t["penalties"], holdings=hs, orders=orders, points=points(s["ref"]))

def points(tid):
    r1 = float(R2.r1map(C).get(tid, 0)) if D.get(C, "r1_results") else S.score(C, tid)["total"]
    r2 = 0.0
    if C.execute("SELECT 1 FROM r2_accounts WHERE team_id=?", (tid,)).fetchone(): r2 = R2.scores(C, tid)["r2"]
    return dict(r1=round(r1, 2), r2=round(r2, 2), overall=round(r1 + r2, 2))

@app.post("/api/team/quote")
async def quote(b: dict, req: Request):
    s = need(req, "team"); clock()
    try: return T.quote(C, b["symbol"], b.get("side", "BUY"), int(b["qty"]), s["ref"])
    except Exception as e: raise HTTPException(400, str(e))

@app.post("/api/team/order")
async def order(b: dict, req: Request):
    s = need(req, "team"); clock()
    try: q = T.execute(C, s["ref"], b.get("symbol"), b.get("side"), b.get("qty"), b.get("client_id") or secrets.token_hex(8))
    except T.TradeError as e: raise HTTPException(400, str(e))
    await push(); return q

# ---------- organizer ----------
@app.get("/api/organizer/teams")
async def teams(req: Request):
    need(req, "organizer"); return [dict(r) for r in C.execute("SELECT id,name,leader,college,members,recovery,status,cash,trades FROM teams")]

@app.post("/api/organizer/team/{tid}")
async def team_edit(tid: str, b: dict, req: Request):
    s = need(req, "organizer")
    if "status" in b and b["status"] in ("approved", "deactivated", "pending", "rejected"): C.execute("UPDATE teams SET status=? WHERE id=?", (b["status"], tid))
    if b.get("name"): C.execute("UPDATE teams SET name=? WHERE id=?", (b["name"], tid))
    if b.get("new_recovery"): C.execute("UPDATE teams SET recovery=? WHERE id=?", (secrets.token_hex(3).upper(), tid))
    audit(s["ref"], "team_edit", f"{tid} {b}"); await push(); return {"ok": True}

@app.post("/api/organizer/team/{tid}/delete")
async def team_delete(tid: str, b: dict, req: Request):
    s = need(req, "organizer")
    t = C.execute("SELECT * FROM teams WHERE id=?", (tid,)).fetchone()
    if not t: raise HTTPException(404, "Team not found")
    if b.get("confirm_id") != tid: raise HTTPException(400, "Confirmation does not match this team")
    C.execute("BEGIN IMMEDIATE")
    try:
        for h in C.execute("SELECT symbol,qty FROM holdings WHERE team_id=?", (tid,)).fetchall():
            C.execute("UPDATE companies SET inventory=inventory+? WHERE symbol=?", (h["qty"], h["symbol"]))
        n_orders = C.execute("SELECT COUNT(*) FROM orders WHERE team_id=?", (tid,)).fetchone()[0]
        C.execute("DELETE FROM holdings WHERE team_id=?", (tid,)); C.execute("DELETE FROM orders WHERE team_id=?", (tid,))
        C.execute("DELETE FROM sessions WHERE role='team' AND ref=?", (tid,)); C.execute("DELETE FROM teams WHERE id=?", (tid,)); C.execute("COMMIT")
    except Exception:
        C.execute("ROLLBACK"); raise
    audit(s["ref"], "team_delete", f"{tid} '{t['name']}'"); R2.remove_team(C, tid); await push(); return {"ok": True, "deleted": tid}

@app.get("/api/organizer/audit")
async def audit_log(req: Request):
    need(req, "organizer"); return [dict(r) for r in C.execute("SELECT ts,actor,action,detail FROM audit ORDER BY id DESC LIMIT 40")]

@app.get("/api/organizer/stats")
async def stats(req: Request):
    need(req, "organizer"); st_ = stocks()
    ch = lambda x: (x["price"] / x["prev_price"] - 1) * 100
    return dict(teams=C.execute("SELECT COUNT(*) FROM teams").fetchone()[0], active=C.execute("SELECT COUNT(*) FROM teams WHERE status='approved'").fetchone()[0],
        advancing=sum(1 for x in st_ if x["price"] > x["prev_price"]), declining=sum(1 for x in st_ if x["price"] < x["prev_price"]),
        gainer=max(st_, key=ch)["symbol"], loser=min(st_, key=ch)["symbol"], trades=C.execute("SELECT COUNT(*) FROM orders").fetchone()[0], volume=sum(x["volume"] for x in st_))

@app.get("/api/organizer/export")
async def export(req: Request):
    need(req, "organizer"); rows = S.leaderboard(C)
    csv = "Rank,Team,Portfolio Value,Return %,Total,Returns,Cash,Discipline,Risk,Diversification\n" + "\n".join(f'{r["rank"]},"{r["team"]}",{r["value"]},{r["ret"]},{r["total"]},{",".join(str(v) for v in r["parts"].values())}' for r in rows) + "\n\n© FINestra @Doms, AU"
    return Response(csv, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=finestra_results.csv"})

# ---------- organizer: settings & event control ----------
LOCKED = ("borrow_limit", "borrow_fee_pct", "borrow_pen", "capital", "tick_sec", "final_tick", "final5_sec", "test_sec", "r1_sec", "trans_sec", "pre_sec", "brk_sec", "news_sec", "disc_sec", "auc_sec", "r2_cash", "r2_teams", "lots_per_co", "lot_bp")
RANGES = dict(brk_normal=(0, 5), time_scale=(0.1, 5000), capital=(1000, 1e10), tick_sec=(5, 600), final_tick=(5, 600), final5_sec=(30, 900), test_sec=(30, 3600), r1_sec=(120, 7200), trans_sec=(5, 600),
    pre_sec=(30, 3600), brk_sec=(5, 600), news_sec=(30, 600), disc_sec=(30, 900), auc_sec=(60, 3600), window_sec=(10, 300), open_sec=(10, 300), r2_cash=(100000, 1e10), r2_teams=(2, 40), lots_per_co=(0, 10), borrow_limit=(0, 1e9), borrow_fee_pct=(0, 50), borrow_pen=(10000, 1e9), swap_ttl=(15, 3600), lot_bp=(500, 10000))

@app.post("/api/organizer/settings")
async def settings(b: dict, req: Request):
    s = need(req, "organizer"); applied = {}; locked = D.get(C, "status") not in ("idle", "ended")
    for k in ("spectator_code", "reg_code", "auto_news") + tuple(RANGES):
        if k not in b: continue
        if k in RANGES:
            try: v = float(b[k])
            except Exception: raise HTTPException(400, f"{k} must be a number")
            if not RANGES[k][0] <= v <= RANGES[k][1]: raise HTTPException(400, f"{k} must be between {RANGES[k][0]} and {RANGES[k][1]}")
        if k == "lot_bp" and float(b[k]) % 500: raise HTTPException(400, "lot_bp must be a multiple of 500")
        if locked and k in LOCKED: continue
        applied[k] = b[k]
    if "time_scale" in applied and D.get(C, "status") == "running": D.put(C, "elapsed", clock()); D.put(C, "run_since", time.time())
    for k, v in applied.items(): D.put(C, k, v)
    audit(s["ref"], "settings", json.dumps(applied)); return {"ok": True, "applied": applied}

@app.get("/api/organizer/settings")
async def get_settings(req: Request):
    need(req, "organizer"); return {k: D.get(C, k) for k in ("spectator_code", "reg_code", "auto_news") + tuple(RANGES)}

@app.post("/api/organizer/event/{action}")
async def event(action: str, b: dict, req: Request):
    s = need(req, "organizer"); stt = D.get(C, "status")
    if action == "start" and stt == "idle": D.put(C, "elapsed", 0); D.put(C, "run_since", time.time()); D.put(C, "stage_cur", "idle"); D.put(C, "status", "running")
    elif action == "pause" and stt == "running": D.put(C, "elapsed", clock()); D.put(C, "status", "paused")
    elif action == "resume" and stt == "paused": D.put(C, "run_since", time.time()); D.put(C, "status", "running")
    elif action == "end" and stt in ("running", "paused"): clock(); finish()
    elif action == "jump" and stt in ("running", "paused"):
        el = clock(); name, st0, en0 = flow.stage_at(C, el); tg = b.get("target", "next")
        if tg != "next" and tg not in flow.ORDER: raise HTTPException(400, "Unknown stage")
        t = en0 if tg == "next" else flow.bounds(C, tg)[0]
        if D.get(C, "hold_at") not in (None, "") and name == "trans1" and t >= en0 - 1e-9: D.put(C, "hold_at", ""); D.put(C, "elapsed", st0); el = st0
        if t <= el: raise HTTPException(400, "You can only skip forward")
        if t >= flow.total(C): clock(); finish()
        else: D.put(C, "elapsed", t); D.put(C, "run_since", time.time())
        tick_once()
    elif action == "start_r2" and stt in ("running", "paused") and cur_stage() == "trans1":
        D.put(C, "hold_at", ""); D.put(C, "elapsed", flow.bounds(C, "r2pre")[0]); D.put(C, "run_since", time.time()); D.put(C, "status", "running")
        tick_once()
    elif action == "restart":
        if b.get("confirm") != "RESTART": raise HTTPException(400, "Type RESTART to confirm")
        bk = os.path.join(BASE, "backups"); os.makedirs(bk, exist_ok=True); path = os.path.join(bk, f"finestra_{int(time.time()*1000)}_{secrets.token_hex(2)}.db")
        C.execute("VACUUM INTO ?", (path,)); audit(s["ref"], "restart", f"backup {path}"); market_reset()
        with D.tx(C):
            for t in ("r2_accounts", "r2_stakes", "r2_auctions", "r2_bids", "r2_windows", "r2_swaps", "r2_feed", "r2_values", "r2_results", "r2_news", "r2_loans", "r2_finish"): C.execute(f"DELETE FROM {t}")
            C.execute("UPDATE r2_companies SET value=start_value")
            for k, v in dict(status="idle", elapsed="0", run_since="0", upd="0", elapsed_now="0", stage_cur="idle", r1_results="", r2_round="0", r2_final="", final5_on="0", hold_at="").items(): D.put(C, k, v)
        R2.gen_news(C)
    elif action == "release":
        # IMMEDIATE PRICE SHOCK UPON MANUAL EVENT RELEASE
        nid = b.get("id")
        C.execute("UPDATE news SET released=1,released_upd=? WHERE id=? AND released=0", (int(D.get(C, "upd")), nid))
        M.apply_news_shock(C, nid)
        R2.SOUNDS.append("alert")
    else: raise HTTPException(400, f"Cannot {action} while {stt}")
    audit(s["ref"], f"event_{action}", json.dumps(b)); await push("restart" if action == "restart" else "update"); return state()

# ---------- Round 2 ----------
def r2_ctx(need_auction=True):
    st = cur_stage(); el = clock()
    if D.get(C, "status") != "running" or st not in flow.R2_STAGES: raise HTTPException(400, "Round 2 is not live")
    s0, _ = flow.bounds(C, st); ph = flow.phase(C, st, el - s0)
    if need_auction and ph != "auction": raise HTTPException(400, "Actions disabled during newsletter and discussion phases")
    return el, flow.ROUND_OF[st], ph

def r2call(fn, *a):
    try: return fn(*a)
    except R2.R2Error as e: raise HTTPException(400, str(e))
    except (ValueError, TypeError, KeyError): raise HTTPException(400, "Invalid request")

@app.get("/api/r2/state")
async def r2_state(req: Request):
    s = need(req, "organizer", "team", "spectator"); return R2.state_for(C, s["role"], s["ref"], clock())

@app.post("/api/r2/sell")
async def r2_sell(b: dict, req: Request):
    s = need(req, "team"); el, rnd, ph = r2_ctx(); r2call(R2.sell, C, s["ref"], b.get("symbol"), b.get("pct"), b.get("ask"), el); await push(); return {"ok": True}

@app.post("/api/r2/pass")
async def r2_pass(req: Request):
    s = need(req, "team"); el, rnd, ph = r2_ctx(); r2call(R2.pass_window, C, s["ref"], el); tick_once(); await push(); return {"ok": True}

@app.post("/api/r2/bid")
async def r2_bid(b: dict, req: Request):
    s = need(req, "team"); el, rnd, ph = r2_ctx(); r2call(R2.place_bid, C, s["ref"], b.get("auction_id"), b.get("amount"), el); await push(); return {"ok": True}

def r2_live_round():
    st = cur_stage()
    if D.get(C, "status") != "running" or st not in ("a1", "a2", "a3"): raise HTTPException(400, "Available only while an auction round is running")
    return clock(), flow.ROUND_OF[st]

@app.post("/api/r2/swap/propose")
async def r2_swap(b: dict, req: Request):
    s = need(req, "team"); el, rnd = r2_live_round()
    sid = r2call(R2.swap_propose, C, s["ref"], b.get("receiver"), b.get("give_symbol"), b.get("give_pct"), b.get("get_symbol"), b.get("get_pct"), b.get("cash"), el, rnd); await push(); return {"ok": True, "id": sid}

@app.post("/api/r2/swap/{sid}/{decision}")
async def r2_swap_resp(sid: int, decision: str, req: Request):
    s = need(req, "team"); el, rnd = r2_live_round()
    if decision == "cancel": r2call(R2.swap_cancel, C, s["ref"], sid, el); await push(); return {"ok": True, "status": "cancelled"}
    if decision not in ("accept", "reject"): raise HTTPException(400, "Invalid decision")
    res = r2call(R2.swap_respond, C, s["ref"], sid, decision == "accept", el, rnd); await push()
    if not res["ok"]: raise HTTPException(409, "Swap not completed – " + res["message"])
    return res

@app.post("/api/r2/finish")
async def r2_finish(req: Request):
    s = need(req, "team"); el, rnd = r2_live_round(); r2call(R2.finish_round, C, s["ref"], rnd, el); tick_once(); await push(); return {"ok": True}

@app.post("/api/r2/borrow")
async def r2_borrow(b: dict, req: Request):
    s = need(req, "team"); el, rnd = r2_live_round(); res = r2call(R2.borrow, C, s["ref"], b.get("amount"), rnd, el); await push(); return res

@app.post("/api/r2/repay")
async def r2_repay(b: dict, req: Request):
    s = need(req, "team"); el, rnd = r2_live_round(); res = r2call(R2.repay, C, s["ref"], b.get("amount"), rnd, el); await push(); return res

@app.post("/api/r2/org/config")
async def r2_config(b: dict, req: Request):
    s = need(req, "organizer")
    if cur_stage() in flow.R2_STAGES + flow.BREAKS + ("ended",): raise HTTPException(400, "Industries can only be configured before Round 2 starts")
    with D.tx(C):
        for x in b.get("companies", []):
            v = int(float(x["value"]) * 1e5) if float(x["value"]) < 1e5 else int(x["value"])
            if v < 1_000_000 or v > 1_000_000_000 or not str(x.get("name", "")).strip() or not str(x.get("industry", "")).strip(): raise HTTPException(400, "Each company needs a valid name, industry and valuation")
            C.execute("UPDATE r2_companies SET name=?,industry=?,value=?,start_value=? WHERE symbol=?", (x["name"].strip(), x["industry"].strip(), v, v, x["symbol"]))
    R2.gen_news(C); audit(s["ref"], "r2_config", json.dumps(b)); await push(); return {"ok": True}

@app.post("/api/r2/org/news/generate")
async def r2_gen(b: dict, req: Request):
    s = need(req, "organizer"); started = int(D.get(C, "r2_round", 0)) if cur_stage() in flow.R2_STAGES + flow.BREAKS + ("ended",) else -1
    rounds = [r for r in (b.get("rounds") or [1, 2, 3]) if r in (1, 2, 3) and r > started]
    if not rounds: raise HTTPException(400, "Those rounds have already started")
    R2.gen_news(C, rounds, secrets.randbelow(10**6)); audit(s["ref"], "r2_news_generate", json.dumps(rounds)); await push(); return {"ok": True, "rounds": rounds}

@app.post("/api/r2/org/news/toggle")
async def r2_toggle(b: dict, req: Request):
    s = need(req, "organizer"); D.put(C, "newsletter_on", "1" if b.get("on") else "0"); audit(s["ref"], "r2_newsletter", str(b.get("on"))); await push(); return {"on": D.get(C, "newsletter_on") == "1"}

@app.post("/api/r2/org/news/release")
async def r2_release(req: Request):
    s = need(req, "organizer"); st = cur_stage()
    if st not in ("a1", "a2", "a3"): raise HTTPException(400, "Only during an auction round")
    rnd = flow.ROUND_OF[st]; rows = C.execute("SELECT * FROM r2_news WHERE rnd=? AND released=0 ORDER BY ord", (rnd,)).fetchall()
    for r in rows: R2.release_news(C, r, clock())
    audit(s["ref"], "r2_news_release", str(rnd)); await push(); return {"released": len(rows)}

@app.post("/api/r2/org/auction/{action}")
async def r2_org_auction(action: str, req: Request):
    s = need(req, "organizer"); a = R2.active_auction(C)
    if not a: raise HTTPException(400, "No live auction")
    if action == "cancel": R2.cancel(C, a, clock())
    elif action == "force": r2call(R2.force_complete, C, clock())
    else: raise HTTPException(400, "Unknown action")
    audit(s["ref"], f"r2_auction_{action}", str(a["id"])); await push(); return {"ok": True}

@app.get("/api/r2/export")
async def r2_export(req: Request):
    need(req, "organizer"); lb = R2.leaderboard(C)
    out = "Rank,Team,Portfolio Value (INR),Growth %,Capital Growth /50,Participation /20,Swap & Sell /20,Diversification /10,Borrowed (INR),Borrowing penalty,Round 1 Points,Round 2 Points,Overall Points\n"
    out += "\n".join(f'{r["rank"]},"{r["team"]}",{r["value"]},{r["growth_pct"]},{",".join(str(v) for v in r["parts"].values())},{r["borrowed"]},{r["borrow_penalty"]},{r["r1"]},{r["r2"]},{r["overall"]}' for r in lb)
    return Response(out + "\n© FINestra @Doms, AU", media_type="text/csv", headers={"Content-Disposition": "attachment; filename=finestra_round2_results.csv"})

@app.get("/api/results")
async def results(req: Request):
    need(req, "organizer", "team", "spectator")
    j = lambda k: json.loads(D.get(C, k) or "[]")
    org_ = need(req, "organizer", "team", "spectator")["role"] == "organizer"
    slim = lambda rows: [{k: r[k] for k in r if k not in ("id",)} if org_ else {k: r[k] for k in ("rank", "team", "value", "ret", "total", "status", "move", "growth_pct", "r1", "r2", "overall") if k in r} for r in rows]
    return dict(r1=slim(j("r1_results")), r2=slim(j("r2_final")) if D.get(C, "r2_final") else slim(R2.leaderboard(C)) if C.execute("SELECT 1 FROM r2_accounts").fetchone() else [])

@app.websocket("/ws")
async def ws(w: WebSocket):
    await w.accept(); clients.add(w)
    try:
        while True: await w.receive_text()
    except WebSocketDisconnect: clients.discard(w)

app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")

@app.get("/")
@app.get("/spectator")
async def index(): return FileResponse(os.path.join(BASE, "static", "index.html"))

if __name__ == "__main__":
    import uvicorn
    try: ip = socket.gethostbyname(socket.gethostname())
    except Exception: ip = "YOUR-IP"
    print(f"\nFINestra @Doms, AU\n Organizer: http://localhost:8000\n Teams: http://{ip}:8000\n Spectator: http://{ip}:8000/spectator\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
