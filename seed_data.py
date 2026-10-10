import random, json, database as D, auth
IND = {"BANK":"Banking & Financial Services","TECH":"Technology & Telecom","AUTO":"Automobile & EV","ENERGY":"Energy & Renewables","PHARMA":"Healthcare & Pharma","INFRA":"Infrastructure, Metals & Manufacturing","COMM":"Commodity-Linked"}
# 12 industry stocks (2 per industry) + 3 commodity-linked stocks.  (symbol,name,industry,price,beta,vol,fundamental)
CO = [("AURB","Aurora Bank","BANK",1450,1.1,.8,78),("MRDN","Meridian Finserv","BANK",820,1.2,1.0,70),
("NVTL","Novatel Systems","TECH",1980,1.0,.9,80),("QBIT","Quantabit Software","TECH",1120,1.2,1.2,72),
("VOLT","Voltaro Motors","AUTO",760,1.4,1.4,68),("EVRA","Evara EV","AUTO",430,1.6,1.7,60),
("SOLR","Solaris Power","ENERGY",610,1.3,1.3,70),("PTRX","Petrix Oil & Gas","ENERGY",1380,.9,.9,75),
("HLXA","Helixa Pharma","PHARMA",1640,.7,.8,82),("CRBY","Carebay Hospitals","PHARMA",480,.8,.8,71),
("BLDX","Buildex Infra","INFRA",1075,1.2,1.0,73),("FRGN","Forgenix Steel","INFRA",385,1.4,1.3,63),
("GOLD","Aurum Gold Trust","COMM",6200,-.3,.7,66),("CRUD","Brentix Crude-Linked","COMM",780,.6,1.9,60),("INMT","Ironcore Industrial Metals","COMM",540,1.0,1.3,64)]
RISK = {"GOLD":-1.0,"CRUD":0.5,"INMT":1.0}   # risk-off events: gold rises when equities fall
# ---------------------------------------------------------------------------------------------------------------------------------
# ROUND 1 EVENTS.  The regular 2-minute news cards were REMOVED completely.  Only surprise market events remain:
#   * "shock" events  - released automatically every 4 minutes (3:00, 7:00 ... 27:00).  One sector/commodity group is hit hard by each event
#                       (impact ~4% per update for 4 updates on the target stocks, only small spill-over elsewhere).
#   * "mega" events   - 31:00 and 36:00 (market-wide rotation).
#   * "surprise" pool - extra cards the organiser may release by hand.
# Every pool is balanced about 70% positive / 30% negative and covers all six industries plus the commodity group.
# (headline, industry|symbol|None, direction, severity[, sens, impact %, duration in updates])
# ---------------------------------------------------------------------------------------------------------------------------------
SHOCK = [   # X01..X10 - 7 positive / 3 negative; the 7 TIMED ones (see TIMED) are 5 positive / 2 negative and hit each of the 7 groups once
("Regulator eases capital norms and launches a credit-guarantee scheme - lenders surge","BANK",1,3,{"AURB":1.3,"MRDN":1.6,"BLDX":.25},4.0,4),
("Cloud boom: record deal pipeline and margin upgrades lift software and IT services","TECH",1,3,{"NVTL":1.4,"QBIT":1.7,"AURB":.2},3.8,4),
("Government fast-tracks EV incentives and charging corridors - auto stocks rally","AUTO",1,3,{"VOLT":1.2,"EVRA":1.7,"FRGN":.25},4.2,4),
("Record clean-power tender and tariff reset lift energy producers","ENERGY",1,3,{"SOLR":1.7,"PTRX":1.0},4.0,4),
("Breakthrough therapy approved on a fast track - healthcare names jump","PHARMA",1,3,{"HLXA":1.7,"CRBY":1.1},4.0,4),
("Budget lifts infrastructure outlay by a third - builders and steel makers surge","INFRA",1,3,{"BLDX":1.7,"FRGN":1.3,"INMT":.3},4.0,4),
("Gold surges to a record as central banks pile in; commodity-linked funds rally","COMM",1,3,{"GOLD":1.8,"INMT":.5,"CRUD":.3},3.6,4),
("Data-breach scandal at a leading IT services major triggers client pullbacks","TECH",-1,3,{"NVTL":1.5,"QBIT":1.3,"AURB":.2},4.0,4),
("Bridge collapse prompts a nationwide audit and payment holds for builders","INFRA",-1,3,{"BLDX":1.6,"FRGN":1.0},4.0,4),
("Battery-fire probe: regulator halts EV sales pending a safety review","AUTO",-1,3,{"VOLT":1.0,"EVRA":1.8},4.2,4)]
TIMED = ["X01","X08","X03","X09","X04","X05","X07"]      # one event every 4 minutes, starting at 3:00: BANK+ TECH- AUTO+ INFRA- ENERGY+ PHARMA+ COMM+  (5 positive, 2 negative, all 7 groups)

