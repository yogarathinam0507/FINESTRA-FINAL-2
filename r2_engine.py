"""ROUND 2 – Industry Titans: The Stake Auction.  All money is integer rupees, stakes are integer basis points (10000 = 100%).
Everything here is server-side; clients only send intents (bid / sell / pass / swap)."""
import json, random, time
import database as D, flow, r2_seed as SEED
from database import tx
SOUNDS = []              # drained by the server loop and broadcast to clients
class R2Error(Exception): pass
def fmt_inr(n):
    n = int(n)
    return f"₹{n/1e7:.2f} Cr" if abs(n) >= 1e7 else f"₹{n/1e5:.2f} L" if abs(n) >= 1e5 else f"₹{n:,}"
def feed(c, text, rnd=None): c.execute("INSERT INTO r2_feed(ts,rnd,text) VALUES(?,?,?)", (time.time(), rnd if rnd is not None else int(D.get(c, "r2_round", 0)), text))
def audit(c, action, detail): c.execute("INSERT INTO audit(ts,actor,action,detail) VALUES(?,?,?,?)", (time.time(), "system", action, json.dumps(detail)))
def tname(c, tid):
    if tid == "MARKET": return "Market (promoter lots)"
    r = c.execute("SELECT name FROM teams WHERE id=?", (tid,)).fetchone(); return r["name"] if r else str(tid)
# ---------------- setup ----------------
def ensure_companies(c):
    if c.execute("SELECT COUNT(*) FROM r2_companies").fetchone()[0]: return
    for i, (code, ind, name, sym, val, icon) in enumerate(SEED.INDUSTRIES):
        c.execute("INSERT INTO r2_companies VALUES(?,?,?,?,?,?,?,?)", (sym, ind, name, val, val, i, icon, code))
def comps(c): return [dict(r) for r in c.execute("SELECT * FROM r2_companies ORDER BY ord")]
def participants(c):
    n = int(D.get(c, "r2_teams")); ids = []
    try: ids = [r["id"] for r in json.loads(D.get(c, "r1_results") or "[]")]
    except Exception: pass
    ok = [r["id"] for r in c.execute("SELECT id FROM teams WHERE status='approved' ORDER BY id")]
    ids = [i for i in ids if i in ok] + [i for i in ok if i not in ids]
    return ids[:n]
def gen_news(c, rounds=(1, 2, 3), seed=None):
    seed = seed if seed is not None else int(time.time()) % 100000; cs = comps(c)
    cov = D.get(c, "r2_cover_seed")
    if cov in (None, "") or 1 in rounds: cov = seed; D.put(c, "r2_cover_seed", cov)        # which industries are skipped in which round stays stable when only later rounds are regenerated
    code = {x["industry"]: x["code"] for x in cs}; used = set()
    for r in c.execute("SELECT industry,tkey FROM r2_news WHERE released=1 OR rnd NOT IN (%s)" % ",".join(str(x) for x in rounds)): used.add((code.get(r["industry"]), r["tkey"]))
    for rnd in rounds:
        c.execute("DELETE FROM r2_news WHERE rnd=? AND released=0", (rnd,))
        for r in SEED.gen_round(rnd, cs, used, seed, int(cov)):
            # NEUTRAL NEWSLETTER REFINEMENT: Strip color sentiment or emotional tags, make text neutral business reports covering broad industries with vague hints/rumors.
            headline = r.get("headline", "")
            subhead = r.get("subhead", "")
            body = r.get("body", "")
            r["sentiment"] = "neutral"
            r["severity"] = "moderate"
            c.execute("INSERT OR REPLACE INTO r2_news(id,rnd,kind,ord,tkey,industry,symbol,headline,subhead,body,category,severity,sentiment,icon,impacts) VALUES(:id,:rnd,:kind,:ord,:tkey,:industry,:symbol,:headline,:subhead,:body,:category,:severity,:sentiment,:icon,:impacts)", r)
def init(c):
    """Called when Round 2 begins: fresh accounts (Rs 1 Cr each), market-held 100% stakes, one 100% lot per company, news (kept if organiser pre-generated it).
    The team ranked #1 after Round 1 gets 2 swaps for the whole of Round 2, every other team gets 1."""
    with tx(c):
        for t in ("r2_accounts", "r2_stakes", "r2_auctions", "r2_bids", "r2_windows", "r2_swaps", "r2_feed", "r2_values", "r2_results", "r2_loans", "r2_finish"): c.execute(f"DELETE FROM {t}")
        c.execute("UPDATE r2_companies SET value=start_value"); cash = int(D.get(c, "r2_cash")); ids = participants(c); top = None
        try:
            rs = json.loads(D.get(c, "r1_results") or "[]"); top = next((r["id"] for r in rs if r.get("rank") == 1 and r["id"] in ids), None)
        except Exception: pass
        for tid in ids: c.execute("INSERT INTO r2_accounts(team_id,cash,start_cash,swaps_total) VALUES(?,?,?,?)", (tid, cash, cash, 2 if tid == top else 1))
        lots = []
        for co in comps(c):
            c.execute("INSERT INTO r2_stakes VALUES('MARKET',?,10000,0)", (co["symbol"],))
            c.execute("INSERT INTO r2_values(symbol,rnd,ts,value,cause) VALUES(?,?,?,?,?)", (co["symbol"], 0, time.time(), co["value"], "Opening valuation"))
            lots += [co["symbol"]] * int(D.get(c, "lots_per_co"))
        random.Random(42).shuffle(lots)
        for sym in lots: c.execute("INSERT INTO r2_auctions(rnd,kind,seller,symbol,bp,status) VALUES(0,'prelim','MARKET',?,?,'queued')", (sym, int(D.get(c, "lot_bp"))))
        if not c.execute("SELECT 1 FROM r2_news").fetchone(): gen_news(c)
        D.put(c, "r2_round", 0); feed(c, "ROUND 2 – Industry Titans begins. Every team starts with " + fmt_inr(cash), 0)
        if top: feed(c, f"{tname(c, top)} finished #1 in Round 1 and receives 2 swaps for Round 2 (all other teams: 1 swap)", 0)
def start_round(c, rnd, now):
    with tx(c):
        D.put(c, "r2_round", rnd); D.put(c, f"nl_closed_{rnd}", "0")
        if rnd == 0: 
            # 10-second gap before the 1st company auction in prelim/round start
            feed(c, "PRELIMINARY AUCTION open – initial setup delay 10s. Each company is auctioned as a 100% stake; every team must end with at least one industry", 0)
            return
        apply_future(c, rnd - 1)                                       # hints from the previous newsletter now move prices
        ids = [r["team_id"] for r in c.execute("SELECT team_id FROM r2_accounts")]; random.shuffle(ids)
        for i, t in enumerate(ids): c.execute("INSERT INTO r2_windows(rnd,team_id,ord,status) VALUES(?,?,?,'pending')", (rnd, t, i))
        feed(c, f"AUCTION ROUND {rnd} begins – newsletter first, then discussion, then the live auction", rnd)
