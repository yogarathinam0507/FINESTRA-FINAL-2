import random, json, database as D, auth

IND = {
    "BANK":"Banking & Financial Services",
    "TECH":"Technology & Telecom",
    "AUTO":"Automobile & EV",
    "ENERGY":"Energy & Renewables",
    "PHARMA":"Healthcare & Pharma",
    "INFRA":"Infrastructure, Metals & Manufacturing",
    "COMM":"Commodity-Linked"
}

# 12 industry stocks (2 per industry) + 3 commodity-linked stocks.
CO = [
    ("AURB","Aurora Bank","BANK",1450,1.1,.8,78),("MRDN","Meridian Finserv","BANK",820,1.2,1.0,70),
    ("NVTL","Novatel Systems","TECH",1980,1.0,.9,80),("QBIT","Quantabit Software","TECH",1120,1.2,1.2,72),
    ("VOLT","Voltaro Motors","AUTO",760,1.4,1.4,68),("EVRA","Evara EV","AUTO",430,1.6,1.7,60),
    ("SOLR","Solaris Power","ENERGY",610,1.3,1.3,70),("PTRX","Petrix Oil & Gas","ENERGY",1380,.9,.9,75),
    ("HLXA","Helixa Pharma","PHARMA",1640,.7,.8,82),("CRBY","Carebay Hospitals","PHARMA",480,.8,.8,71),
    ("BLDX","Buildex Infra","INFRA",1075,1.2,1.0,73),("FRGN","Forgenix Steel","INFRA",385,1.4,1.3,63),
    ("GOLD","Aurum Gold Trust","COMM",6200,-.3,.7,66),("CRUD","Brentix Crude-Linked","COMM",780,.6,1.9,60),("INMT","Ironcore Industrial Metals","COMM",540,1.0,1.3,64)
]

RISK = {"GOLD":-1.0,"CRUD":0.5,"INMT":1.0}

# Round 1 Events: Multi-industry impact maps via `sens` dictionaries affecting 2-3 sectors simultaneously
SHOCK = [
    ("Regulator eases capital norms and launches a credit-guarantee scheme - lenders & fintech surge", "BANK", 1, 3, {"AURB":1.3, "MRDN":1.6, "NVTL":0.5, "BLDX":0.3}, 4.0, 4),
    ("Cloud boom & 5G rollout: record contract wins lift tech and telecom infrastructure", "TECH", 1, 3, {"NVTL":1.4, "QBIT":1.7, "AURB":0.3, "BLDX":0.2}, 3.8, 4),
    ("Government fast-tracks EV incentives and charging corridors - auto and manufacturing rally", "AUTO", 1, 3, {"VOLT":1.2, "EVRA":1.7, "FRGN":0.4, "INMT":0.3}, 4.2, 4),
    ("Record clean-power tender and tariff reset lift energy producers and grid suppliers", "ENERGY", 1, 3, {"SOLR":1.7, "PTRX":1.0, "BLDX":0.3}, 4.0, 4),
    ("Breakthrough therapy approved on a fast track - healthcare names and hospital groups jump", "PHARMA", 1, 3, {"HLXA":1.7, "CRBY":1.1, "AURB":0.2}, 4.0, 4),
    ("Budget lifts infrastructure outlay by a third - builders, steel makers and metal commodities surge", "INFRA", 1, 3, {"BLDX":1.7, "FRGN":1.3, "INMT":0.8, "CRUD":0.4}, 4.0, 4),
    ("Gold surges to a record as central banks pile in; commodity-linked funds and metal futures rally", "COMM", 1, 3, {"GOLD":1.8, "INMT":0.5, "CRUD":0.3, "AURB":0.2}, 3.6, 4),
    ("Data-breach scandal at a leading IT services major triggers client pullbacks and banking caution", "TECH", -1, 3, {"NVTL":1.5, "QBIT":1.3, "AURB":-0.4}, 4.0, 4),
    ("Bridge collapse prompts nationwide safety audits, halting infrastructure projects and steel demand", "INFRA", -1, 3, {"BLDX":1.6, "FRGN":1.0, "INMT":-0.5}, 4.0, 4),
    ("Battery-fire probe: regulator halts EV sales pending a safety review, affecting auto and lithium supply chains", "AUTO", -1, 3, {"VOLT":1.0, "EVRA":1.8, "INMT":-0.3}, 4.2, 4)
]

