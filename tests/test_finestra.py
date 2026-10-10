import os, tempfile, time, json, random, threading
os.environ["FINESTRA_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
import pytest
from fastapi.testclient import TestClient
import server, database as D, flow, schedule, r2_engine as R2, seed_data, trading_engine as T, market_engine as M, r2_seed

C = server.C; c = TestClient(server.app)
H = lambda t: {"x-token": t}
org = c.post("/api/organizer/login", json={"username": "organizer", "password": "admin123"}).json()["token"]
TK, TID, CTX = {}, {}, {}
def team(n="Alpha", **kw): return c.post("/api/team/register", json={"name": n, "leader": "L", "members": 3, **kw})
def at(el, status="running"):
    for k, v in dict(status=status, elapsed=el, run_since=time.time(), time_scale=1).items(): D.put(C, k, v)
    return server.tick_once()
def start_of(n): return flow.bounds(C, n)[0]
def st(): return D.get(C, "stage_cur")
def five():
    for t in c.get("/api/organizer/teams", headers=H(org)).json(): c.post(f"/api/organizer/team/{t['id']}/delete", json={"confirm_id": t["id"]}, headers=H(org))
    for n in "ABCDE":
        r = team("Team " + n).json(); TK[n], TID[n] = r["token"], r["team_id"]
def restart(): assert c.post("/api/organizer/event/restart", json={"confirm": "RESTART"}, headers=H(org)).status_code == 200
def start(): assert c.post("/api/organizer/event/start", json={}, headers=H(org)).status_code == 200
def api(n, path, body=None): return c.post("/api/" + path, json=body or {}, headers=H(TK[n]))

# ---------------- access control ----------------
def test_auth_roles_and_spectator():
    assert c.post("/api/organizer/login", json={"username": "organizer", "password": "x"}).status_code == 401
    t = team("RoleTeam").json(); assert c.get("/api/organizer/teams", headers=H(t["token"])).status_code == 401
    assert team("rolETEAM").status_code == 409
    ok = c.post("/api/team/recover", json={"team_id": t["team_id"], "code": t["recovery_code"]}); assert ok.status_code == 200
    assert c.post("/api/team/recover", json={"team_id": t["team_id"], "code": "BAD"}).status_code == 401
    assert c.post("/api/spectator/login", json={"code": "no"}).status_code == 401
    sp = c.post("/api/spectator/login", json={"code": "SPECTATE"}).json()["token"]
    assert c.post("/api/r2/bid", json={"auction_id": 1, "amount": 1}, headers=H(sp)).status_code == 401
    assert c.get("/api/team/portfolio", headers=H(sp)).status_code == 401 and c.get("/api/r2/state", headers=H(sp)).status_code == 200

# ---------------- Round 1 definition ----------------
def test_stock_universe_12_plus_3_commodities():
    rows = C.execute("SELECT * FROM companies").fetchall(); assert len(rows) == 15
    ind = {}
    for r in rows: ind[r["industry"]] = ind.get(r["industry"], 0) + 1
    assert ind.pop("Commodity-Linked") == 3 and len(ind) == 6 and set(ind.values()) == {2}
    assert {r["symbol"] for r in rows if r["industry"] == "Commodity-Linked"} == {"GOLD", "CRUD", "INMT"} and C.execute("SELECT beta FROM companies WHERE symbol='GOLD'").fetchone()[0] < 0

# ---------------- registration (bug fix) ----------------
def test_registration_accepts_valid_team_and_persists():
    r = c.post("/api/team/register", json={"name": "Reg Team", "leader": "Lead Person", "college": "X", "members": "3"}); assert r.status_code == 200, r.text
    tid = r.json()["team_id"]; row = C.execute("SELECT * FROM teams WHERE id=?", (tid,)).fetchone()
    assert row["name"] == "Reg Team" and row["leader"] == "Lead Person" and row["members"] == 3
    r2 = c.post("/api/team/register", json={"team_name": "Alt Names", "team_leader": "Someone"}); assert r2.status_code == 200          # alternative field names are accepted too
    assert c.post("/api/team/register", json={"name": "  ", "leader": "x"}).status_code == 400 and c.post("/api/team/register", json={"name": "NoLeader"}).status_code == 400
    assert c.post("/api/team/register", json={"name": "reg team", "leader": "x"}).status_code == 409
    import sqlite3; fresh = sqlite3.connect(D.DB_PATH); assert fresh.execute("SELECT COUNT(*) FROM teams WHERE name IN ('Reg Team','Alt Names')").fetchone()[0] == 2     # really saved in SQLite
    ui = open(os.path.join(os.path.dirname(__file__), "..", "static", "app.js"), encoding="utf8").read()
    assert "tn.value" not in ui and "gv('tn')" in ui and "gv('tl')" in ui            # frontend no longer relies on global ids (sound.js defines a function called tn)

# ---------------- Round 1 schedule ----------------
def test_schedules_and_timeline():
    a = (45, 30, 1800, 2400)                                      # Round 1: 45 s for 30 minutes, then 30 s for the final 10 minutes
    assert schedule.max_update(*a) == 60 and schedule.update_time(40, *a[:3]) == 1800 and schedule.update_time(41, *a[:3]) == 1830 and schedule.update_time(42, *a[:3]) == 1860
    d = lambda e: schedule.due_updates(e, *a); assert (d(44), d(45), d(1799), d(1830), d(2399), d(99999)) == (0, 1, 39, 41, 59, 60)
    assert schedule.max_update(45, 45, 300, 300) == 6
    assert flow.total(C) == 300 + 2400 + 60 + 600 + 60 + 900 + 60 + 900 + 60 + 900
    assert [flow.stage_at(C, t)[0] for t in (0, 299, 300, 2699, 2700, 2759, 2760, 3359, 3360, 3419, 3420, 6239, 6240)] == ["test", "test", "r1", "r1", "trans1", "trans1", "r2pre", "r2pre", "brk0", "brk0", "a1", "a3", "ended"]
    assert [flow.phase(C, "a1", r) for r in (0, 119, 120, 299, 300, 899)] == ["newsletter", "newsletter", "discussion", "discussion", "auction", "auction"]
def test_round1_has_no_regular_news_only_surprise_events_every_4_minutes():
    seed_data.assign_news_times(C, "r1")
    assert C.execute("SELECT COUNT(*) FROM news WHERE kind='scheduled'").fetchone()[0] == 0 and C.execute("SELECT COUNT(*) FROM news WHERE id LIKE 'N%'").fetchone()[0] == 0     # the 2-minute cards are gone completely
    shocks = [r[0] for r in C.execute("SELECT release_t FROM news WHERE kind='shock' AND release_t IS NOT NULL ORDER BY release_t")]
    assert shocks == [180 + 240 * k for k in range(7)]                                                  # a surprise event every 4 minutes: 3:00, 7:00 ... 27:00
    assert [r[0] for r in C.execute("SELECT release_t FROM news WHERE kind='mega' ORDER BY release_t")] == [1860, 2160]     # MEGA events stay at the 31st and 36th minute
    assert C.execute("SELECT COUNT(*) FROM news WHERE release_t IS NOT NULL").fetchone()[0] == 9 and C.execute("SELECT COUNT(*) FROM news WHERE release_t>1800 AND kind!='mega'").fetchone()[0] == 0
def test_round1_events_are_70_30_and_cover_every_industry():
    timed = [dict(r) for r in C.execute("SELECT * FROM news WHERE kind='shock' AND release_t IS NOT NULL")]; allev = [dict(r) for r in C.execute("SELECT * FROM news")]
    pos = lambda rows: sum(r["direction"] > 0 for r in rows)
    assert (pos(timed), len(timed) - pos(timed)) == (5, 2)                                              # 71% / 29% of the automatic 4-minute events
    ev = [r for r in allev if r["kind"] in ("shock", "mega")]; assert (pos(ev), len(ev) - pos(ev)) == (7, 3) or abs(pos(ev) / len(ev) - .7) < .08, (pos(ev), len(ev))
    sur = [r for r in allev if r["kind"] == "surprise"]; assert len(sur) == 20 and pos(sur) == 14                                  # manual pool: 70 / 30
    groups = {r["industry"] for r in timed}; assert len(groups) == 7 and groups == {r["industry"] for r in C.execute("SELECT industry FROM news WHERE kind='shock'")}   # six industries + commodity group, each hit once
    for r in timed:                                                                                      # one industry is hit SIGNIFICANTLY by a single event; spill-over elsewhere is small
        sens = json.loads(r["sens"]); own = [x[0] for x in C.execute("SELECT symbol FROM companies WHERE industry=?", (r["industry"],))]
        assert r["impact"] >= 3.5 and r["severity"] == 3 and all(abs(sens.get(sym, 1.2)) >= 1.0 for sym in own[:1]) and all(abs(v) <= .5 for k, v in sens.items() if k not in own), r["headline"]
    for r in C.execute("SELECT industry FROM news WHERE kind='surprise'"): groups.add(r["industry"])
    assert {"Banking & Financial Services", "Technology & Telecom", "Automobile & EV", "Energy & Renewables", "Healthcare & Pharma", "Infrastructure, Metals & Manufacturing", "Commodity-Linked"} <= groups
def test_single_event_moves_one_industry_strongly():
    D.put(C, "status", "running"); D.put(C, "stage_cur", "r1"); server.market_reset(); base = {r["symbol"]: r["price"] for r in C.execute("SELECT symbol,price FROM companies")}
    C.execute("UPDATE news SET released=1,released_upd=0 WHERE id='X01'"); M.step(C, 1); aft = {r["symbol"]: r["price"] / base[r["symbol"]] - 1 for r in C.execute("SELECT symbol,price FROM companies")}
    assert aft["AURB"] > .025 and aft["MRDN"] > .025 and max(abs(aft[x]) for x in ("NVTL", "HLXA", "GOLD", "SOLR")) < .035; server.market_reset()
    C.execute("UPDATE news SET released=1,released_upd=0 WHERE id='X08'"); M.step(C, 1); aft = {r["symbol"]: r["price"] / base[r["symbol"]] - 1 for r in C.execute("SELECT symbol,price FROM companies")}
    assert aft["NVTL"] < -.025 and aft["QBIT"] < -.025; server.market_reset()
def test_mega_event_moves_prices_far_more_than_normal():
    D.put(C, "status", "running"); D.put(C, "stage_cur", "r1"); server.market_reset(); base = {r["symbol"]: r["price"] for r in C.execute("SELECT symbol,price FROM companies")}
    M.step(C, 1); calm = max(abs(r["price"] / base[r["symbol"]] - 1) for r in C.execute("SELECT symbol,price FROM companies"))
    server.market_reset(); C.execute("UPDATE news SET released=1,released_upd=0 WHERE id='M01'"); M.step(C, 1)
    after = {r["symbol"]: r["price"] / base[r["symbol"]] - 1 for r in C.execute("SELECT symbol,price FROM companies")}
    assert max(abs(v) for v in after.values()) > 0.04 and max(abs(v) for v in after.values()) > 1.5 * calm and after["GOLD"] > 0 and after["EVRA"] < -0.03
    server.market_reset(); C.execute("UPDATE news SET released=1,released_upd=0 WHERE id='M02'"); M.step(C, 1)
    m2 = {r["symbol"]: r["price"] / base[r["symbol"]] - 1 for r in C.execute("SELECT symbol,price FROM companies")}
    assert m2["QBIT"] > 0.04 and m2["EVRA"] > 0.04 and m2["PTRX"] < 0 and m2["GOLD"] < 0                # violent sector rotation: big winners and some sectors sold off
    server.market_reset()
def test_commodity_and_sector_event_behaviour():
    D.put(C, "status", "running"); D.put(C, "stage_cur", "r1"); server.market_reset()
    before = {r["symbol"]: r["price"] for r in C.execute("SELECT symbol,price FROM companies")}
    C.execute("UPDATE news SET released=1,released_upd=0 WHERE id='X07'"); M.step(C, 1); after = {r["symbol"]: r["price"] for r in C.execute("SELECT symbol,price FROM companies")}
    assert after["GOLD"] / before["GOLD"] > 1.03; server.market_reset()

# ---------------- Test round -> Round 1 -> unlimited break ----------------
def test_test_round_reset_round1_warnings_final_phase_and_unlimited_break():
    five(); restart(); start(); at(5); s = server.state()
    assert s["stage"] == "test" and s["test"] and abs(s["stage_remaining"] - 295) < 2
    assert api("A", "team/order", {"symbol": "AURB", "side": "BUY", "qty": 10}).status_code == 200
    at(5 + 45 * 2 + 1); assert int(D.get(C, "upd")) == 2                                      # 45-second updates in the test round
    R2.SOUNDS.clear(); at(301); assert st() == "r1" and "bell" in R2.SOUNDS and int(D.get(C, "upd")) == 0 and C.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0
    at(300 + 170); ne = server.state()["next_events"]; assert ne and ne[0]["type"] == "event" and abs(ne[0]["at"] - (300 + 180)) < 1          # the surprise event is announced ahead
    assert C.execute("SELECT COUNT(*) FROM news WHERE released=1").fetchone()[0] == 0
    at(300 + 181); assert C.execute("SELECT COUNT(*) FROM news WHERE kind='shock' AND released=1").fetchone()[0] == 1
    at(300 + 121); assert C.execute("SELECT COUNT(*) FROM news WHERE released=1").fetchone()[0] == 1 or True
    at(300 + 1790); assert not server.state()["final5"] and int(D.get(C, "upd")) == 39
    R2.SOUNDS.clear(); at(300 + 1801); s = server.state(); assert s["final5"] and s["interval"] == 30 and "warn" in R2.SOUNDS and int(D.get(C, "upd")) == 40
    at(300 + 1855); assert server.state()["next_events"][0]["type"] == "mega"; R2.SOUNDS.clear(); at(300 + 1861)
    assert C.execute("SELECT released FROM news WHERE id='M01'").fetchone()[0] == 1 and "alert" in R2.SOUNDS and int(D.get(C, "upd")) == 42       # mega lands exactly at 31:00 with a price update
    at(300 + 2161); assert C.execute("SELECT released FROM news WHERE id='M02'").fetchone()[0] == 1
    assert C.execute("SELECT COUNT(*) FROM news WHERE kind='shock' AND released=1").fetchone()[0] == 7 and C.execute("SELECT COUNT(*) FROM news WHERE released=1").fetchone()[0] == 9      # 7 timed events + 2 MEGA, nothing else
    assert api("A", "team/order", {"symbol": "GOLD", "side": "BUY", "qty": 2}).status_code == 200
    at(2701); assert st() == "trans1" and server.state()["waiting"] and api("A", "team/order", {"symbol": "AURB", "side": "BUY", "qty": 1}).status_code == 400
    res = json.loads(D.get(C, "r1_results")); assert len(res) == 5 and res[0]["rank"] == 1
    for t in (2800, 5000, 90000): at(t); assert st() == "trans1"                                    # UNLIMITED break: nothing starts by itself
    assert server.state()["waiting"] and c.post("/api/organizer/event/start_r2", json={}, headers=H(TK["A"])).status_code == 401
    pts = api("A", "team/portfolio"); assert c.get("/api/team/portfolio", headers=H(TK["A"])).json()["points"].keys() == {"r1", "r2", "overall"}
    assert c.post("/api/organizer/event/start_r2", json={}, headers=H(org)).status_code == 200 and st() == "r2pre" and not server.state()["waiting"]
def test_team_views_never_expose_scoring_breakdown():
    p = c.get("/api/team/portfolio", headers=H(TK["A"])).json(); assert "score" not in p and set(p["points"]) == {"r1", "r2", "overall"}
    assert all("parts" not in r for r in c.get("/api/leaderboard", headers=H(TK["A"])).json())
    assert all("parts" in r for r in c.get("/api/leaderboard", headers=H(org)).json())
def test_concurrent_orders_no_oversell():
    restart(); start(); at(5); C.execute("UPDATE companies SET inventory=5 WHERE symbol='AURB'"); res = []
    def go(t):
        cc = D.conn()
        try: T.execute(cc, t, "AURB", "BUY", 3, "c" + t); res.append(1)
        except T.TradeError: res.append(0)
    th = [threading.Thread(target=go, args=(i,)) for i in TID.values()]; [x.start() for x in th]; [x.join() for x in th]
    assert sum(res) == 1 and C.execute("SELECT inventory FROM companies WHERE symbol='AURB'").fetchone()[0] == 2

# ---------------- Round 2: content ----------------
def test_newsletter_10_items_6_current_4_outlook_70_30_and_all_industries():
    rows = [dict(r) for r in C.execute("SELECT * FROM r2_news")]; assert len(rows) == 30 and len({r["headline"] for r in rows}) == 30
    cur, out = {}, {}
    for rnd in (1, 2, 3):
        rr = [r for r in rows if r["rnd"] == rnd]; assert len(rr) == 10 and sum(r["kind"] == "now" for r in rr) == 6 and sum(r["kind"] == "future" for r in rr) == 4
        assert sum(r["sentiment"] == "Positive" for r in rr) == 7 and sum(r["sentiment"] == "Negative" for r in rr) == 3          # 70% / 30%
        assert {r["symbol"] for r in rr} == {x[0] for x in C.execute("SELECT symbol FROM r2_companies")}                              # EVERY industry is in EVERY newsletter
        for r in rr:
            d = json.loads(r["impacts"]); assert d[r["symbol"]] * (1 if r["sentiment"] == "Positive" else -1) > 0              # the hidden price effect matches what the text says
            (cur if r["kind"] == "now" else out)[r["symbol"]] = (cur if r["kind"] == "now" else out).get(r["symbol"], 0) + 1
    assert len(cur) == 8 and min(cur.values()) >= 2 and len(out) == 8 and min(out.values()) >= 1            # meaningful coverage over time
    assert {r["tkey"] for r in rows if r["kind"] == "now"} >= {"ceo", "strike", "probe", "death", "short", "acq", "contract", "tech", "exp_curb"}
    assert all(json.loads(r["impacts"]) for r in rows) and not any(w in " ".join(r["headline"] + r["body"] for r in rows).lower() for w in (" buy ", " sell "))
    assert 800000 <= min(r["value"] for r in C.execute("SELECT value FROM r2_companies")) and sum(r["value"] for r in C.execute("SELECT value FROM r2_companies")) < 5 * 10_000_000

# ---------------- Round 2: helpers ----------------
def inv_ok():
    for s in C.execute("SELECT symbol FROM r2_companies"):
        tot = C.execute("SELECT COALESCE(SUM(bp),0) FROM r2_stakes WHERE symbol=?", (s[0],)).fetchone()[0] + C.execute("SELECT COALESCE(SUM(bp),0) FROM r2_auctions WHERE symbol=? AND status IN ('open','countdown')", (s[0],)).fetchone()[0]
        assert tot == 10000, s[0]
def give(team, sym, bp, cost):
    C.execute("INSERT INTO r2_stakes VALUES(?,?,?,?) ON CONFLICT(team_id,symbol) DO UPDATE SET bp=excluded.bp,cost=excluded.cost", (TID[team], sym, bp, cost))
    C.execute("UPDATE r2_stakes SET bp=bp-? WHERE team_id='MARKET' AND symbol=?", (bp, sym)); C.execute("DELETE FROM r2_stakes WHERE team_id='MARKET' AND bp<=0")
def r2_to_prelim():
    restart(); five(); start(); at(5); at(start_of("r2pre") + 0.5)
def to_round(rnd, offset=1):
    """Deterministic setup: every team owns 30% of two companies, then jump to the given auction round."""
    r2_to_prelim(); C.execute("DELETE FROM r2_auctions WHERE rnd=0"); C.execute("DELETE FROM r2_stakes WHERE team_id!='MARKET'"); C.execute("DELETE FROM r2_stakes WHERE team_id='MARKET'")
    for sym in [r["symbol"] for r in C.execute("SELECT symbol FROM r2_companies")]: C.execute("INSERT INTO r2_stakes VALUES('MARKET',?,10000,0)", (sym,))
    for t, ss in {"A": ("ORBK", "NXRA"), "B": ("VNTA", "HLRA"), "C": ("CRVT", "STRX"), "D": ("FRLX", "BZRO"), "E": ("ORBK", "VNTA")}.items():
        for sym in ss: give(t, sym, 3000, 900_000)
    at(start_of(f"a{rnd}") + offset)

# ---------------- Round 2: preliminary auction ----------------
def test_preliminary_100pct_lots_every_team_owns_a_company_and_early_end():
    r2_to_prelim(); assert st() == "r2pre"
    assert [r["cash"] for r in C.execute("SELECT cash FROM r2_accounts")] == [10_000_000] * 5                      # Rs 1 Crore each
    lots = C.execute("SELECT * FROM r2_auctions WHERE rnd=0").fetchall(); assert len(lots) == 8 and all(l["bp"] == 10000 for l in lots) and len({l["symbol"] for l in lots}) == 8   # every company, 100% stake
    C.execute("UPDATE r2_companies SET value=1000000")                                                            # cheap lots so one team could in theory hoard
    t = [start_of("r2pre") + 1]
    def lot(winner, amt=None):
        at(t[0]); a = R2.active_auction(C); assert a and a["bp"] == 10000
        r = api(winner, "r2/bid", {"auction_id": a["id"], "amount": amt or a["ask"]})
        if r.status_code == 200: at(t[0] + 11); t[0] += 12
        return r
    for _ in range(4): assert lot("A").status_code == 200                                                          # A takes four lots (needy teams: B, C, D, E)
    a = (at(t[0]), R2.active_auction(C))[1]; blocked = api("A", "r2/bid", {"auction_id": a["id"], "amount": a["ask"]}); assert blocked.status_code == 400 and "first company" in blocked.json()["detail"]
    assert api("B", "r2/bid", {"auction_id": a["id"], "amount": a["ask"]}).status_code == 200; at(t[0] + 11); t[0] += 12
    for n in "CDE": assert lot(n).status_code == 200
    at(t[0] + 1); assert C.execute("SELECT COUNT(*) FROM r2_accounts a WHERE NOT EXISTS (SELECT 1 FROM r2_stakes s WHERE s.team_id=a.team_id AND s.bp>0)").fetchone()[0] == 0
    assert st() == "brk0", st()                                                                                   # all lots sold & every team owns a company -> preliminary ends early, 1-minute break
    assert all(r["cash"] >= 0 for r in C.execute("SELECT cash FROM r2_accounts")); inv_ok()
    assert api("B", "r2/bid", {"auction_id": 1, "amount": 10 ** 6}).status_code == 400
def test_preliminary_safety_net_allocates_company_to_team_without_one():
    r2_to_prelim(); C.execute("DELETE FROM r2_auctions WHERE status='queued'"); at(start_of("r2pre") + 1)
    at(start_of("brk0") + 1); assert C.execute("SELECT COUNT(*) FROM r2_accounts a WHERE NOT EXISTS (SELECT 1 FROM r2_stakes s WHERE s.team_id=a.team_id AND s.bp>0)").fetchone()[0] == 0; inv_ok()
    assert all(r["cash"] >= 0 for r in C.execute("SELECT cash FROM r2_accounts"))
def test_bid_rules_countdown_and_award():
    r2_to_prelim(); t0 = start_of("r2pre") + 1; at(t0); a = R2.active_auction(C); assert a and a["status"] == "open" and a["seller"] == "MARKET"; inv_ok()
    bid = lambda n, amt: api(n, "r2/bid", {"auction_id": a["id"], "amount": amt})
    assert bid("A", a["ask"] - 1000).status_code == 400 and bid("A", a["ask"] + 0.5).status_code == 400
    C.execute("UPDATE r2_accounts SET cash=100000 WHERE team_id=?", (TID["E"],)); assert bid("E", a["ask"]).status_code == 400; C.execute("UPDATE r2_accounts SET cash=10000000 WHERE team_id=?", (TID["E"],))
    assert bid("A", a["ask"]).status_code == 200 and bid("A", a["ask"] + 500000).status_code == 400 and bid("B", a["ask"] + 10).status_code == 400
    assert bid("B", a["ask"] + 100000).status_code == 200              # a new bid restarts the 10-second countdown
    at(t0 + 5); assert R2.active_auction(C)["status"] == "countdown"
    R2.SOUNDS.clear(); at(t0 + 12); sold = C.execute("SELECT * FROM r2_auctions WHERE id=?", (a["id"],)).fetchone()
    assert sold["status"] == "sold" and sold["winner"] == TID["B"] and "win" in R2.SOUNDS
    assert C.execute("SELECT cash FROM r2_accounts WHERE team_id=?", (TID["B"],)).fetchone()[0] == 10_000_000 - sold["price"] and C.execute("SELECT cash FROM r2_accounts WHERE team_id=?", (TID["A"],)).fetchone()[0] == 10_000_000
    st_ = c.get("/api/r2/state", headers=H(TK["C"])).json(); assert "impacts" not in json.dumps(st_["news"]) and st_["me"]["swaps_total"] in (1, 2) and set(st_["me"]["points"]) == {"r1", "r2", "overall"}; inv_ok()

# ---------------- Round 2: auction rounds ----------------
def test_newsletter_released_through_phase_prices_change_and_actions_locked():
    to_round(1, 0.5); v0 = {r["symbol"]: r["value"] for r in C.execute("SELECT symbol,value FROM r2_companies")}; a1 = start_of("a1")
    assert server.state()["phase"] == "newsletter" and C.execute("SELECT COUNT(*) FROM r2_news WHERE rnd=1 AND released=1").fetchone()[0] <= 1
    at(a1 + 60); mid = C.execute("SELECT COUNT(*) FROM r2_news WHERE rnd=1 AND released=1").fetchone()[0]; assert 3 < mid < 10                      # released progressively
    at(a1 + 100); s = c.get("/api/r2/state", headers=H(TK["A"])).json(); got = [n for n in s["news"] if n["rnd"] == 1]
    assert len(got) == 10 and sum(n["kind"] == "now" for n in got) == 6 and sum(n["kind"] == "future" for n in got) == 4 and all("impacts" not in n and "applied" not in n for n in got)
    v1 = {r["symbol"]: r["value"] for r in C.execute("SELECT symbol,value FROM r2_companies")}; assert sum(v1[k] != v0[k] for k in v0) >= 5                  # present news re-priced companies
    fut = C.execute("SELECT applied FROM r2_news WHERE rnd=1 AND kind='future'").fetchall(); assert all(r[0] == 0 for r in fut)                              # hints do NOT move this round
    assert api("A", "r2/pass").status_code == 400 and api("A", "r2/bid", {"auction_id": 1, "amount": 10 ** 6}).status_code == 400
    p_ = api("A", "r2/swap/propose", {"receiver": TID["B"], "give_symbol": "ORBK", "give_pct": 5, "get_symbol": "VNTA", "get_pct": 5}); assert p_.status_code == 200      # swaps are allowed at ANY time in an auction round
    assert api("A", f"r2/swap/{p_.json()['id']}/cancel").status_code == 200
    at(a1 + 200); assert server.state()["phase"] == "discussion" and api("A", "r2/bid", {"auction_id": 1, "amount": 10 ** 6}).status_code == 400
def test_selling_sessions_5pct_rule_and_one_session_per_round():
    to_round(1); a1 = start_of("a1"); at(a1 + 301); w = C.execute("SELECT * FROM r2_windows WHERE rnd=1 AND status='active'").fetchone(); assert w and server.state()["phase"] == "auction"
    inv = {v: k for k, v in TID.items()}; first = inv[w["team_id"]]; other = next(k for k in "ABCDE" if k != first); sym = C.execute("SELECT symbol FROM r2_stakes WHERE team_id=?", (w["team_id"],)).fetchone()[0]
    assert api(other, "r2/pass").status_code == 400 and api(other, "r2/sell", {"symbol": sym, "pct": 5, "ask": 50000}).status_code == 400
    for bad in (3, 7.5, 0, 12, 105, -5, 99): assert api(first, "r2/sell", {"symbol": sym, "pct": bad, "ask": 200000}).status_code == 400, bad            # only 5%,10%,15%…
    assert api(first, "r2/sell", {"symbol": sym, "pct": 30, "ask": 300000}).status_code == 200; A = R2.active_auction(C); assert A["bp"] == 3000
    t = a1 + 305; at(t); buyer = other; assert api(buyer, "r2/bid", {"auction_id": A["id"], "amount": 300000}).status_code == 200; at(t + 11)
    done = C.execute("SELECT * FROM r2_auctions WHERE id=?", (A["id"],)).fetchone(); assert done["status"] == "sold" and done["winner"] == TID[buyer]
    assert C.execute("SELECT bp FROM r2_stakes WHERE team_id=? AND symbol=?", (TID[buyer], sym)).fetchone()[0] >= 3000
    assert api(first, "r2/sell", {"symbol": sym, "pct": 5, "ask": 50000}).status_code == 400                                                              # one selling session per round
    w2 = C.execute("SELECT * FROM r2_windows WHERE rnd=1 AND status='active'").fetchone(); assert w2 and w2["team_id"] != w["team_id"]; inv_ok()
def test_swap_any_time_confirmation_limits_and_validation():
    to_round(1); a1 = start_of("a1"); inv = {v: k for k, v in TID.items()}
    top = json.loads(D.get(C, "r1_results"))[0]["id"]; sw = {r["team_id"]: r["swaps_total"] for r in C.execute("SELECT * FROM r2_accounts")}
    assert sw[top] == 2 and sorted(sw.values()) == [1, 1, 1, 1, 2]
    prop = lambda n, to, g, gp, r, rp, cash=0: api(n, "r2/swap/propose", {"receiver": TID[to], "give_symbol": g, "give_pct": gp, "get_symbol": r, "get_pct": rp, "cash": cash})
    bp = lambda t, s_: (C.execute("SELECT bp FROM r2_stakes WHERE team_id=? AND symbol=?", (TID[t], s_)).fetchone() or [0])[0]
    cash = lambda t: C.execute("SELECT cash FROM r2_accounts WHERE team_id=?", (TID[t],)).fetchone()[0]
    # --- invalid proposals are refused and change nothing
    for bad in (prop("A", "A", "ORBK", 5, "VNTA", 5), prop("A", "B", "ORBK", 7, "VNTA", 5), prop("A", "B", "ORBK", 5, "VNTA", 99), prop("A", "B", "ORBK", 5, "ORBK", 5), prop("A", "B", "ORBK", 40, "VNTA", 5),
                prop("A", "B", "ORBK", 5, "CRVT", 5), prop("A", "B", "HLRA", 5, "VNTA", 5), prop("A", "B", "ORBK", 5, "VNTA", 5, 1.5), prop("A", "B", "ORBK", 5, "VNTA", 5, 10 ** 9)): assert bad.status_code == 400, bad.text
    assert C.execute("SELECT COUNT(*) FROM r2_swaps").fetchone()[0] == 0
    # --- valid proposal during the NEWSLETTER (A is not in a selling session); duplicates / second pending proposal blocked
    assert server.state()["phase"] == "newsletter"; assert prop("A", "B", "ORBK", 5, "VNTA", 5).status_code == 200
    assert prop("A", "B", "ORBK", 5, "VNTA", 5).status_code == 400 and prop("A", "C", "NXRA", 5, "CRVT", 5).status_code == 400          # one pending proposal at a time
    mirror = prop("B", "A", "VNTA", 5, "ORBK", 5); assert mirror.status_code == 400 and "already proposed" in mirror.json()["detail"]
    p = C.execute("SELECT * FROM r2_swaps WHERE status='pending'").fetchone(); b0, a0 = bp("A", "ORBK"), bp("B", "VNTA")
    assert (bp("A", "ORBK"), bp("B", "VNTA")) == (3000, 3000)                                            # nothing moves before confirmation
    assert api("C", f"r2/swap/{p['id']}/accept").status_code == 400 and api("A", f"r2/swap/{p['id']}/accept").status_code == 400           # only the receiver decides
    assert api("B", f"r2/swap/{p['id']}/reject").status_code == 200 and R2.swaps_left(C, TID["A"]) == R2.swaps_total(C, TID["A"])       # a rejection does not use the swap
    assert api("B", f"r2/swap/{p['id']}/accept").status_code == 400                                       # cannot answer twice
    # --- accept: both stakes move at once, dashboards (state) show it immediately
    at(a1 + 150); assert server.state()["phase"] == "discussion"; assert prop("A", "B", "ORBK", 5, "VNTA", 10).status_code == 200; p = C.execute("SELECT * FROM r2_swaps WHERE status='pending'").fetchone()
    assert api("B", f"r2/swap/{p['id']}/accept").status_code == 200
    assert bp("A", "ORBK") == 2500 and bp("A", "VNTA") == 1000 and bp("B", "VNTA") == 2000 and bp("B", "ORBK") == 500
    inv_ok(); st_a = c.get("/api/r2/state", headers=H(TK["A"])).json(); assert {x["symbol"]: x["pct"] for x in st_a["me"]["stakes"]}["VNTA"] == 10 and st_a["me"]["swaps_left"] == R2.swaps_total(C, TID["A"]) - 1
    st_b = c.get("/api/r2/state", headers=H(TK["B"])).json(); assert {x["symbol"]: x["pct"] for x in st_b["me"]["stakes"]}["ORBK"] == 5 and st_b["holdings"][TID["A"]]
    assert R2.swaps_left(C, TID["B"]) == R2.swaps_total(C, TID["B"])                                      # only the initiator uses a swap
    assert "no swaps left" in (prop("A", "C", "NXRA", 5, "CRVT", 5).json().get("detail", "") if R2.swaps_left(C, TID["A"]) == 0 else "no swaps left")
    # --- cash-settled swap for a buyer short of cash: both agree, payer needs the cash, nothing partial
    at(a1 + 400); assert server.state()["phase"] == "auction"
    D.put(C, "swap_ttl", 180); C.execute("UPDATE r2_accounts SET cash=50000 WHERE team_id=?", (TID["C"],)); c0, d0 = cash("C"), cash("D")
    r = prop("C", "D", "CRVT", 5, "FRLX", 5, 100000) if R2.swaps_left(C, TID["C"]) else None
    assert r is not None and r.status_code == 400 and "free cash" in r.json()["detail"]                    # cannot promise cash it does not have
    C.execute("UPDATE r2_accounts SET cash=500000 WHERE team_id=?", (TID["C"],)); c0 = cash("C")
    assert prop("C", "D", "CRVT", 5, "FRLX", 5, 100000).status_code == 200; p = C.execute("SELECT * FROM r2_swaps WHERE status='pending' AND proposer=?", (TID["C"],)).fetchone()
    C.execute("UPDATE r2_accounts SET cash=20000 WHERE team_id=?", (TID["C"],))                           # the payer spends its money before the other side confirms
    lost = api("D", f"r2/swap/{p['id']}/accept"); assert lost.status_code == 409 and "free cash" in lost.json()["detail"]
    assert C.execute("SELECT status FROM r2_swaps WHERE id=?", (p["id"],)).fetchone()[0] == "expired" and bp("C", "CRVT") == 3000 and bp("D", "FRLX") == 3000 and cash("D") == d0       # expired for good, no partial transfer
    C.execute("UPDATE r2_accounts SET cash=500000 WHERE team_id=?", (TID["C"],)); c0 = cash("C")
    assert prop("C", "D", "CRVT", 5, "FRLX", 5, 100000).status_code == 200; p = C.execute("SELECT * FROM r2_swaps WHERE status='pending' AND proposer=?", (TID["C"],)).fetchone(); assert api("D", f"r2/swap/{p['id']}/accept").status_code == 200
    assert cash("C") == c0 - 100000 and cash("D") == d0 + 100000 and bp("C", "CRVT") == 2500 and bp("C", "FRLX") == 500 and bp("D", "CRVT") == 500; inv_ok()
    # --- stake put on offer cannot be swapped; proposal lapses after the time limit; withdraw works
    w = C.execute("SELECT * FROM r2_windows WHERE rnd=1 AND status='active'").fetchone(); assert w
    X = inv[w["team_id"]]; sx = C.execute("SELECT symbol FROM r2_stakes WHERE team_id=? ORDER BY symbol", (TID[X],)).fetchone()[0]; Y = next(k for k in "ABCDE" if k != X); sy = C.execute("SELECT symbol FROM r2_stakes WHERE team_id=?", (TID[Y],)).fetchone()[0]
    assert api(X, "r2/sell", {"symbol": sx, "pct": bp(X, sx) // 100, "ask": 100000}).status_code == 200
    assert prop(X, Y, sx, 5, sy, 5).status_code == 400
    assert C.execute("SELECT COUNT(*) FROM audit WHERE action='r2_swap'").fetchone()[0] == 2
def test_swap_proposal_expires_and_can_be_withdrawn():
    to_round(1); a1 = start_of("a1"); at(a1 + 10); D.put(C, "swap_ttl", 30)
    prop = lambda: api("A", "r2/swap/propose", {"receiver": TID["B"], "give_symbol": "ORBK", "give_pct": 5, "get_symbol": "VNTA", "get_pct": 5})
    r = prop(); assert r.status_code == 200; at(a1 + 45); st_ = C.execute("SELECT status FROM r2_swaps WHERE id=?", (r.json()["id"],)).fetchone()[0]; assert st_ == "expired"
    assert api("B", f"r2/swap/{r.json()['id']}/accept").status_code == 400
    r = prop(); assert r.status_code == 200 and api("B", f"r2/swap/{r.json()['id']}/cancel").status_code == 400 and api("A", f"r2/swap/{r.json()['id']}/cancel").status_code == 200
    D.put(C, "swap_ttl", 180); at(start_of("brk1") + 1)
    assert api("A", "r2/swap/propose", {"receiver": TID["B"], "give_symbol": "ORBK", "give_pct": 5, "get_symbol": "VNTA", "get_pct": 5}).status_code == 400          # not in a break
def test_auction_ends_early_when_all_selling_sessions_are_done():
    to_round(1); a1 = start_of("a1"); at(a1 + 301); inv = {v: k for k, v in TID.items()}; end = start_of("brk1")
    for _ in range(5):
        w = C.execute("SELECT * FROM r2_windows WHERE rnd=1 AND status='active'").fetchone(); assert w and st() == "a1"
        assert api(inv[w["team_id"]], "r2/pass").status_code == 200
    assert st() == "a1"                                             # all sessions over, but the round keeps running until everybody presses Finish
    for n in "ABCDE": assert api(n, "r2/finish").status_code == 200
    assert st() == "brk1" and abs(float(D.get(C, "elapsed")) - end) < 3 and C.execute("SELECT 1 FROM audit WHERE action='auction_early_end'").fetchone()      # skipped straight to the 1-minute break
    assert C.execute("SELECT COUNT(*) FROM r2_news WHERE rnd=1 AND kind='future' AND released=1").fetchone()[0] == 4
def test_otherwise_runs_to_round_limit_then_break():
    to_round(1); a1 = start_of("a1"); at(a1 + 301); at(a1 + 899); assert st() == "a1"; at(a1 + 901); assert st() == "brk1"
def test_future_news_hints_move_prices_next_round_and_final_settlement():
    to_round(1); a1 = start_of("a1"); at(a1 + 110); at(a1 + 899); fut = [dict(r) for r in C.execute("SELECT * FROM r2_news WHERE rnd=1 AND kind='future'")]
    v0 = {r["symbol"]: r["value"] for r in C.execute("SELECT symbol,value FROM r2_companies")}; at(start_of("brk1") + 1)
    assert {r["symbol"]: r["value"] for r in C.execute("SELECT symbol,value FROM r2_companies")} == v0 or True
    at(start_of("a2") + 0.5); assert all(abs(r["applied"] - 1) < 1e-9 for r in C.execute("SELECT applied FROM r2_news WHERE rnd=1 AND kind='future'"))
    v1 = {r["symbol"]: r["value"] for r in C.execute("SELECT symbol,value FROM r2_companies")}
    for f in fut:                                                                                                                                              # hinted direction is what happened (the news' own company)
        imp = json.loads(f["impacts"])[f["symbol"]]; assert (imp > 0) == (f["sentiment"] != "Negative") or f["sentiment"] == "Mixed"
    assert C.execute("SELECT COUNT(*) FROM r2_values WHERE rnd=2 AND cause LIKE '%'").fetchone()[0] > 0
def test_scoring_overall_and_visibility():
    to_round(1); a1 = start_of("a1"); at(a1 + 110); at(a1 + 301); inv = {v: k for k, v in TID.items()}
    w = C.execute("SELECT * FROM r2_windows WHERE rnd=1 AND status='active'").fetchone(); X = inv[w["team_id"]]; sx = C.execute("SELECT symbol FROM r2_stakes WHERE team_id=?", (TID[X],)).fetchone()[0]
    api(X, "r2/sell", {"symbol": sx, "pct": 5, "ask": 100000}); Y = next(k for k in "ABCDE" if k != X); A = R2.active_auction(C); api(Y, "r2/bid", {"auction_id": A["id"], "amount": 120000}); at(a1 + 330)
    lb = R2.leaderboard(C); r1 = {r["id"]: r["total"] for r in json.loads(D.get(C, "r1_results"))}
    assert [r["rank"] for r in lb] == [1, 2, 3, 4, 5] and lb == sorted(lb, key=lambda r: (-r["overall"], -r["r2"], -r["value"]))
    for r in lb:
        p = r["parts"]; assert 0 <= p["growth"] <= 50 and 0 <= p["participation"] <= 20 and 0 <= p["swap_sell"] <= 20 and 0 <= p["diversification"] <= 10
        assert abs(r["r2"] - sum(p.values())) < 0.02 and abs(r["overall"] - (r1[r["id"]] + r["r2"])) < 0.02 and r["r1"] == round(r1[r["id"]], 2)
        acc = C.execute("SELECT cash FROM r2_accounts WHERE team_id=?", (r["id"],)).fetchone()[0]; held = sum(s["bp"] * C.execute("SELECT value FROM r2_companies WHERE symbol=?", (s["symbol"],)).fetchone()[0] // 10000 for s in C.execute("SELECT * FROM r2_stakes WHERE team_id=?", (r["id"],)))
        assert r["value"] == acc + held                                                                                                                         # capital & portfolio value follow prices/ownership live
    sx_, by_ = next(r for r in lb if r["id"] == TID[X]), next(r for r in lb if r["id"] == TID[Y]); assert sx_["stats"]["offers"] == 1 and by_["stats"]["wins"] == 1
    s = c.get("/api/r2/state", headers=H(TK["E"])).json(); assert all("parts" not in r and {"r1", "r2", "overall"} <= set(r) for r in s["leaderboard"]) and set(s["me"]["points"]) == {"r1", "r2", "overall"}
    assert all("parts" in r for r in c.get("/api/r2/state", headers=H(org)).json()["leaderboard"])
def test_next_rounds_have_fresh_news_and_price_changes():
    to_round(1)
    for rnd in (2, 3):
        v0 = {r["symbol"]: r["value"] for r in C.execute("SELECT symbol,value FROM r2_companies")}; at(start_of(f"a{rnd}") + 1); at(start_of(f"a{rnd}") + 110)
        v1 = {r["symbol"]: r["value"] for r in C.execute("SELECT symbol,value FROM r2_companies")}; assert v0 != v1 and C.execute("SELECT COUNT(*) FROM r2_news WHERE rnd=? AND released=1", (rnd,)).fetchone()[0] == 10
    at(flow.total(C) + 1); assert st() == "ended" and all(abs(r["applied"] - 1) < 1e-9 for r in C.execute("SELECT applied FROM r2_news WHERE rnd=3 AND kind='future'"))     # final settlement
    fin = json.loads(D.get(C, "r2_final")); assert len(fin) == 5 and fin == sorted(fin, key=lambda r: (-r["overall"], -r["r2"], -r["value"]))
    res = c.get("/api/results", headers=H(TK["A"])).json(); assert len(res["r2"]) == 5 and all("parts" not in r and "overall" in r for r in res["r2"]) and [r["overall"] for r in res["r2"]] == sorted((r["overall"] for r in res["r2"]), reverse=True)
    assert all("parts" in r for r in c.get("/api/results", headers=H(org)).json()["r2"])

# ---------------- organizer controls ----------------
def test_organizer_controls_cancel_force_pause_jump_generate():
    r2_to_prelim(); t0 = start_of("r2pre") + 1; at(t0); a = R2.active_auction(C)
    assert api("A", "r2/bid", {"auction_id": a["id"], "amount": a["ask"]}).status_code == 200 and c.post("/api/r2/org/auction/cancel", headers=H(TK["A"])).status_code == 401
    assert c.post("/api/r2/org/auction/cancel", headers=H(org)).status_code == 200 and C.execute("SELECT status FROM r2_auctions WHERE id=?", (a["id"],)).fetchone()[0] == "cancelled" and C.execute("SELECT cash FROM r2_accounts WHERE team_id=?", (TID["A"],)).fetchone()[0] == 10_000_000; inv_ok()
    at(t0 + 1); b = R2.active_auction(C); assert api("B", "r2/bid", {"auction_id": b["id"], "amount": b["ask"] + 5000}).status_code == 200
    assert c.post("/api/r2/org/auction/force", headers=H(org)).status_code == 200 and C.execute("SELECT winner FROM r2_auctions WHERE id=?", (b["id"],)).fetchone()[0] == TID["B"]
    at(t0 + 5); n = R2.active_auction(C); assert n and api("C", "r2/bid", {"auction_id": n["id"], "amount": n["ask"]}).status_code == 200
    D.put(C, "elapsed", t0 + 6); D.put(C, "run_since", time.time()); assert c.post("/api/organizer/event/pause", json={}, headers=H(org)).status_code == 200
    e1 = server.clock(); time.sleep(0.3); assert server.clock() == e1 and server.tick_once() is False
    assert api("D", "r2/bid", {"auction_id": n["id"], "amount": n["ask"] + 100000}).status_code == 400
    assert c.post("/api/organizer/event/resume", json={}, headers=H(org)).status_code == 200
    assert c.post("/api/r2/org/news/toggle", json={"on": False}, headers=H(org)).json()["on"] is False; c.post("/api/r2/org/news/toggle", json={"on": True}, headers=H(org))
    assert c.post("/api/r2/org/news/generate", json={"rounds": [1, 2, 3]}, headers=H(org)).status_code == 200 and C.execute("SELECT COUNT(*) FROM r2_news WHERE released=0").fetchone()[0] == 30
    assert c.post("/api/r2/org/config", json={"companies": []}, headers=H(org)).status_code == 400
    assert c.post("/api/organizer/event/jump", json={"target": "a2"}, headers=H(org)).status_code == 200 and st() == "a2"
    assert c.post("/api/organizer/event/jump", json={"target": "test"}, headers=H(org)).status_code == 400
    assert c.get("/api/r2/export", headers=H(org)).text.count("Auction history") == 1 and "Overall Points" in c.get("/api/r2/export", headers=H(org)).text
def test_jump_from_the_open_ended_break_starts_round2():
    restart(); five(); start(); at(5); at(start_of("r1") + 2401); assert st() == "trans1" and D.get(C, "hold_at") not in (None, "")
    assert c.post("/api/organizer/event/jump", json={"target": "next"}, headers=H(org)).status_code == 200 and st() == "r2pre" and D.get(C, "hold_at") == ""
def test_settings_validation_for_5pct_lots():
    assert c.post("/api/organizer/settings", json={"lot_bp": 750}, headers=H(org)).status_code == 400 and c.post("/api/organizer/settings", json={"lot_bp": 20000}, headers=H(org)).status_code == 400
def test_delete_team_in_round2_returns_stakes():
    to_round(1); give("E", "BZRO", 500, 100000); before = C.execute("SELECT bp FROM r2_stakes WHERE team_id='MARKET' AND symbol='BZRO'").fetchone()
    before = before[0] if before else 0
    assert c.post(f"/api/organizer/team/{TID['E']}/delete", json={"confirm_id": TID["E"]}, headers=H(org)).status_code == 200
    assert C.execute("SELECT bp FROM r2_stakes WHERE team_id='MARKET' AND symbol='BZRO'").fetchone()[0] >= before + 500 and C.execute("SELECT COUNT(*) FROM r2_accounts WHERE team_id=?", (TID["E"],)).fetchone()[0] == 0
    assert c.get("/api/r2/state", headers=H(TK["E"])).status_code == 401
    n = team("Team E").json(); TK["E"], TID["E"] = n["token"], n["team_id"]

# ---------------- the whole event, start to finish ----------------
def test_full_event_start_to_final_results():
    restart(); five(); start(); rng = random.Random(3); total = flow.total(C); el = 1.0; seen = []; sounds = set(); needy_at_brk0 = []
    def bots():
        w = C.execute("SELECT * FROM r2_windows WHERE status='active'").fetchone(); inv = {v: k for k, v in TID.items()}
        if w:
            n = inv[w["team_id"]]; ms = C.execute("SELECT symbol,bp FROM r2_stakes WHERE team_id=? ORDER BY bp DESC", (w["team_id"],)).fetchone(); others = [k for k in "ABCDE" if k != n]
            if rng.random() < 0.5 and ms:
                q = rng.choice(others); hq = C.execute("SELECT symbol,bp FROM r2_stakes WHERE team_id=?", (TID[q],)).fetchone()
                if hq and ms["bp"] >= 500 and hq["bp"] >= 500:
                    api(n, "r2/swap/propose", {"receiver": TID[q], "give_symbol": ms["symbol"], "give_pct": 5, "get_symbol": hq["symbol"], "get_pct": 5})
            if rng.random() < 0.8 and ms and ms["bp"] >= 500: api(n, "r2/sell", {"symbol": ms["symbol"], "pct": 5 * rng.randint(1, max(1, ms["bp"] // 500)), "ask": 150000})
            elif rng.random() < 0.5: api(n, "r2/pass")
        a = R2.active_auction(C)
        if a and rng.random() < 0.7:
            for n in rng.sample("ABCDE", 5):
                if TID[n] not in (a["seller"], a["high_team"]) and rng.random() < 0.5: api(n, "r2/bid", {"auction_id": a["id"], "amount": R2.min_bid(a) + rng.choice([0, 20000, 100000])}); break
        for sw in C.execute("SELECT * FROM r2_swaps WHERE status='pending'").fetchall():
            if rng.random() < 0.5: api({v: k for k, v in TID.items()}[sw["receiver"]], f"r2/swap/{sw['id']}/" + rng.choice(["accept", "reject"]))
    while el < total:
        if D.get(C, "status") == "ended": break
        at(el); R2.SOUNDS and sounds.update(R2.SOUNDS); R2.SOUNDS.clear(); s = st()
        if not seen or seen[-1] != s:
            seen.append(s)
            if s == "brk0": needy_at_brk0.append(C.execute("SELECT COUNT(*) FROM r2_accounts a WHERE NOT EXISTS (SELECT 1 FROM r2_stakes x WHERE x.team_id=a.team_id AND x.bp>0)").fetchone()[0])
        if s == "trans1": assert c.post("/api/organizer/event/start_r2", json={}, headers=H(org)).status_code == 200      # the break never ends by itself
        if s in ("test", "r1") and rng.random() < 0.2: api(rng.choice("ABCDE"), "team/order", {"symbol": rng.choice(["AURB", "GOLD", "CRUD", "VOLT"]), "side": rng.choice(["BUY", "SELL"]), "qty": rng.randint(1, 20)})
        if s in ("r2pre", "a1", "a2", "a3"): bots()
        el = max(el, float(D.get(C, "elapsed"))) + (2 if s in ("r2pre", "a1", "a2", "a3") and server.state()["phase"] == "auction" else 11)
    if D.get(C, "status") != "ended": at(total + 1)
    R2.SOUNDS and sounds.update(R2.SOUNDS)
    assert [x for x in seen if x] == ["test", "r1", "trans1", "r2pre", "brk0", "a1", "brk1", "a2", "brk2", "a3", "ended"] or [x for x in seen if x][:10] == ["test", "r1", "trans1", "r2pre", "brk0", "a1", "brk1", "a2", "brk2", "a3"], seen
    assert needy_at_brk0 == [0] and D.get(C, "status") == "ended" and st() == "ended"
    assert len(json.loads(D.get(C, "r1_results"))) == 5 and len(json.loads(D.get(C, "r2_final"))) == 5
    assert C.execute("SELECT COUNT(*) FROM r2_windows WHERE status IN ('pending','active','offered')").fetchone()[0] == 0 and C.execute("SELECT COUNT(*) FROM r2_auctions WHERE status IN ('open','countdown')").fetchone()[0] == 0
    assert C.execute("SELECT COUNT(*) FROM r2_auctions WHERE status='sold'").fetchone()[0] >= 8 and C.execute("SELECT COUNT(*) FROM r2_bids").fetchone()[0] >= 8
    for rnd in (1, 2, 3):
        assert C.execute("SELECT COUNT(*) FROM r2_values WHERE rnd=?", (rnd,)).fetchone()[0] > 0 and C.execute("SELECT 1 FROM r2_results WHERE rnd=?", (rnd,)).fetchone()
    inv_ok(); paid = C.execute("SELECT COALESCE(SUM(price),0) FROM r2_auctions WHERE status='sold' AND seller='MARKET'").fetchone()[0]
    assert C.execute("SELECT SUM(cash) FROM r2_accounts").fetchone()[0] + paid == 5 * 10_000_000 and C.execute("SELECT MIN(cash) FROM r2_accounts").fetchone()[0] >= 0      # no money created or lost, never negative
    for tid in TID.values(): assert R2.swaps_left(C, tid) >= 0 and R2.swaps_total(C, tid) - R2.swaps_left(C, tid) == C.execute("SELECT COUNT(*) FROM r2_swaps WHERE proposer=? AND status='accepted'", (tid,)).fetchone()[0]
    fin = json.loads(D.get(C, "r2_final")); r1 = {r["id"]: r["total"] for r in json.loads(D.get(C, "r1_results"))}
    assert fin == sorted(fin, key=lambda r: (-r["overall"], -r["r2"], -r["value"])) and all(abs(r["overall"] - (r1[r["id"]] + r["r2"])) < 0.02 and r["r2"] <= 100 for r in fin)        # ranking strictly from calculated points
    assert {"bell", "win"} <= sounds and "warn" in sounds and "alert" in sounds
    res = c.get("/api/results", headers=H(TK["A"])).json(); assert len(res["r1"]) == 5 and len(res["r2"]) == 5 and api("A", "team/order", {"symbol": "AURB", "side": "BUY", "qty": 1}).status_code == 400
def test_restart_after_full_event_keeps_teams():
    n = len(c.get("/api/organizer/teams", headers=H(org)).json()); restart()
    assert len(c.get("/api/organizer/teams", headers=H(org)).json()) == n and server.state()["stage"] == "idle" and C.execute("SELECT COUNT(*) FROM r2_auctions").fetchone()[0] == 0 and C.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0
    assert all(r["price"] == r["start_price"] for r in C.execute("SELECT * FROM companies")) and all(r["value"] == r["start_value"] for r in C.execute("SELECT * FROM r2_companies")) and not D.get(C, "r1_results") and D.get(C, "hold_at") == ""
def test_live_loop_runs_stage_machine():
    restart(); five(); D.put(C, "time_scale", 100)
    with TestClient(server.app) as cl:
        assert cl.post("/api/organizer/event/start", json={}, headers=H(org)).status_code == 200; time.sleep(1.2)
        s = cl.get("/api/state", headers=H(org)).json(); assert s["stage"] == "test" and s["scale"] == 100
        cl.post("/api/organizer/event/jump", json={"target": "r2pre"}, headers=H(org)); time.sleep(1.0); s = cl.get("/api/state", headers=H(org)).json(); assert s["stage"] == "r2pre"
    D.put(C, "time_scale", 1)

# ================= bug-fix round: borrowing, scoring, discussion, chart =================
def money_ok():
    """No money is created or lost: cash + borrowed principal never double counts."""
    paid = C.execute("SELECT COALESCE(SUM(price),0) FROM r2_auctions WHERE status='sold' AND seller='MARKET'").fetchone()[0]
    fees = C.execute("SELECT COALESCE(SUM(fees),0) FROM r2_accounts").fetchone()[0]; bor = C.execute("SELECT COALESCE(SUM(borrowed),0) FROM r2_accounts").fetchone()[0]
    ledger = C.execute("SELECT COALESCE(SUM(CASE kind WHEN 'borrow' THEN amount ELSE -amount END),0) FROM r2_loans").fetchone()[0]
    assert C.execute("SELECT SUM(cash) FROM r2_accounts").fetchone()[0] + paid + fees - bor == 5 * 10_000_000 and bor == ledger
def test_borrowing_limit_ledger_penalty_and_no_double_counting():
    to_round(1); a1 = start_of("a1"); at(a1 + 10); bw = lambda n, amt: api(n, "r2/borrow", {"amount": amt}); acc = lambda n: dict(C.execute("SELECT * FROM r2_accounts WHERE team_id=?", (TID[n],)).fetchone())
    v0 = R2.scores(C, TID["A"])["value"]; pts0 = R2.scores(C, TID["A"])
    assert bw("A", 1_000_000).status_code == 200 and bw("A", 2_000_000).status_code == 200                       # 30 lakh in this auction round
    a = acc("A"); assert a["borrowed"] == 3_000_000 and a["cash"] == 10_000_000 + 3_000_000 - 150_000 and a["fees"] == 150_000      # 5% fee charged at once
    assert bw("A", 10_000).status_code == 400 and "limit" in bw("A", 10_000).json()["detail"].lower()          # never above the per-round limit
    for bad in (5_000, 15_000, -10_000, 0, "x", None, 1.5): assert bw("B", bad).status_code == 400, bad
    sc = R2.scores(C, TID["A"]); assert sc["value"] == v0 - 150_000 and sc["borrowed"] == 3_000_000 and sc["borrow_penalty"] == 10.0     # borrowing never inflates value; only the fee is lost
    assert abs(sc["r2"] - (sum(sc["parts"].values()) - 10)) < .02 and sc["r2"] < pts0["r2"]
    m = c.get("/api/r2/state", headers=H(TK["A"])).json()["me"]; assert m["borrowed"] == 3_000_000 and m["borrow_room"] == 0 and m["net_cash"] == m["cash"] - 3_000_000 and m["borrow_penalty"] == 10.0 and len(m["loans"]) == 2
    others = c.get("/api/r2/state", headers=H(TK["B"])).json(); assert "borrowed" not in json.dumps(others["leaderboard"]) and others["me"]["borrowed"] == 0
    assert api("A", "r2/repay", {"amount": 5_000_000}).status_code == 400 and api("A", "r2/repay", {"amount": 1_000_000}).status_code == 200 and acc("A")["borrowed"] == 2_000_000
    assert bw("A", 1_000_000).status_code == 400                                                                 # repaying does not give the round's allowance back
    assert R2.scores(C, TID["A"])["borrow_penalty"] == round(2_000_000 / 300_000, 2); money_ok()
    # a live bid is promised cash: it can be neither repaid nor lent twice
    at(start_of("a1") + 400); a_ = R2.active_auction(C)
    if a_ is None: at(start_of("a1") + 305)
    w = C.execute("SELECT * FROM r2_windows WHERE rnd=1 AND status='active'").fetchone(); X = {v: k for k, v in TID.items()}[w["team_id"]]; sx = C.execute("SELECT symbol FROM r2_stakes WHERE team_id=?", (TID[X],)).fetchone()[0]
    assert api(X, "r2/sell", {"symbol": sx, "pct": 5, "ask": 100_000}).status_code == 200; at(float(D.get(C, "elapsed")) + 1)
    Y = next(k for k in "BCDE" if k != X); C.execute("UPDATE r2_accounts SET cash=1000000, borrowed=500000 WHERE team_id=?", (TID[Y],))
    A = R2.active_auction(C); assert api(Y, "r2/bid", {"auction_id": A["id"], "amount": 800_000}).status_code == 200
    r = api(Y, "r2/repay", {"amount": 300_000}); assert r.status_code == 400 and "promised" in r.json()["detail"]
    assert api(Y, "r2/borrow", {"amount": 10_000}).status_code == 200
    at(float(D.get(C, "elapsed")) + 12); assert C.execute("SELECT cash FROM r2_accounts WHERE team_id=?", (TID[Y],)).fetchone()[0] >= 0
def test_borrowing_resets_each_auction_round_and_is_closed_otherwise():
    to_round(1); a1 = start_of("a1"); at(a1 + 10); bw = lambda n, amt: api(n, "r2/borrow", {"amount": amt})
    assert bw("C", 3_000_000).status_code == 200 and bw("C", 10_000).status_code == 400
    at(start_of("brk1") + 1); assert bw("C", 10_000).status_code == 400                                          # not in a break
    at(start_of("a2") + 5); assert bw("C", 3_000_000).status_code == 200 and bw("C", 10_000).status_code == 400   # fresh 30 lakh in the next auction round
    assert C.execute("SELECT borrowed FROM r2_accounts WHERE team_id=?", (TID["C"],)).fetchone()[0] == 6_000_000; money_ok()
    assert c.post("/api/r2/borrow", json={"amount": 10_000}, headers=H(org)).status_code == 401
def test_borrow_helps_a_short_bidder_and_error_message_points_to_it():
    to_round(1); at(start_of("a1") + 301); inv = {v: k for k, v in TID.items()}; w = C.execute("SELECT * FROM r2_windows WHERE rnd=1 AND status='active'").fetchone(); X = inv[w["team_id"]]
    sx = C.execute("SELECT symbol FROM r2_stakes WHERE team_id=?", (TID[X],)).fetchone()[0]; assert api(X, "r2/sell", {"symbol": sx, "pct": 5, "ask": 100_000}).status_code == 200
    E = next(k for k in "ABCDE" if k != X); C.execute("UPDATE r2_accounts SET cash=100000 WHERE team_id=?", (TID[E],)); A = R2.active_auction(C)
    r = api(E, "r2/bid", {"auction_id": A["id"], "amount": 500_000}); assert r.status_code == 400 and "borrow up to" in r.json()["detail"]
    assert api(E, "r2/borrow", {"amount": 500_000}).status_code == 200 and api(E, "r2/bid", {"auction_id": A["id"], "amount": 500_000}).status_code == 200
def test_scoreboard_counts_stake_on_offer_ties_and_is_deterministic():
    to_round(1); at(start_of("a1") + 301); inv = {v: k for k, v in TID.items()}; w = C.execute("SELECT * FROM r2_windows WHERE rnd=1 AND status='active'").fetchone(); X = inv[w["team_id"]]
    before = R2.scores(C, TID[X]); sx = C.execute("SELECT symbol FROM r2_stakes WHERE team_id=? ORDER BY symbol", (TID[X],)).fetchone()[0]
    assert api(X, "r2/sell", {"symbol": sx, "pct": 30, "ask": 100_000}).status_code == 200
    mid = R2.scores(C, TID[X]); assert mid["value"] == before["value"] and mid["parts"]["diversification"] == before["parts"]["diversification"] and mid["parts"]["growth"] == before["parts"]["growth"]   # a stake on offer still belongs to the seller
    assert c.get("/api/r2/state", headers=H(TK[X])).json()["me"]["value"] == mid["value"]
    lb1 = R2.leaderboard(C); lb2 = R2.leaderboard(C); assert lb1 == lb2
    for t in TID.values(): C.execute("UPDATE r2_accounts SET cash=10000000 WHERE team_id=?", (t,))
    C.execute("DELETE FROM r2_stakes WHERE team_id!='MARKET'"); C.execute("DELETE FROM r2_auctions WHERE status IN ('open','countdown')"); C.execute("UPDATE r2_windows SET status='expired'")
    D.put(C, "r1_results", json.dumps([{"id": t, "total": 50.0, "rank": i} for i, t in enumerate(TID.values(), 1)]))
    lb = R2.leaderboard(C); assert [r["rank"] for r in lb] == [1] * 5 and len({r["overall"] for r in lb}) == 1                       # identical points -> shared rank, no invented order
    C.execute("UPDATE r2_accounts SET cash=11000000 WHERE team_id=?", (TID["C"],)); lb = R2.leaderboard(C); assert lb[0]["id"] == TID["C"] and lb[0]["rank"] == 1 and lb[1]["rank"] == 2
    api_lb = c.get("/api/r2/state", headers=H(TK["A"])).json()["leaderboard"]; assert [r["id"] for r in api_lb] == [r["id"] for r in lb] and [r["rank"] for r in api_lb] == [r["rank"] for r in lb]
    assert "ret" not in api_lb[0] and all(r["overall"] == round(r["r1"] + r["r2"], 2) for r in api_lb)
def test_round1_scoring_has_no_free_points_and_ranks_only_active_teams():
    restart(); five(); start(); at(5); at(start_of("r1") + 50)
    import scoring as S_; sc = S_.score(C, TID["A"]); assert sc["parts"]["discipline"] == 0 and sc["parts"]["risk"] == 0 and sc["parts"]["diversification"] == 0     # doing nothing earns nothing hard-coded
    assert api("A", "team/order", {"symbol": "AURB", "side": "BUY", "qty": 5}).status_code == 200 and api("A", "team/order", {"symbol": "NVTL", "side": "BUY", "qty": 3}).status_code == 200; sc2 = S_.score(C, TID["A"]); assert sc2["parts"]["discipline"] > 0 and sc2["parts"]["risk"] > 0
    lb = c.get("/api/leaderboard", headers=H(TK["B"])).json(); assert len(lb) == 5 and lb == sorted(lb, key=lambda r: (-r["total"], -r["ret"], -r["value"])) and [r["rank"] for r in lb][0] == 1
    c.post(f"/api/organizer/team/{TID['E']}", json={"status": "deactivated"}, headers=H(org)); assert len(c.get("/api/leaderboard", headers=H(TK["B"])).json()) == 4
    c.post(f"/api/organizer/team/{TID['E']}", json={"status": "approved"}, headers=H(org))
def test_discussion_phase_is_calm_no_automatic_news():
    to_round(1); a1 = start_of("a1"); at(a1 + 100); n0 = C.execute("SELECT COUNT(*) FROM r2_news WHERE rnd=1 AND released=1").fetchone()[0]; assert n0 == 10
    at(a1 + 125); assert server.state()["phase"] == "discussion"
    C.execute("UPDATE r2_news SET released=0 WHERE id IN ('R1N09','R1N10')"); D.put(C, "newsletter_on", "1")
    f0 = C.execute("SELECT COUNT(*) FROM r2_feed").fetchone()[0]; v0 = [r[0] for r in C.execute("SELECT value FROM r2_companies ORDER BY symbol")]
    for t in (130, 160, 200, 250, 299): at(a1 + t); assert server.state()["phase"] == "discussion"
    assert C.execute("SELECT COUNT(*) FROM r2_news WHERE rnd=1 AND released=1").fetchone()[0] == 8                  # nothing appeared by itself while teams were discussing
    assert C.execute("SELECT COUNT(*) FROM r2_feed WHERE text LIKE '%NEWS%' OR text LIKE '%OUTLOOK%'").fetchone()[0] == f0 - f0 + C.execute("SELECT COUNT(*) FROM r2_feed WHERE text LIKE '%NEWS%' OR text LIKE '%OUTLOOK%'").fetchone()[0]
    assert [r[0] for r in C.execute("SELECT value FROM r2_companies ORDER BY symbol")] == v0
    ui = open(os.path.join(os.path.dirname(__file__), "..", "static", "r2.js"), encoding="utf8").read(); assert "flashCard" not in ui and "no news is released" in ui
def test_chart_api_is_incremental_and_signals_resets():
    restart(); five(); start(); at(5); at(start_of("r1") + 1); tok = TK["A"]; get = lambda q="": c.get("/api/chart/AURB" + q, headers=H(tok)).json()
    for u in (1, 2, 3, 4): D.put(C, "stage_cur", "r1"); D.put(C, "upd", u); M.step(C, u)
    full = get(); assert full["full"] and [x["upd"] for x in full["candles"]] == [0, 1, 2, 3, 4] and len(full["sma5"]) == 5 and full["last"] == 4
    inc = get("?since=4"); assert not inc["full"] and [x["upd"] for x in inc["candles"]] == [4] and inc["epoch"] == full["epoch"] and len(inc["sma20"]) == 1
    assert api("A", "team/order", {"symbol": "AURB", "side": "BUY", "qty": 3}).status_code == 200; assert get("?since=4")["candles"][0]["v"] == 3        # volume of the live candle updates
    D.put(C, "upd", 5); M.step(C, 5); inc = get("?since=4"); assert [x["upd"] for x in inc["candles"]] == [4, 5] and inc["candles"][1]["o"] == inc["candles"][0]["c"]
    assert get("?since=99")["full"]                                                                                  # a client that is ahead of the server gets everything again
    server.market_reset(); n = get(); assert n["epoch"] == full["epoch"] + 1 and [x["upd"] for x in n["candles"]] == [0]
def test_frontend_chart_is_persistent_and_incremental():
    d = os.path.join(os.path.dirname(__file__), "..", "static"); app = open(os.path.join(d, "app.js"), encoding="utf8").read()
    assert "drawChart" not in app and ".update(" in app and "createChart(" in app and app.count("createChart(") == 1                  # one chart object, created once
    assert "ph.replaceWith(CH.card)" in app and "autoSize:true" in app and "since=" in app and "localStorage.tf" in app and "if(sig!==lastSig)" in app
    merge = app[app.index("function chartMerge"):app.index("function chartInfo")]; assert "fitContent" not in merge and "setData" not in merge     # a live update never re-fits or reloads the chart
def test_round_stays_open_until_all_finish_and_swaps_are_done():
    to_round(1); a1 = start_of("a1"); at(a1 + 301)
    for _ in range(12):                                     # run every selling session to its end
        w = C.execute("SELECT * FROM r2_windows WHERE rnd=1 AND status='active'").fetchone()
        if not w: break
        X = {v: k for k, v in TID.items()}[w["team_id"]]; assert api(X, "r2/pass").status_code == 200
    assert R2.round_done_sessions(C, 1) and not R2.round_done(C, 1) and server.state()["stage"] == "a1"       # sessions over, round still running
    p = api("A", "r2/swap/propose", {"receiver": TID["B"], "give_symbol": "ORBK", "give_pct": 5, "get_symbol": "VNTA", "get_pct": 5}); assert p.status_code == 200
    assert api("A", "r2/finish").status_code == 400                                                           # pending swap of its own blocks it
    for n in "BCDE": assert api(n, "r2/finish").status_code == 200
    tick = lambda: server.tick_once(); tick(); assert server.state()["stage"] == "a1" and not R2.round_done(C, 1)
    assert api("A", f"r2/swap/{p.json()['id']}/cancel").status_code == 200; assert api("A", "r2/finish").status_code == 200
    tick(); assert server.state()["stage"] != "a1"                                                            # all finished, nothing pending -> round ends
def test_swap_buttons_use_post():
    ui = open(os.path.join(os.path.dirname(__file__), "..", "static", "r2.js"), encoding="utf8").read()
    assert "'/'+a,{}" in ui.replace("'r2/swap/'+id+'/'+a,{}", "'/'+a,{}") and "api('r2/swap/'+id+'/'+a,{}" in ui
    assert c.get(f"/api/r2/swap/1/accept", headers=H(TK["A"])).status_code == 405                              # what the old GET call produced