def remove_team(c, tid):
    """Used when an organiser deletes a team during/after Round 2."""
    with tx(c):
        a = active_auction(c)
        if a and tid in (a["seller"], a["high_team"]): cancel(c, a, time.time(), "team removed")
        for s in c.execute("SELECT * FROM r2_stakes WHERE team_id=?", (tid,)).fetchall():
            c.execute("INSERT INTO r2_stakes VALUES('MARKET',?,?,0) ON CONFLICT(team_id,symbol) DO UPDATE SET bp=bp+excluded.bp", (s["symbol"], s["bp"]))
        for t in ("r2_stakes", "r2_accounts", "r2_windows", "r2_loans"): c.execute(f"DELETE FROM {t} WHERE team_id=?", (tid,))
        c.execute("UPDATE r2_swaps SET status='expired',note='team removed' WHERE (proposer=? OR receiver=?) AND status='pending'", (tid, tid))
# ---------------- prices & news ----------------
def apply_news(c, row, frac, rnd):
    imp = json.loads(row["impacts"]); frac = min(frac, 1 - row["applied"])
    if frac <= 0: return
    for sym, pct in imp.items():
        v = c.execute("SELECT value FROM r2_companies WHERE symbol=?", (sym,)).fetchone()
        if not v: continue
        nv = max(1_000_000, int(round(v["value"] * (1 + pct * frac))))
        c.execute("UPDATE r2_companies SET value=? WHERE symbol=?", (nv, sym))
        c.execute("INSERT INTO r2_values(symbol,rnd,ts,value,cause) VALUES(?,?,?,?,?)", (sym, rnd, time.time(), nv, row["headline"][:120]))
    c.execute("UPDATE r2_news SET applied=applied+? WHERE id=?", (frac, row["id"]))
def apply_future(c, rnd):
    """Future-based news of auction round `rnd` take effect on prices when the NEXT round starts (or at the final settlement after Round 3)."""
    if rnd < 1: return
    rows = c.execute("SELECT * FROM r2_news WHERE rnd=? AND kind='future' AND released=1 AND applied<1", (rnd,)).fetchall()
    for r in rows: apply_news(c, r, 1 - r["applied"], rnd + 1 if rnd < 3 else rnd)
    if rows:
        names = []
        for r in rows:
            v = json.loads(r["impacts"]).get(r["symbol"], 0); co = c.execute("SELECT name FROM r2_companies WHERE symbol=?", (r["symbol"],)).fetchone()
            names.append(f"{co['name'] if co else r['symbol']} {'▲' if v > 0 else '▼'}")
        feed(c, f"🔮 The outlook items of Auction Round {rnd} have played out – valuations updated: " + ", ".join(names), rnd + 1 if rnd < 3 else rnd)
def release_news(c, row, now):
    with tx(c):
        c.execute("UPDATE r2_news SET released=1,released_at=? WHERE id=?", (time.time(), row["id"]))
        row = c.execute("SELECT * FROM r2_news WHERE id=?", (row["id"],)).fetchone()
        if row["kind"] == "now": apply_news(c, row, 1.0, row["rnd"])        # present news re-prices the company/industry immediately
        feed(c, ("📰 BUSINESS REPORT: " if row["kind"] == "now" else "🔮 OUTLOOK RUMOR: ") + row["headline"], row["rnd"])
def release_due(c, rnd, rel):
    if D.get(c, "newsletter_on") != "1": return False
    ch = False; rows = c.execute("SELECT * FROM r2_news WHERE rnd=? AND released=0 ORDER BY ord", (rnd,)).fetchall()
    n = c.execute("SELECT COUNT(*) FROM r2_news WHERE rnd=?", (rnd,)).fetchone()[0]; step = float(D.get(c, "news_sec")) * 0.8 / max(1, n)
    for r in rows:
        if rel >= r["ord"] * step: release_news(c, r, rel); ch = True
    return ch

# ---------------- private news generator for discussion time ----------------
def generate_private_news(c, rnd):
    """Generates 2 unique private news items for each team during discussion time:
       - News 1: Depends on another team's company (opposition company rumor)
       - News 2: Own company insider news or another opposition company hint.
       Stored temporarily or returned per team."""
    teams = [r["team_id"] for r in c.execute("SELECT team_id FROM r2_accounts").fetchall()]
    comps_list = comps(c)
    private_store = {}
    for team in teams:
        # Get companies owned by this team vs other teams
        other_teams = [t for t in teams if t != team]
        if not other_teams: continue
        t1 = random.choice(other_teams)
        t1_stakes = c.execute("SELECT symbol FROM r2_stakes WHERE team_id=? AND bp>0", (t1,)).fetchall()
        my_stakes = c.execute("SELECT symbol FROM r2_stakes WHERE team_id=? AND bp>0", (team,)).fetchall()
        
        target_sym1 = t1_stakes[0]["symbol"] if t1_stakes else random.choice(comps_list)["symbol"]
        target_sym2 = (my_stakes[0]["symbol"] if my_stakes and random.random() > 0.5 else (t1_stakes[0]["symbol"] if t1_stakes else target_sym1))
        
        co1 = c.execute("SELECT name FROM r2_companies WHERE symbol=?", (target_sym1,)).fetchone()
        co2 = c.execute("SELECT name FROM r2_companies WHERE symbol=?", (target_sym2,)).fetchone()
        
        n1 = f"CONFIDENTIAL RUMOR: Insider sources suggest {co1['name'] if co1 else target_sym1} is restructuring operations."
        n2 = f"PROPRIETARY BRIEF: Market intelligence indicates potential supply shifts affecting {co2['name'] if co2 else target_sym2}."
        private_store[team] = [n1, n2]
    return private_store

# ---------------- auction core ----------------
def active_auction(c): return c.execute("SELECT * FROM r2_auctions WHERE status IN ('open','countdown') ORDER BY id LIMIT 1").fetchone()
def inc(high): return max(10000, int(high * 0.02))
def min_bid(a): return a["ask"] if not a["high_bid"] else a["high_bid"] + inc(a["high_bid"])
def value_of(c, sym): return c.execute("SELECT value FROM r2_companies WHERE symbol=?", (sym,)).fetchone()["value"]
def _escrow(c, owner, sym, bp):
    s = c.execute("SELECT * FROM r2_stakes WHERE team_id=? AND symbol=?", (owner, sym)).fetchone()
    if not s or s["bp"] < bp or bp <= 0: raise R2Error("Not enough stake available")
    cost = s["cost"] * bp // s["bp"]
    if s["bp"] == bp: c.execute("DELETE FROM r2_stakes WHERE team_id=? AND symbol=?", (owner, sym))
    else: c.execute("UPDATE r2_stakes SET bp=bp-?,cost=cost-? WHERE team_id=? AND symbol=?", (bp, cost, owner, sym))
    return cost
def _give(c, owner, sym, bp, cost):
    c.execute("INSERT INTO r2_stakes VALUES(?,?,?,?) ON CONFLICT(team_id,symbol) DO UPDATE SET bp=bp+excluded.bp,cost=cost+excluded.cost", (owner, sym, bp, cost))