TIMED = ["X01","X08","X03","X09","X04","X05","X07"]

SURP = [
    ("Unexpected earnings beat at leading banks", "BANK", 1, 3, {"AURB":1.3, "MRDN":1.4}, 3.2, 4),
    ("Cyber breach at a major payments platform", "BANK", -1, 3, {"AURB":-1.2, "MRDN":-1.3}, 3.2, 4),
    ("Mega telecom contract won by an IT major", "TECH", 1, 3, {"NVTL":1.4, "QBIT":1.2}, 3.2, 4),
    ("Record EV order from a fleet operator", "AUTO", 1, 3, {"VOLT":1.3, "EVRA":1.5}, 3.2, 4),
    ("Battery fire recall announced by an auto maker", "AUTO", -1, 3, {"VOLT":-1.3, "EVRA":-1.6}, 3.2, 4),
    ("Breakthrough solar efficiency claimed", "ENERGY", 1, 3, {"SOLR":1.5, "PTRX":0.4}, 3.2, 4),
    ("Pipeline leak halts a major refinery", "ENERGY", -1, 3, {"PTRX":-1.5, "SOLR":0.2}, 3.2, 4),
    ("Blockbuster clinical trial results released", "PHARMA", 1, 3, {"HLXA":1.6, "CRBY":0.8}, 3.2, 4),
    ("Defence manufacturing order awarded to infrastructure builders", "INFRA", 1, 3, {"BLDX":1.4, "FRGN":1.2}, 3.2, 4),
    ("Stimulus package announced across industrial sectors", "(all)", 1, 3, {"AURB":1.0,"NVTL":1.0,"VOLT":1.0,"SOLR":1.0,"HLXA":1.0,"BLDX":1.0,"GOLD":1.0}, 2.0, 4),
    ("Gold hits a record on central-bank buying", "GOLD", 1, 3, {"GOLD":1.8, "INMT":0.4}, 3.2, 4)
]

MEGA = [
    ("MEGA EVENT: Global financial panic - circuit breakers trip as equity markets plunge; safe-haven assets surge", None, -1, 5,
     {"AURB":1.7,"MRDN":1.9,"NVTL":1.4,"QBIT":1.7,"VOLT":1.6,"EVRA":1.9,"SOLR":1.5,"PTRX":1.2,"HLXA":.7,"CRBY":.8,"BLDX":1.5,"FRGN":1.6,"GOLD":-1.5,"CRUD":.9,"INMT":1.4}, 9.0, 4),
    ("MEGA EVENT: Landmark stimulus-and-reform budget triggers violent sector rotation - tech, autos, infrastructure and banks surge while energy and gold sell off", None, 1, 5,
     {"AURB":1.1,"MRDN":1.2,"NVTL":1.6,"QBIT":2.0,"VOLT":1.8,"EVRA":2.2,"SOLR":-.6,"PTRX":-1.2,"HLXA":.4,"CRBY":.4,"BLDX":1.6,"FRGN":1.7,"GOLD":-1.0,"CRUD":-1.4,"INMT":1.3}, 8.0, 4)
]

def _syms(ind):
    if ind in (None, "(all)"): return [x[0] for x in CO]
    if ind in IND: return [x[0] for x in CO if x[2]==ind]
    return [ind]

def _add_news(c, lst, kind, pre):
    for k, t in enumerate(lst):
        h, ind, d, sev = t[:4]
        sens = t[4] if len(t)>4 else None
        imp = t[5] if len(t)>5 else sev*0.6
        dur = t[6] if len(t)>6 else sev+1
        ind = None if ind=="(all)" else ind
        label = "Entire market" if ind is None else IND.get(ind, ind)
        syms = list(set(_syms(ind) + list(sens.keys() if sens else [])))
        c.execute("INSERT OR REPLACE INTO news(id,kind,headline,descr,category,industry,symbols,direction,severity,impact,duration,sens) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
         (f"{pre}{k+1:02d}", kind, h, f"Simulated event: {h}. Affected: {label}.", "Macro" if ind is None else "Sector" if ind in IND else "Commodity", label, ",".join(syms), d, sev, imp, dur, json.dumps(sens) if sens else None))