# Manual surprise pool (organiser releases by hand): 14 positive / 6 negative, every group covered.
SURP = [("Unexpected earnings beat at a leading bank","BANK",1,3,None,3.2,4),("Cyber breach at a payments platform","BANK",-1,3,None,3.2,4),
("Credit growth hits a multi-year high","BANK",1,2,None,2.4,3),("Mega telecom contract won by an IT major","TECH",1,3,None,3.2,4),
("Record EV order from a fleet operator","AUTO",1,3,None,3.2,4),("Battery fire recall announced by an auto maker","AUTO",-1,3,None,3.2,4),
("Oil falls sharply, bringing cost relief to automakers","AUTO",1,2,None,2.4,3),("Breakthrough solar efficiency claimed","ENERGY",1,3,None,3.2,4),
("Pipeline leak halts a major refinery","ENERGY",-1,3,None,3.2,4),("Blockbuster trial results released","PHARMA",1,3,None,3.2,4),
("Regulator flags drug-trial irregularities","PHARMA",-1,3,None,3.2,4),("Hospital footfall rises sharply","PHARMA",1,2,None,2.4,3),
("Defence manufacturing order awarded to a builder","INFRA",1,3,None,3.2,4),("Environmental clearance delays stall projects","INFRA",-1,2,None,2.4,3),
("Stimulus package announced","(all)",1,3,None,2.0,4),("Trade deal signed with a major partner","(all)",1,3,None,2.0,4),
("Sovereign rating upgraded","(all)",1,3,None,2.0,4),("Gold hits a record on central-bank buying","GOLD",1,3,None,3.2,4),
("Industrial-metal demand surges on the infrastructure pipeline","INMT",1,3,None,3.2,4),("Stronger dollar and ETF outflows hit gold","GOLD",-1,2,None,2.4,3)]

# MEGA surprise events (Round 1, 31st and 36th minute): very large, sector-rotating moves.  One panic (negative), one stimulus rotation (positive).
# (headline, industry, direction, severity, sens, impact %, duration in updates).  sens overrides the per-stock multiplier (negative = opposite move).
MEGA = [("MEGA EVENT: Global financial panic - circuit breakers trip as equity markets plunge; safe-haven assets surge", None, -1, 5,
  {"AURB":1.7,"MRDN":1.9,"NVTL":1.4,"QBIT":1.7,"VOLT":1.6,"EVRA":1.9,"SOLR":1.5,"PTRX":1.2,"HLXA":.7,"CRBY":.8,"BLDX":1.5,"FRGN":1.6,"GOLD":-1.5,"CRUD":.9,"INMT":1.4}, 9.0, 4),
 ("MEGA EVENT: Landmark stimulus-and-reform budget triggers violent sector rotation - tech, autos, infrastructure and banks surge while energy and gold sell off", None, 1, 5,
  {"AURB":1.1,"MRDN":1.2,"NVTL":1.6,"QBIT":2.0,"VOLT":1.8,"EVRA":2.2,"SOLR":-.6,"PTRX":-1.2,"HLXA":.4,"CRBY":.4,"BLDX":1.6,"FRGN":1.7,"GOLD":-1.0,"CRUD":-1.4,"INMT":1.3}, 8.0, 4)]
def _syms(ind):
    if ind in (None, "(all)"): return [x[0] for x in CO]
    if ind in IND: return [x[0] for x in CO if x[2]==ind]
    return [ind]
def _add_news(c, lst, kind, pre):
    for k,t in enumerate(lst):
        h,ind,d,sev=t[:4]; sens=t[4] if len(t)>4 else None; imp=t[5] if len(t)>5 else sev*0.6; dur=t[6] if len(t)>6 else sev+1
        ind=None if ind=="(all)" else ind
        label="Entire market" if ind is None else IND.get(ind, ind)
        syms=_syms(ind)+[x for x in (sens or {}) if x not in _syms(ind)]            # spill-over stocks listed in `sens` are affected too
        c.execute("INSERT OR REPLACE INTO news(id,kind,headline,descr,category,industry,symbols,direction,severity,impact,duration,sens) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
         (f"{pre}{k+1:02d}",kind,h,f"Simulated event: {h}. Affected: {label}.","Macro" if ind is None else "Sector" if ind in IND else "Commodity",label,",".join(syms),d,sev,imp,dur,json.dumps(sens) if sens else None))
def seed_news(c):
    c.execute("DELETE FROM news"); _add_news(c,SURP,"surprise","S"); _add_news(c,SHOCK,"shock","X"); _add_news(c,MEGA,"mega","M")