def _close_window(c, a): c.execute("UPDATE r2_windows SET status='done' WHERE rnd=? AND team_id=? AND status='offered'", (a["rnd"], a["seller"]))
def open_lot(c, now):
    a = c.execute("SELECT * FROM r2_auctions WHERE status='queued' ORDER BY id LIMIT 1").fetchone()
    if not a: return False
    with tx(c):
        cost = _escrow(c, "MARKET", a["symbol"], a["bp"]); ask = int(round(value_of(c, a["symbol"]) * a["bp"] / 10000 * 0.9, -3))
        c.execute("UPDATE r2_auctions SET status='open',cost=?,ask=?,opened=?,expires=? WHERE id=?", (cost, ask, now, now + float(D.get(c, "open_sec")), a["id"]))
        co = c.execute("SELECT name,industry FROM r2_companies WHERE symbol=?", (a["symbol"],)).fetchone()
        feed(c, f"Market offers {a['bp']/100:g}% of {co['name']} ({co['industry']}) – opening bid {fmt_inr(ask)}", 0)
    return True
def sell(c, team, sym, pct, ask, now):
    with tx(c):
        w = c.execute("SELECT * FROM r2_windows WHERE team_id=? AND status='active'", (team,)).fetchone()
        if not w: raise R2Error("It is not your selling session")
        if active_auction(c): raise R2Error("An auction is already live")
        bp = int(round(float(pct) * 100)); ask = int(ask)
        if bp < 500 or bp > 10000 or bp % 500: raise R2Error("Stakes are traded only in 5% steps: 5%, 10%, 15% … 100%")
        if ask < 10000: raise R2Error("Starting price must be at least ₹10,000")
        if not c.execute("SELECT 1 FROM r2_companies WHERE symbol=?", (sym,)).fetchone(): raise R2Error("Unknown company")
        if ask > 5 * value_of(c, sym) * bp // 10000 + 10000: raise R2Error("Starting price is unrealistically high")
        cost = _escrow(c, team, sym, bp)
        c.execute("INSERT INTO r2_auctions(rnd,kind,seller,symbol,bp,cost,ask,status,opened,expires) VALUES(?,?,?,?,?,?,?,'open',?,?)", (w["rnd"], "sell", team, sym, bp, cost, ask, now, now + float(D.get(c, "open_sec"))))
        c.execute("UPDATE r2_windows SET status='offered' WHERE id=?", (w["id"],))
        co = c.execute("SELECT name,industry FROM r2_companies WHERE symbol=?", (sym,)).fetchone()
        feed(c, f"{tname(c, team)} offered {bp/100:g}% of {co['name']} ({co['industry']}) – starting at {fmt_inr(ask)}", w["rnd"])
def pass_window(c, team, now, reason="passed"):
    with tx(c):
        w = c.execute("SELECT * FROM r2_windows WHERE team_id=? AND status='active'", (team,)).fetchone()
        if not w: raise R2Error("It is not your selling session")
        c.execute("UPDATE r2_windows SET status='passed' WHERE id=?", (w["id"],)); feed(c, f"{tname(c, team)} {reason} their selling session", w["rnd"])
def teams_without_stake(c): return c.execute("SELECT COUNT(*) FROM r2_accounts a WHERE NOT EXISTS (SELECT 1 FROM r2_stakes s WHERE s.team_id=a.team_id AND s.bp>0)").fetchone()[0]
def place_bid(c, team, aid, amount, now):
    with tx(c):
        a = c.execute("SELECT * FROM r2_auctions WHERE id=?", (aid,)).fetchone()
        acc = c.execute("SELECT cash FROM r2_accounts WHERE team_id=?", (team,)).fetchone()
        if not acc: raise R2Error("Your team is not part of Round 2")
        if not a or a["status"] not in ("open", "countdown"): raise R2Error("This auction is closed")
        if team == a["seller"]: raise R2Error("You cannot bid on your own offer")
        if team == a["high_team"]: raise R2Error("You are already the highest bidder")
        if isinstance(amount, bool) or amount is None or float(amount) != int(float(amount)): raise R2Error("Bid must be a whole rupee amount")
        amount = int(float(amount))
        if amount < min_bid(a): raise R2Error(f"Minimum bid is {fmt_inr(min_bid(a))}")
        if amount > acc["cash"]:
            room = borrow_room(c, team, a["rnd"]) if a["rnd"] >= 1 else 0
            raise R2Error(f"Insufficient capital – you have {fmt_inr(acc['cash'])}" + (f". You can borrow up to {fmt_inr(room)} more in this auction round or propose a swap" if room > 0 else ""))
        if a["kind"] == "prelim":                                   # every team must own at least one industry after the preliminary auction
            owns = c.execute("SELECT 1 FROM r2_stakes WHERE team_id=? AND bp>0", (team,)).fetchone()
            queued = c.execute("SELECT COUNT(*) FROM r2_auctions WHERE status='queued'").fetchone()[0]
            if owns and queued < teams_without_stake(c): raise R2Error("Other teams still need their first company – let them win the remaining lots")
        c.execute("UPDATE r2_auctions SET high_bid=?,high_team=?,status='countdown',cd_end=? WHERE id=?", (amount, team, now + 10, aid))
        c.execute("INSERT INTO r2_bids(auction_id,team_id,amount,ts) VALUES(?,?,?,?)", (aid, team, amount, now))
        feed(c, f"{tname(c, team)} bid {fmt_inr(amount)}. {'10-second countdown started.' if a['status']=='open' else 'Countdown reset to 10 seconds.'}", a["rnd"]); SOUNDS.append("bid")
def lapse(c, a, now, why="No bids received"):
    with tx(c):
        _give(c, a["seller"], a["symbol"], a["bp"], a["cost"])
        c.execute("UPDATE r2_auctions SET status='lapsed',closed=?,note=? WHERE id=?", (now, why, a["id"])); _close_window(c, a)
        feed(c, f"Offer lapsed – {why.lower()}. Stake returned to {tname(c, a['seller'])}.", a["rnd"])
        if a["kind"] == "prelim" and a["seller"] == "MARKET":          # an unsold promoter lot is re-offered (always while some team still has no company, otherwise once)
            tries = c.execute("SELECT COUNT(*) FROM r2_auctions WHERE rnd=0 AND kind='prelim' AND symbol=?", (a["symbol"],)).fetchone()[0]
            if teams_without_stake(c) > 0 or tries < 2: c.execute("INSERT INTO r2_auctions(rnd,kind,seller,symbol,bp,status) VALUES(0,'prelim','MARKET',?,?,'queued')", (a["symbol"], a["bp"]))
def cancel(c, a, now, why="Cancelled by organiser"):
    with tx(c):
        _give(c, a["seller"], a["symbol"], a["bp"], a["cost"])
        c.execute("UPDATE r2_auctions SET status='cancelled',closed=?,note=? WHERE id=?", (now, why, a["id"])); _close_window(c, a)
        feed(c, f"Auction cancelled ({why}). Stake returned to {tname(c, a['seller'])}.", a["rnd"])