def seed_news(c):
    c.execute("DELETE FROM news"); _add_news(c, SURP, "surprise", "S"); _add_news(c, SHOCK, "shock", "X"); _add_news(c, MEGA, "mega", "M")

def seed_market(c):
    rnd = random.Random(7)
    for t in ("companies","price_history"): c.execute(f"DELETE FROM {t}")
    for s, n, i, p, b, v, f in CO:
        inv = rnd.choice([4000, 5000, 6000, 8000])
        c.execute("INSERT INTO companies(symbol,name,industry,start_price,price,prev_price,inventory,issued,beta,vol,fund,tech) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (s, n, IND[i], p, p, p, inv, inv, b, v, f, 50))
        c.execute("INSERT INTO price_history(symbol,upd,o,h,l,c,v) VALUES(?,?,?,?,?,?,?)", (s, 0, p, p, p, p, 0))
    seed_news(c)

def assign_news_times(c, mode, seed=11):
    c.execute("UPDATE news SET release_t=NULL,released=0,released_upd=NULL")
    if mode=="test": c.execute("UPDATE news SET release_t=180 WHERE id=?",(TIMED[0],)); return
    for k, i in enumerate(TIMED): c.execute("UPDATE news SET release_t=? WHERE id=?", (180+240*k, i))
    c.execute("UPDATE news SET release_t=? WHERE id='M01'", (31*60,))
    c.execute("UPDATE news SET release_t=? WHERE id='M02'", (36*60,))

def _defaults():
    return dict(status="idle",elapsed="0",run_since="0",upd="0",time_scale="1",brk_normal="0.10",capital="1000000",spectator_code="SPECTATE",reg_code="",auto_news="1",
        tick_sec="45",final_tick="30",final5_sec="600",test_sec="300",r1_sec="2400",trans_sec="60",pre_sec="600",brk_sec="60",news_sec="120",disc_sec="180",auc_sec="600",
        window_sec="60",open_sec="30",r2_cash="10000000",r2_teams="5",lots_per_co="1",lot_bp="10000",newsletter_on="1",stage_cur="idle",hold_at="",cfg_ver="5",
        borrow_limit="3000000",borrow_fee_pct="5",borrow_pen="300000",swap_ttl="180",chart_epoch="0")

def migrate(c):
    for col in ("sens TEXT","release_t REAL"):
        try: c.execute(f"ALTER TABLE news ADD COLUMN {col}")
        except Exception: pass
    for k, v in _defaults().items():
        if D.get(c, k) is None: D.put(c, k, v)
    cv = D.get(c, "cfg_ver")
    if cv not in ("4","5"):
        seed_market(c)
        c.execute("DELETE FROM holdings"); c.execute("DELETE FROM orders"); c.execute("DELETE FROM leaderboard_snapshots")
        c.execute("UPDATE teams SET cash=?,brokerage=0,penalties=0,trades=0,prev_rank=0",(D.get(c,"capital"),))
        cv="4"
    if cv=="4":
        seed_news(c); D.put(c,"cfg_ver","5")
        if D.get(c,"status") in ("running","paused") and D.get(c,"stage_cur") in ("test","r1"): assign_news_times(c, D.get(c,"stage_cur"))

def seed(c, force=False):
    if not c.execute("SELECT COUNT(*) FROM companies").fetchone()[0] or force: seed_market(c)
    migrate(c)
    if not c.execute("SELECT 1 FROM users").fetchone():
        h, s = auth.hash_pw("admin123"); c.execute("INSERT INTO users(username,pw_hash,salt) VALUES(?,?,?)",("organizer",h,s))
    import r2_engine; r2_engine.ensure_companies(c)