def seed_market(c):
    rnd = random.Random(7)
    for t in ("companies","price_history"): c.execute(f"DELETE FROM {t}")
    for s,n,i,p,b,v,f in CO:
        inv = rnd.choice([4000,5000,6000,8000])
        c.execute("INSERT INTO companies(symbol,name,industry,start_price,price,prev_price,inventory,issued,beta,vol,fund,tech) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(s,n,IND[i],p,p,p,inv,inv,b,v,f,50))
        c.execute("INSERT INTO price_history(symbol,upd,o,h,l,c,v) VALUES(?,?,?,?,?,?,?)",(s,0,p,p,p,p,0))
    seed_news(c)
def assign_news_times(c, mode, seed=11):
    """Round-1 event timetable (event-seconds from the start of the stage).  NO regular news cards any more.
    Round 1: one surprise market event every 4 minutes (3:00, 7:00 ... 27:00) + MEGA events at 31:00 and 36:00.  Test round shows one sample event."""
    c.execute("UPDATE news SET release_t=NULL,released=0,released_upd=NULL")
    if mode=="test": c.execute("UPDATE news SET release_t=180 WHERE id=?",(TIMED[0],)); return
    for k,i in enumerate(TIMED): c.execute("UPDATE news SET release_t=? WHERE id=?",(180+240*k,i))
    c.execute("UPDATE news SET release_t=? WHERE id='M01'",(31*60,)); c.execute("UPDATE news SET release_t=? WHERE id='M02'",(36*60,))
def _defaults():
    return dict(status="idle",elapsed="0",run_since="0",upd="0",time_scale="1",brk_normal="0.10",capital="1000000",spectator_code="SPECTATE",reg_code="",auto_news="1",
        tick_sec="45",final_tick="30",final5_sec="600",test_sec="300",r1_sec="2400",trans_sec="60",pre_sec="600",brk_sec="60",news_sec="120",disc_sec="180",auc_sec="600",
        window_sec="60",open_sec="30",r2_cash="10000000",r2_teams="5",lots_per_co="1",lot_bp="10000",newsletter_on="1",stage_cur="idle",hold_at="",cfg_ver="5",
        borrow_limit="3000000",borrow_fee_pct="5",borrow_pen="300000",swap_ttl="180",chart_epoch="0")
def migrate(c):
    """Bring any older database up to the Round-1/Round-2 event format (keeps users and registered teams)."""
    for col in ("sens TEXT","release_t REAL"):
        try: c.execute(f"ALTER TABLE news ADD COLUMN {col}")
        except Exception: pass
    for k,v in _defaults().items():
        if D.get(c,k) is None: D.put(c,k,v)
    for tbl,col in (("r2_accounts","swaps_total INTEGER DEFAULT 1"),("r2_accounts","borrowed INTEGER DEFAULT 0"),("r2_accounts","fees INTEGER DEFAULT 0"),
                    ("r2_swaps","cash INTEGER DEFAULT 0"),("r2_swaps","expires REAL"),("r2_swaps","note TEXT")):
        try: c.execute(f"ALTER TABLE {tbl} ADD COLUMN {col}")
        except Exception: pass
    cv=D.get(c,"cfg_ver")
    if cv not in ("4","5"):
        seed_market(c)
        c.execute("DELETE FROM holdings"); c.execute("DELETE FROM orders"); c.execute("DELETE FROM leaderboard_snapshots")
        c.execute("UPDATE teams SET cash=?,brokerage=0,penalties=0,trades=0,prev_rank=0",(D.get(c,"capital"),))
        for k,v in dict(status="idle",elapsed="0",run_since="0",upd="0",stage_cur="idle",tick_sec="45",final_tick="30",final5_sec="600",r1_sec="2400",lots_per_co="1",lot_bp="10000",window_sec="60",hold_at="",cfg_ver="4").items(): D.put(c,k,v)
        import r2_seed
        for code,ind,name,sym,val,icon in r2_seed.INDUSTRIES: c.execute("UPDATE r2_companies SET value=?,start_value=? WHERE symbol=?",(val,val,sym))
        cv="4"
    if cv=="4":                      # v5: regular 2-minute news cards removed, balanced surprise-event pools, loans, new swap fields (event state is kept)
        seed_news(c); D.put(c,"cfg_ver","5")
        if D.get(c,"status") in ("running","paused") and D.get(c,"stage_cur") in ("test","r1"): assign_news_times(c, D.get(c,"stage_cur"))
def seed(c, force=False):
    if not c.execute("SELECT COUNT(*) FROM companies").fetchone()[0] or force: seed_market(c)
    migrate(c)
    if not c.execute("SELECT 1 FROM users").fetchone():
        h,s = auth.hash_pw("admin123"); c.execute("INSERT INTO users(username,pw_hash,salt) VALUES(?,?,?)",("organizer",h,s))
    import r2_engine; r2_engine.ensure_companies(c)