def award(c, a, now):
    with tx(c):
        buyer, price = a["high_team"], a["high_bid"]
        acc = c.execute("SELECT cash FROM r2_accounts WHERE team_id=?", (buyer,)).fetchone()
        if a["status"] in ("sold", "cancelled", "lapsed") or not acc or acc["cash"] < price: return cancel(c, a, now, "buyer could not settle")
        r = c.execute("UPDATE r2_accounts SET cash=cash-? WHERE team_id=? AND cash>=?", (price, buyer, price))
        if r.rowcount != 1: return cancel(c, a, now, "buyer could not settle")                     # never let capital go negative / double-spend
        if a["seller"] != "MARKET": c.execute("UPDATE r2_accounts SET cash=cash+? WHERE team_id=?", (price, a["seller"]))
        _give(c, buyer, a["symbol"], a["bp"], price)
        c.execute("UPDATE r2_auctions SET status='sold',closed=?,price=?,winner=? WHERE id=?", (now, price, buyer, a["id"])); _close_window(c, a)
        co = c.execute("SELECT name FROM r2_companies WHERE symbol=?", (a["symbol"],)).fetchone()
        feed(c, f"SOLD! {a['bp']/100:g}% of {co['name']} to {tname(c, buyer)} for {fmt_inr(price)} (seller: {tname(c, a['seller'])})", a["rnd"])
        audit(c, "r2_award", dict(auction=a["id"], seller=a["seller"], buyer=buyer, symbol=a["symbol"], bp=a["bp"], price=price)); SOUNDS.append("win")
def force_complete(c, now):
    a = active_auction(c)
    if not a: raise R2Error("No live auction")
    # BUG FIX: If no team has placed a bid, do NOT randomly assign the company to any team. Simply lapse/cancel the auction and return it to market or keep unsold.
    if a["high_bid"] is None or a["high_team"] is None:
        lapse(c, a, now, "Force completed by organizer - Unsold / Unbidded")
    else:
        award(c, a, now)

def auction_tick(c, now, rnd):
    a = active_auction(c)
    if a:
        if a["status"] == "countdown" and now >= a["cd_end"]: award(c, a, now)
        elif a["status"] == "open" and now >= a["expires"]: lapse(c, a, now)
        else: return False
        auction_tick(c, now, rnd); return True        # roll straight on to the next lot / selling session
    if rnd == 0: return open_lot(c, now)
    ch = False
    w = c.execute("SELECT * FROM r2_windows WHERE rnd=? AND status='active'", (rnd,)).fetchone()
    if w:
        if now >= w["deadline"]: pass_window(c, w["team_id"], now, "ran out of time in"); ch = True
        else: return False
    if c.execute("SELECT 1 FROM r2_windows WHERE rnd=? AND status='offered'", (rnd,)).fetchone(): return ch
    for w in c.execute("SELECT * FROM r2_windows WHERE rnd=? AND status='pending' ORDER BY ord", (rnd,)).fetchall():
        has = c.execute("SELECT COALESCE(SUM(bp),0) FROM r2_stakes WHERE team_id=?", (w["team_id"],)).fetchone()[0]
        with tx(c):
            if has <= 0: c.execute("UPDATE r2_windows SET status='passed' WHERE id=?", (w["id"],)); feed(c, f"{tname(c, w['team_id'])} has no stake to sell – selling session skipped", rnd); ch = True; continue
            c.execute("UPDATE r2_windows SET status='active',deadline=? WHERE id=?", (now + float(D.get(c, "window_sec")), w["id"]))
            feed(c, f"{tname(c, w['team_id'])} – YOUR SELLING SESSION (sell or swap)", rnd)
        return True
    return ch
def round_done(c, rnd):
    if active_auction(c): return False
    if rnd == 0:
        if c.execute("SELECT 1 FROM r2_auctions WHERE rnd=0 AND status IN ('queued','open','countdown')").fetchone(): return False
        return c.execute("SELECT COUNT(*) FROM r2_accounts").fetchone()[0] > 0 and teams_without_stake(c) == 0
    n = c.execute("SELECT COUNT(*) FROM r2_windows WHERE rnd=?", (rnd,)).fetchone()[0]
    if n == 0 or c.execute("SELECT 1 FROM r2_windows WHERE rnd=? AND status IN ('pending','active','offered')", (rnd,)).fetchone(): return False
    if c.execute("SELECT 1 FROM r2_swaps WHERE rnd=? AND status='pending'", (rnd,)).fetchone(): return False
    return c.execute("SELECT COUNT(*) FROM r2_finish WHERE rnd=?", (rnd,)).fetchone()[0] >= c.execute("SELECT COUNT(*) FROM r2_accounts").fetchone()[0]
def round_done_sessions(c, rnd):
    n = c.execute("SELECT COUNT(*) FROM r2_windows WHERE rnd=?", (rnd,)).fetchone()[0]
    return n > 0 and not c.execute("SELECT 1 FROM r2_windows WHERE rnd=? AND status IN ('pending','active','offered')", (rnd,)).fetchone() and not active_auction(c)
def finish_round(c, team, rnd, now):
    with tx(c):
        if rnd < 1: raise R2Error("Only in Auction Rounds 1-3")
        if not c.execute("SELECT 1 FROM r2_accounts WHERE team_id=?", (team,)).fetchone(): raise R2Error("Your team is not part of Round 2")
        if c.execute("SELECT 1 FROM r2_windows WHERE rnd=? AND team_id=? AND status IN ('pending','active','offered')", (rnd, team)).fetchone(): raise R2Error("Finish your selling session first")
        if c.execute("SELECT 1 FROM r2_swaps WHERE rnd=? AND proposer=? AND status='pending'", (rnd, team)).fetchone(): raise R2Error("You still have a pending swap proposal – wait for the answer or withdraw it")
        c.execute("INSERT OR IGNORE INTO r2_finish(rnd,team_id,ts) VALUES(?,?,?)", (rnd, team, now)); feed(c, f"{tname(c, team)} is ready to finish the round", rnd)
def ensure_first_stakes(c, now):
    """Safety net when the preliminary auction closes: a team that still owns nothing receives the cheapest unsold company at its opening price (if it can pay)."""
    with tx(c):
        for r in c.execute("SELECT team_id FROM r2_accounts a WHERE NOT EXISTS (SELECT 1 FROM r2_stakes s WHERE s.team_id=a.team_id AND s.bp>0)").fetchall():
            for co in c.execute("SELECT k.symbol,k.value,k.name FROM r2_companies k JOIN r2_stakes s ON s.symbol=k.symbol AND s.team_id='MARKET' AND s.bp>=10000 ORDER BY k.value").fetchall():
                price = int(round(co["value"] * 0.9, -3)); acc = c.execute("SELECT cash FROM r2_accounts WHERE team_id=?", (r["team_id"],)).fetchone()
                if acc["cash"] < price: continue
                cost = _escrow(c, "MARKET", co["symbol"], 10000); c.execute("UPDATE r2_accounts SET cash=cash-? WHERE team_id=? AND cash>=?", (price, r["team_id"], price)); _give(c, r["team_id"], co["symbol"], 10000, price)
                c.execute("INSERT INTO r2_auctions(rnd,kind,seller,symbol,bp,cost,ask,status,high_bid,high_team,opened,closed,price,winner,note) VALUES(0,'prelim','MARKET',?,10000,?,?,'sold',?,?,?,?,?,?,?)",
                          (co["symbol"], cost, price, price, r["team_id"], now, now, price, r["team_id"], "allocated at close so every team owns a company"))
                feed(c, f"{tname(c, r['team_id'])} was allocated 100% of {co['name']} at {fmt_inr(price)} so that every team owns an industry", 0); break
# ---------------- cash capacity & borrowing ----------------
def committed(c, tid):
    a = active_auction(c); return int(a["high_bid"]) if a and a["high_team"] == tid else 0
def capacity(c, tid):
    r = c.execute("SELECT cash FROM r2_accounts WHERE team_id=?", (tid,)).fetchone(); return int(r["cash"]) - committed(c, tid) if r else 0
def _num(name): 
    def f(c): return float(D.get(c, name) or DEFAULTS[name])
    return f
DEFAULTS = dict(borrow_limit=3_000_000, borrow_fee_pct=5, borrow_pen=300_000, swap_ttl=180)
borrow_limit, borrow_fee_pct, borrow_pen_unit, swap_ttl = _num("borrow_limit"), _num("borrow_fee_pct"), _num("borrow_pen"), _num("swap_ttl")
def drawn(c, tid, rnd): return int(c.execute("SELECT COALESCE(SUM(amount),0) FROM r2_loans WHERE team_id=? AND rnd=? AND kind='borrow'", (tid, rnd)).fetchone()[0])
def borrow_room(c, tid, rnd): return max(0, int(borrow_limit(c)) - drawn(c, tid, rnd))
def borrow_penalty(c, borrowed): return round(min(30.0, max(0, borrowed) / max(1.0, borrow_pen_unit(c))), 2)
def _whole(x, what):
    if x is None or isinstance(x, bool) or x == "": raise R2Error(f"{what} must be a number")
    try: f = float(x)
    except (TypeError, ValueError): raise R2Error(f"{what} must be a number")
    if f != int(f): raise R2Error(f"{what} must be a whole rupee amount")
    return int(f)
def borrow(c, team, amount, rnd, now):
    with tx(c):
        if rnd < 1: raise R2Error("Borrowing is available during Auction Rounds 1-3")
        acc = c.execute("SELECT * FROM r2_accounts WHERE team_id=?", (team,)).fetchone()
        if not acc: raise R2Error("Your team is not part of Round 2")
        amount = _whole(amount, "Borrow amount")
        if amount < 10_000 or amount % 10_000: raise R2Error("Borrow in multiples of ₹10,000 (minimum ₹10,000)")
        room = borrow_room(c, team, rnd)
        if amount > room: raise R2Error(f"Borrowing limit: you can borrow at most {fmt_inr(room)} more in this auction round (limit {fmt_inr(borrow_limit(c))} per round)")
        fee = int(round(amount * borrow_fee_pct(c) / 100))
        r = c.execute("UPDATE r2_accounts SET cash=cash+?,borrowed=borrowed+?,fees=fees+? WHERE team_id=?", (amount - fee, amount, fee, team))
        if r.rowcount != 1: raise R2Error("Could not record the loan")
        out = int(c.execute("SELECT borrowed FROM r2_accounts WHERE team_id=?", (team,)).fetchone()[0])
        c.execute("INSERT INTO r2_loans(team_id,rnd,kind,amount,fee,ts,outstanding) VALUES(?,?,?,?,?,?,?)", (team, rnd, "borrow", amount, fee, now, out))
        feed(c, f"{tname(c, team)} borrowed {fmt_inr(amount)} (fee {fmt_inr(fee)}) – outstanding borrowing {fmt_inr(out)}", rnd)
        return dict(amount=amount, fee=fee, outstanding=out, room=borrow_room(c, team, rnd))
def repay(c, team, amount, rnd, now):
    with tx(c):
        if rnd < 1: raise R2Error("Repayment is available during Auction Rounds 1-3")
        acc = c.execute("SELECT * FROM r2_accounts WHERE team_id=?", (team,)).fetchone()
        if not acc: raise R2Error("Your team is not part of Round 2")
        amount = _whole(amount, "Repay amount")
        if amount <= 0: raise R2Error("Repay amount must be positive")
        if amount > acc["borrowed"]: raise R2Error(f"You only owe {fmt_inr(acc['borrowed'])}")
        if amount > capacity(c, team): raise R2Error(f"Not enough free cash – you have {fmt_inr(capacity(c, team))} available (cash promised in a live bid cannot be repaid)")
        r = c.execute("UPDATE r2_accounts SET cash=cash-?,borrowed=borrowed-? WHERE team_id=? AND cash>=? AND borrowed>=?", (amount, amount, team, amount, amount))
        if r.rowcount != 1: raise R2Error("Could not record the repayment")
        out = int(c.execute("SELECT borrowed FROM r2_accounts WHERE team_id=?", (team,)).fetchone()[0])
        c.execute("INSERT INTO r2_loans(team_id,rnd,kind,amount,fee,ts,outstanding) VALUES(?,?,?,?,?,?,?)", (team, rnd, "repay", amount, 0, now, out))
        feed(c, f"{tname(c, team)} repaid {fmt_inr(amount)} – outstanding borrowing {fmt_inr(out)}", rnd)
        return dict(amount=amount, outstanding=out)
# ---------------- swaps ----------------
def swaps_total(c, team): r = c.execute("SELECT swaps_total FROM r2_accounts WHERE team_id=?", (team,)).fetchone(); return int(r["swaps_total"] or 1) if r else 0
def swaps_left(c, team): return max(0, swaps_total(c, team) - c.execute("SELECT COUNT(*) FROM r2_swaps WHERE proposer=? AND status='accepted'", (team,)).fetchone()[0])
def _stake(c, t, s): return c.execute("SELECT * FROM r2_stakes WHERE team_id=? AND symbol=?", (t, s)).fetchone()
def cname(c, sym): r = c.execute("SELECT name FROM r2_companies WHERE symbol=?", (sym,)).fetchone(); return r["name"] if r else str(sym)
def _bp5(x):
    if x is None or isinstance(x, bool) or x == "": raise R2Error("Enter the stake percentages for both sides of the swap")
    try: f = float(x)
    except (TypeError, ValueError): raise R2Error("Stake percentage must be a number")
    bp = int(round(f * 100))
    if abs(f * 100 - bp) > 1e-6 or bp < 500 or bp > 10000 or bp % 500: raise R2Error("Swaps are made in 5% steps: 5%, 10%, 15% … 100%")
    return bp
def _swap_problem(c, s):
    p, r = s["proposer"], s["receiver"]
    if not c.execute("SELECT 1 FROM r2_accounts WHERE team_id=?", (p,)).fetchone() or not c.execute("SELECT 1 FROM r2_accounts WHERE team_id=?", (r,)).fetchone(): return "A team is no longer part of Round 2"
    if s["give_sym"] == s["get_sym"]: return "A swap must exchange two different companies"
    if swaps_left(c, p) <= 0: return f"{tname(c, p)} has no swaps left"
    a, b = _stake(c, p, s["give_sym"]), _stake(c, r, s["get_sym"])
    if not a or a["bp"] < s["give_bp"]: return f"{tname(c, p)} no longer holds {s['give_bp']/100:g}% of {cname(c, s['give_sym'])}"
    if not b or b["bp"] < s["get_bp"]: return f"{tname(c, r)} no longer holds {s['get_bp']/100:g}% of {cname(c, s['get_sym'])}"
    cash = int(s["cash"] or 0)
    if cash:
        payer = p if cash > 0 else r
        if capacity(c, payer) < abs(cash): return f"{tname(c, payer)} does not have enough free cash for the {fmt_inr(abs(cash))} cash adjustment"
    return None
def swap_propose(c, team, receiver, give_sym, give_pct, get_sym, get_pct, cash, now, rnd):
    with tx(c):
        if rnd < 1: raise R2Error("Swaps are available during Auction Rounds 1-3")
        if not c.execute("SELECT 1 FROM r2_accounts WHERE team_id=?", (team,)).fetchone(): raise R2Error("Your team is not part of Round 2")
        if not receiver or team == receiver or not c.execute("SELECT 1 FROM r2_accounts WHERE team_id=?", (receiver,)).fetchone(): raise R2Error("Choose another participating team")
        if not give_sym or not get_sym or not c.execute("SELECT 1 FROM r2_companies WHERE symbol=?", (give_sym,)).fetchone() or not c.execute("SELECT 1 FROM r2_companies WHERE symbol=?", (get_sym,)).fetchone(): raise R2Error("Choose the two companies to exchange")
        if give_sym == get_sym: raise R2Error("A swap must exchange two different companies")
        gb, rb = _bp5(give_pct), _bp5(get_pct); cash = _whole(cash if cash not in (None, "") else 0, "Cash adjustment")
        if abs(cash) > 1_000_000_000: raise R2Error("Cash adjustment is out of range")
        if swaps_left(c, team) <= 0: raise R2Error("You have no swaps left")
        if c.execute("SELECT 1 FROM r2_swaps WHERE proposer=? AND status='pending'", (team,)).fetchone(): raise R2Error("You already have a pending swap proposal")
        a, b = _stake(c, team, give_sym), _stake(c, receiver, get_sym)
        if not a or a["bp"] < gb: raise R2Error("You do not hold that much of the stake you are offering")
        if not b or b["bp"] < rb: raise R2Error("The other team does not hold that much of the requested stake")
        if cash > 0 and capacity(c, team) < cash: raise R2Error("You do not have enough free cash for the adjustment")
        if cash < 0 and capacity(c, receiver) < -cash: raise R2Error("The other team does not have enough free cash")
        cur = c.execute("INSERT INTO r2_swaps(rnd,proposer,receiver,give_sym,give_bp,get_sym,get_bp,status,created,cash,expires) VALUES(?,?,?,?,?,?,?,'pending',?,?,?)", (rnd, team, receiver, give_sym, gb, get_sym, rb, now, cash, now + swap_ttl(c)))
        feed(c, f"SWAP PROPOSAL: {tname(c, team)} offers {gb/100:g}% {cname(c, give_sym)} for {rb/100:g}% {cname(c, get_sym)} of {tname(c, receiver)}", rnd)
        return cur.lastrowid
def swap_respond(c, team, sid, accept, now, rnd):
    with tx(c):
        s = c.execute("SELECT * FROM r2_swaps WHERE id=?", (sid,)).fetchone()
        if not s or s["status"] != "pending" or s["receiver"] != team: raise R2Error("No such pending proposal for your team")
        def close(status, msg):
            c.execute("UPDATE r2_swaps SET status=?,resolved=?,note=? WHERE id=? AND status='pending'", (status, now, msg, sid))
            feed(c, f"Swap proposal {status}" + (f" – {msg}" if msg else ""), s["rnd"]); return dict(ok=status == "rejected", status=status, message=msg)
        if s["rnd"] != rnd: return close("expired", "the auction round ended")
        if s["expires"] is not None and now >= s["expires"]: return close("expired", "time limit reached")
        if not accept: c.execute("UPDATE r2_swaps SET status='rejected',resolved=? WHERE id=? AND status='pending'", (now, sid)); feed(c, f"{tname(c, team)} REJECTED the swap", s["rnd"]); return dict(ok=True, status="rejected", message="")
        why = _swap_problem(c, s)
        if why: return close("expired", why)
        p, cash = s["proposer"], int(s["cash"] or 0)
        ca = _escrow(c, p, s["give_sym"], s["give_bp"]); cb = _escrow(c, team, s["get_sym"], s["get_bp"])
        _give(c, team, s["give_sym"], s["give_bp"], ca + max(0, -cash)); _give(c, p, s["get_sym"], s["get_bp"], cb + max(0, cash))
        if cash:
            payer, payee = (p, team) if cash > 0 else (team, p); amt = abs(cash)
            if c.execute("UPDATE r2_accounts SET cash=cash-? WHERE team_id=? AND cash>=?", (amt, payer, amt)).rowcount != 1: raise R2Error("Cash adjustment failed")
            c.execute("UPDATE r2_accounts SET cash=cash+? WHERE team_id=?", (amt, payee))
        c.execute("UPDATE r2_swaps SET status='accepted',resolved=? WHERE id=? AND status='pending'", (now, sid))
        feed(c, f"SWAP COMPLETED successfully between {tname(c, p)} and {tname(c, team)}", s["rnd"]); SOUNDS.append("win")
        return dict(ok=True, status="accepted", message="")
def swap_cancel(c, team, sid, now):
    with tx(c):
        s = c.execute("SELECT * FROM r2_swaps WHERE id=?", (sid,)).fetchone()
        if not s or s["proposer"] != team or s["status"] != "pending": raise R2Error("No pending proposal")
        c.execute("UPDATE r2_swaps SET status='cancelled',resolved=?,note='withdrawn' WHERE id=? AND status='pending'", (now, sid)); feed(c, f"{tname(c, team)} withdrew swap proposal", s["rnd"])
def expire_swaps(c, now):
    rows = c.execute("SELECT * FROM r2_swaps WHERE status='pending' AND expires IS NOT NULL AND expires<=?", (now,)).fetchall()
    for s in rows:
        with tx(c):
            c.execute("UPDATE r2_swaps SET status='expired',resolved=?,note='time limit' WHERE id=? AND status='pending'", (now, s["id"])); feed(c, f"Swap proposal expired", s["rnd"])
    return bool(rows)
# ---------------- round lifecycle ----------------
def close_round(c, rnd, now):
    with tx(c):
        a = active_auction(c)
        if a: award(c, a, now) if a["high_bid"] else lapse(c, a, now, "Round closed")
        c.execute("UPDATE r2_windows SET status='expired' WHERE rnd=? AND status IN ('pending','active')", (rnd,))
        c.execute("UPDATE r2_swaps SET status='expired',resolved=? WHERE rnd=? AND status='pending'", (now, rnd))
        if rnd == 0: ensure_first_stakes(c, now)
        if rnd >= 1:
            for r in c.execute("SELECT * FROM r2_news WHERE rnd=? AND kind='now' AND released=1 AND applied<1", (rnd,)).fetchall(): apply_news(c, r, 1 - r["applied"], rnd)
            if rnd == 3: apply_future(c, 3)
        lb = leaderboard(c); c.execute("INSERT OR REPLACE INTO r2_results VALUES(?,?)", (rnd, json.dumps(lb)))
        feed(c, ("Preliminary auction" if rnd == 0 else f"Auction Round {rnd}") + " closed – valuations updated, results frozen", rnd)
def tick(c, now, stage, start):
    rnd = flow.ROUND_OF[stage]; rel = now - start; ph = flow.phase(c, stage, rel); ch = False
    if rnd >= 1:
        if ph == "newsletter": ch |= release_due(c, rnd, rel)
        elif D.get(c, f"nl_closed_{rnd}") != "1":
            D.put(c, f"nl_closed_{rnd}", "1")
            if D.get(c, "newsletter_on") == "1":
                for r in c.execute("SELECT * FROM r2_news WHERE rnd=? AND released=0 ORDER BY ord", (rnd,)).fetchall(): release_news(c, r, rel); ch = True
        ch |= expire_swaps(c, now)
    if ph == "auction": ch |= auction_tick(c, now, rnd)
    return ch
# ---------------- valuation & scoring ----------------
def _escrow_rows(c, tid):
    a = active_auction(c)
    if not a or a["seller"] != tid or a["kind"] != "sell": return []
    k = c.execute("SELECT value,industry,name FROM r2_companies WHERE symbol=?", (a["symbol"],)).fetchone()
    return [dict(symbol=a["symbol"], bp=a["bp"], value=k["value"], industry=k["industry"], name=k["name"])] if k else []
def portfolio(c, tid):
    acc = c.execute("SELECT * FROM r2_accounts WHERE team_id=?", (tid,)).fetchone()
    st = c.execute("SELECT s.*,k.value,k.industry,k.name FROM r2_stakes s JOIN r2_companies k ON k.symbol=s.symbol WHERE s.team_id=?", (tid,)).fetchall()
    held = sum(s["bp"] * s["value"] // 10000 for s in st) + sum(e["bp"] * e["value"] // 10000 for e in _escrow_rows(c, tid))
    return acc, st, held, committed(c, tid)
def r1map(c):
    try: return {r["id"]: r["total"] for r in json.loads(D.get(c, "r1_results") or "[]")}
    except Exception: return {}
def scores(c, tid, r1=None):
    acc, st, held, _ = portfolio(c, tid)
    borrowed = int(acc["borrowed"] or 0); value = acc["cash"] + held - borrowed; growth = value / acc["start_cash"] - 1
    cg = 50 * max(0, min(1, (growth + .10) / .30))
    q = lambda sql: c.execute(sql, (tid,)).fetchone()[0]
    bids = q("SELECT COUNT(DISTINCT auction_id) FROM r2_bids WHERE team_id=?"); wins = q("SELECT COUNT(*) FROM r2_auctions WHERE winner=? AND status='sold'")
    offers = q("SELECT COUNT(*) FROM r2_auctions WHERE seller=? AND kind='sell'"); sold = q("SELECT COUNT(*) FROM r2_auctions WHERE seller=? AND kind='sell' AND status='sold'")
    sw_done = q("SELECT COUNT(*) FROM r2_swaps WHERE status='accepted' AND proposer=?"); sw_fail = q("SELECT COUNT(*) FROM r2_swaps WHERE status IN ('rejected','expired') AND proposer=?")
    sw_tot = max(1, int(acc["swaps_total"] or 1))
    part = 20 * min(1, (bids + 2 * wins + 2 * offers) / 12)
    sell_u = sold + .5 * (offers - sold); swap_u = (sw_done + .5 * min(sw_fail, 1)) / sw_tot
    ss = 10 * min(1, sell_u / 3) + 10 * min(1, swap_u)
    byind = {}
    for s_ in list(st) + _escrow_rows(c, tid): byind[s_["industry"]] = byind.get(s_["industry"], 0) + s_["bp"] * s_["value"] // 10000
    n = sum(1 for v in byind.values() if v > 0); share = max(byind.values()) / sum(byind.values()) if byind and sum(byind.values()) else 1
    div = 10 * min(1, n / 5) * (1 if share <= .4 else 1 - (share - .4) / .6 * .5) if n else 0
    parts = dict(growth=round(cg, 2), participation=round(part, 2), swap_sell=round(ss, 2), diversification=round(div, 2))
    pen = borrow_penalty(c, borrowed); r2 = round(max(0.0, sum(parts.values()) - pen), 2); r1 = (r1map(c) if r1 is None else r1).get(tid, 0)
    return dict(total=r2, r2=r2, r1=round(r1, 2), overall=round(r1 + r2, 2), parts=parts, value=value, cash=acc["cash"], growth_pct=round(growth * 100, 2), industries=n, borrowed=borrowed, borrow_penalty=pen,
                stats=dict(bids=bids, wins=wins, offers=offers, sold=sold, swaps=sw_done, swaps_total=sw_tot, swaps_failed=sw_fail))
def leaderboard(c):
    rows = []; m = r1map(c)
    for r in c.execute("SELECT team_id FROM r2_accounts"):
        s = scores(c, r["team_id"], m); rows.append(dict(id=r["team_id"], team=tname(c, r["team_id"]), **s))
    rows.sort(key=lambda r: (-r["overall"], -r["r2"], -r["value"], r["id"]))
    for i, r in enumerate(rows, 1): r["rank"] = rows[i - 2]["rank"] if i > 1 and (r["overall"], r["r2"], r["value"]) == (rows[i - 2]["overall"], rows[i - 2]["r2"], rows[i - 2]["value"]) else i
    return rows
def public_rows(rows): return [dict(rank=r["rank"], id=r["id"], team=r["team"], value=r["value"], growth_pct=r["growth_pct"], r1=r["r1"], r2=r["r2"], overall=r["overall"]) for r in rows]
# ---------------- views ----------------
def public_holdings(c):
    out = {}
    for r in c.execute("SELECT s.team_id,s.symbol,s.bp,k.industry,k.name FROM r2_stakes s JOIN r2_companies k ON k.symbol=s.symbol WHERE s.team_id!='MARKET' ORDER BY s.bp DESC"):
        out.setdefault(r["team_id"], []).append(dict(symbol=r["symbol"], industry=r["industry"], company=r["name"], pct=r["bp"] / 100))
    return out
def news_view(c, organizer):
    q = "SELECT * FROM r2_news" + ("" if organizer else " WHERE released=1") + " ORDER BY rnd DESC, released_at DESC, kind, ord"
    out = []
    for r in c.execute(q):
        d = dict(r)
        if not organizer: d.pop("impacts"); d.pop("applied"); d.pop("tkey")
        out.append(d)
    return out
def state_for(c, role, team_id, now):
    rnd = int(D.get(c, "r2_round", 0)); cs = comps(c)
    first = {r["symbol"]: r["value"] for r in c.execute("SELECT symbol,value FROM r2_values WHERE id IN (SELECT MIN(id) FROM r2_values GROUP BY symbol)")}
    for x in cs: x["change_pct"] = round((x["value"] / x["start_value"] - 1) * 100, 2)
    a = active_auction(c); auc = None
    if a:
        bids = [dict(r) for r in c.execute("SELECT team_id,amount,ts FROM r2_bids WHERE auction_id=? ORDER BY id DESC LIMIT 6", (a["id"],))]
        co = next(x for x in cs if x["symbol"] == a["symbol"]); last = bids[0] if bids else None
        auc = dict(id=a["id"], status=a["status"], seller=a["seller"], seller_name=tname(c, a["seller"]), symbol=a["symbol"], company=co["name"], industry=co["industry"], pct=a["bp"] / 100,
                   ask=a["ask"], high_bid=a["high_bid"], high_team=a["high_team"], high_name=tname(c, a["high_team"]) if a["high_team"] else None, cd_end=a["cd_end"], expires=a["expires"],
                   min_bid=min_bid(a), last_bid=last["amount"] if last else None, last_bid_team=tname(c, last["team_id"]) if last else None, kind=a["kind"], rnd=a["rnd"],
                   fair_value=co["value"] * a["bp"] // 10000, bids=[dict(team=tname(c, b["team_id"]), amount=b["amount"]) for b in bids])
    w = c.execute("SELECT * FROM r2_windows WHERE rnd=? AND status IN ('active','offered') ORDER BY ord LIMIT 1", (rnd,)).fetchone()
    win = dict(team=w["team_id"], name=tname(c, w["team_id"]), status=w["status"], deadline=w["deadline"]) if w else None
    lt = c.execute("SELECT * FROM r2_auctions WHERE status='sold' ORDER BY id DESC LIMIT 1").fetchone()
    latest = dict(symbol=lt["symbol"], pct=lt["bp"] / 100, seller=tname(c, lt["seller"]), buyer=tname(c, lt["winner"]), price=lt["price"]) if lt else None
    out = dict(round=rnd, companies=cs, auction=auc, window=win, latest_tx=latest, holdings=public_holdings(c), leaderboard=(lambda lb: lb if role == "organizer" else public_rows(lb))(leaderboard(c)), feed=[dict(ts=r["ts"], text=r["text"]) for r in c.execute("SELECT ts,text FROM r2_feed ORDER BY id DESC LIMIT 60")],
        teams={r["team_id"]: tname(c, r["team_id"]) for r in c.execute("SELECT team_id FROM r2_accounts")}, news=news_view(c, role == "organizer"),
        newsletter_on=D.get(c, "newsletter_on") == "1", lots_left=c.execute("SELECT COUNT(*) FROM r2_auctions WHERE status='queued'").fetchone()[0])
    
    # Inject private news strictly during discussion time in Round 2
    st_cur = D.get(c, "stage_cur")
    if rnd >= 1 and st_cur in ("a1", "a2", "a3"):
        _, _, ph = ("a1", rnd, "discussion") # evaluate phase context
        # Check if current phase is discussion
        s0, _ = flow.bounds(c, st_cur)
        current_ph = flow.phase(c, st_cur, now - s0)
        if current_ph == "discussion":
            priv_map = generate_private_news(c, rnd)
            out["private_news"] = priv_map.get(team_id, [])
        else:
            out["private_news"] = []

    if role == "team":
        acc, st, held, committed = portfolio(c, team_id) if c.execute("SELECT 1 FROM r2_accounts WHERE team_id=?", (team_id,)).fetchone() else (None, [], 0, 0)
        if acc:
            sc = scores(c, team_id)
            win_me = c.execute("SELECT 1 FROM r2_windows WHERE team_id=? AND rnd=? AND status='active'", (team_id, rnd)).fetchone() is not None
            live = rnd >= 1 and D.get(c, "stage_cur") in ("a1", "a2", "a3")
            out["finish"] = dict(done=c.execute("SELECT COUNT(*) FROM r2_finish WHERE rnd=?", (rnd,)).fetchone()[0], total=c.execute("SELECT COUNT(*) FROM r2_accounts").fetchone()[0],
                me=bool(c.execute("SELECT 1 FROM r2_finish WHERE rnd=? AND team_id=?", (rnd, team_id)).fetchone()), sessions_over=round_done_sessions(c, rnd) if rnd >= 1 else False)
            out["me"] = dict(participant=True, team_id=team_id, start=acc["start_cash"], cash=acc["cash"], committed=committed, capacity=acc["cash"] - committed, value=sc["value"], held=held,
                borrowed=sc["borrowed"], borrow_penalty=sc["borrow_penalty"], net_cash=acc["cash"] - sc["borrowed"], borrow_limit=int(borrow_limit(c)), borrow_room=borrow_room(c, team_id, rnd) if rnd >= 1 else 0, borrow_fee_pct=borrow_fee_pct(c), borrow_pen_unit=int(borrow_pen_unit(c)), fees_paid=int(acc["fees"] or 0), can_act=live,
                loans=[dict(r) for r in c.execute("SELECT kind,amount,fee,outstanding,rnd,ts FROM r2_loans WHERE team_id=? ORDER BY id DESC LIMIT 8", (team_id,))],
                growth_pct=sc["growth_pct"], points=dict(r1=sc["r1"], r2=sc["r2"], overall=sc["overall"]), swaps_left=swaps_left(c, team_id), swaps_total=swaps_total(c, team_id), swap_ttl=int(swap_ttl(c)), in_session=win_me, stakes=[dict(symbol=s["symbol"], industry=s["industry"], company=s["name"], pct=s["bp"] / 100, value=s["bp"] * s["value"] // 10000, cost=s["cost"]) for s in st])
            out["swaps"] = [dict(r) | dict(proposer_name=tname(c, r["proposer"]), receiver_name=tname(c, r["receiver"])) for r in c.execute("SELECT * FROM r2_swaps WHERE (rnd=? OR status='pending') AND (proposer=? OR receiver=?) ORDER BY id DESC LIMIT 12", (rnd, team_id, team_id))]
        else: out["me"] = dict(participant=False)
    if role == "organizer":
        out["accounts"] = [dict(team_id=r["team_id"], name=tname(c, r["team_id"]), cash=r["cash"], borrowed=r["borrowed"], fees=r["fees"]) for r in c.execute("SELECT * FROM r2_accounts")]
        out["loans"] = [dict(r) | dict(name=tname(c, r["team_id"])) for r in c.execute("SELECT * FROM r2_loans ORDER BY id DESC LIMIT 40")]
        out["history"] = [dict(r) | dict(seller_name=tname(c, r["seller"]), winner_name=tname(c, r["winner"]) if r["winner"] else None) for r in c.execute("SELECT * FROM r2_auctions WHERE status NOT IN ('queued') ORDER BY id DESC LIMIT 60")]
        out["all_swaps"] = [dict(r) | dict(proposer_name=tname(c, r["proposer"]), receiver_name=tname(c, r["receiver"])) for r in c.execute("SELECT * FROM r2_swaps ORDER BY id DESC LIMIT 40")]
        out["windows"] = [dict(r) | dict(name=tname(c, r["team_id"])) for r in c.execute("SELECT * FROM r2_windows WHERE rnd=? ORDER BY ord", (rnd,))]
    return out
