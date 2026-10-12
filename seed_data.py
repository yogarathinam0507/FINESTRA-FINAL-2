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

# Round 1 Automatic News Letters (Affects 2-3 industries simultaneously)
SHOCK = [
    ("RBI Holds Key Rates; Tech Spending Surge Offset by EV Subsidy Cut Concerns", 
     "Banking & Financial Services, Technology & Telecom, Automobile & EV", 1, 3, 
     {"AURB":1.2, "MRDN":1.2, "NVTL":1.1, "QBIT":1.0, "VOLT":-0.8, "EVRA":-0.9}, 3.5, 4),
     
    ("Renewable Integration Mandates Boost Clean Power; Infrastructure Approvals Accelerate", 
     "Energy & Renewables, Infrastructure, Metals & Manufacturing", 1, 3, 
     {"SOLR":1.5, "PTRX":1.2, "BLDX":1.3, "FRGN":1.2, "INMT":1.1}, 3.8, 4),
     
    ("Commodity Volatility Hits Peak; Global Crude Supply Disruption Sparks Energy Rally", 
     "Commodity-Linked, Energy & Renewables, Healthcare & Pharma", 1, 3, 
     {"GOLD":1.6, "CRUD":1.7, "PTRX":1.4, "SOLR":1.2, "HLXA":-0.6}, 4.0, 4),
     
    ("FinTech Regulation Tightens as Telecom Operators Expand 5G Enterprise Services", 
     "Banking & Financial Services, Technology & Telecom", 1, 3, 
     {"AURB":1.3, "MRDN":1.1, "NVTL":1.3, "QBIT":1.2}, 3.2, 4),
     
    ("Infrastructure Spending Boom Triggers Industrial Metal Shortage", 
     "Infrastructure, Metals & Manufacturing, Commodity-Linked", 1, 3, 
     {"BLDX":1.5, "FRGN":1.4, "INMT":1.6, "GOLD":0.8}, 3.8, 4),
     
    ("Healthcare Modernization Grant Announced; EV Battery Cost Breakthrough Reported", 
     "Healthcare & Pharma, Automobile & EV", 1, 3, 
     {"HLXA":1.5, "CRBY":1.3, "VOLT":1.3, "EVRA":1.5}, 3.5, 4),
     
    ("Central Banks Boost Gold Reserves Amid Crude Stabilization", 
     "Commodity-Linked, Banking & Financial Services", 1, 3, 
     {"GOLD":1.7, "AURB":1.1, "MRDN":1.1, "CRUD":-0.3}, 3.2, 4),
     
    ("Global Green Energy Accord Signed; Tech Offshoring Demand Soars", 
     "Energy & Renewables, Technology & Telecom", 1, 3, 
     {"SOLR":1.6, "NVTL":1.4, "QBIT":1.3, "PTRX":0.5}, 3.6, 4)
]

TIMED = ["X01","X02","X03","X04","X05","X06","X07","X08"]

# Round 1 Manual Release News Cards (3 per sector: 2 Positive, 1 Negative)
SURP = [
    # 1. Banking & Financial Services
    ("Aurora Bank & Meridian Finserv Report Record Quarterly Profit & Loan Growth", "Banking & Financial Services", 1, 3, {"AURB":1.5, "MRDN":1.4}, 4.0, 3),
    ("RBI Grants Express Approval for Next-Gen FinTech Expansion", "Banking & Financial Services", 1, 2, {"AURB":1.3, "MRDN":1.2}, 3.0, 3),
    ("Cybersecurity Vulnerability Discovered in Shared Payment Gateway", "Banking & Financial Services", -1, 3, {"AURB":-1.2, "MRDN":-1.4}, 4.0, 3),
    
    # 2. Technology & Telecom
    ("Novatel Systems Secures Multi-Million Dollar European Telecom Deal", "Technology & Telecom", 1, 3, {"NVTL":1.6}, 4.5, 3),
    ("Quantabit Software Launches Enterprise AI Suite; Order Pipeline Soars", "Technology & Telecom", 1, 2, {"QBIT":1.5}, 3.5, 3),
    ("Quantabit Software Experiences Cloud Breach; Client Audits Trigger Delays", "Technology & Telecom", -1, 3, {"QBIT":-1.5, "NVTL":-0.8}, 4.0, 3),
    
    # 3. Automobile & EV
    ("Voltaro Motors & Evara EV Partner for Highway Supercharging Corridor", "Automobile & EV, Infrastructure", 1, 3, {"VOLT":1.5, "EVRA":1.5, "BLDX":0.5}, 3.8, 3),
    ("Evara EV Wins Landmark Order for Commercial Delivery Fleet Units", "Automobile & EV", 1, 2, {"EVRA":1.6, "VOLT":0.8}, 3.5, 3),
    ("Thermal Overheating Probe Halts Shipments for Voltaro Motors", "Automobile & EV", -1, 3, {"VOLT":-1.6, "EVRA":-1.1}, 4.0, 3),
    
    # 4. Energy & Renewables
    ("Solaris Power Bags Massive 500MW Government Solar Park Tender", "Energy & Renewables", 1, 3, {"SOLR":1.6}, 4.2, 3),
    ("Petrix Oil & Gas Strikes Ultra-Deep Offshore Natural Gas Field", "Energy & Renewables, Commodity-Linked", 1, 3, {"PTRX":1.7, "CRUD":0.8}, 4.5, 3),
    ("Key Pipeline Rupture Forces Production Shutdown at Petrix Facility", "Energy & Renewables", -1, 3, {"PTRX":-1.6, "SOLR":0.4}, 4.0, 3),
    
    # 5. Healthcare & Pharma
    ("Helixa Pharma Receives Full US FDA Approval for Generic Oncology Drug", "Healthcare & Pharma", 1, 3, {"HLXA":1.8}, 5.0, 3),
    ("Carebay Hospitals Expands Bed Capacity via Regional Acquisition", "Healthcare & Pharma", 1, 2, {"CRBY":1.4}, 3.5, 3),
    ("Health Regulator Flags Trial Inconsistencies for Helixa Pharma Drug", "Healthcare & Pharma", -1, 3, {"HLXA":-1.7, "CRBY":-0.5}, 4.0, 3),
    
    # 6. Infrastructure & Metals
    ("Buildex Infra Awarded Multi-Billion Urban Transit Project", "Infrastructure, Metals & Manufacturing", 1, 3, {"BLDX":1.5, "FRGN":0.8}, 4.0, 3),
    ("Forgenix Steel Signs Export Bilateral Supply Contract for High-Grade Alloy", "Metals & Manufacturing", 1, 2, {"FRGN":1.4, "INMT":0.6}, 3.5, 3),
    ("Forgenix Steel Facility Outage Caused by Regional Power Failure", "Metals & Manufacturing, Infrastructure", -1, 3, {"FRGN":-1.6, "INMT":-0.7}, 4.2, 3),
    
    # 7. Commodity-Linked
    ("Central Banks Accelerate Bullion Purchases; Aurum Gold Trust Surges", "Commodity-Linked", 1, 3, {"GOLD":1.4}, 3.2, 3),
    ("OPEC+ Production Cuts Send Crude Oil Futures to Multi-Month Highs", "Commodity-Linked, Energy & Renewables", 1, 2, {"CRUD":1.6, "PTRX":1.5}, 4.0, 3),
    ("Sluggish Smelting Demand Slams Ironcore Industrial Metals Prices", "Commodity-Linked, Metals & Manufacturing", -1, 3, {"INMT":-1.5, "FRGN":-0.8}, 3.5, 3)
]

# Round 1 Mega Surprise Events (Affects All Sectors)
MEGA = [
    ("MEGA EVENT: Sovereign Debt Crisis Triggers Global Market Sell-Off", "Entire Market (All Sectors)", -1, 5,
     {"AURB":1.7,"MRDN":1.9,"NVTL":1.4,"QBIT":1.7,"VOLT":1.6,"EVRA":1.9,"SOLR":1.5,"PTRX":1.2,"HLXA":.7,"CRBY":.8,"BLDX":1.5,"FRGN":1.6,"GOLD":-1.5,"CRUD":.9,"INMT":1.4}, 6.0, 5),
    ("MEGA EVENT: Central Government Unveils Massive Economic Revitalization Budget", "Entire Market (All Sectors)", 1, 5,
     {"AURB":1.5,"MRDN":1.6,"NVTL":1.8,"QBIT":2.0,"VOLT":1.9,"EVRA":2.2,"SOLR":1.5,"PTRX":1.2,"HLXA":1.1,"CRBY":1.1,"BLDX":1.8,"FRGN":1.9,"GOLD":-1.0,"CRUD":-1.0,"INMT":1.7}, 6.5, 5)
]

def _syms(ind_string):
    symbols = set()
    parts = [p.strip() for p in ind_string.split(",")]
    for part in parts:
        full_name = IND.get(part, part)
        for s, n, i, p, b, v, f in CO:
            if i == part or IND.get(i) == full_name or full_name.lower() in IND.get(i, "").lower():
                symbols.add(s)
    return list(symbols) if symbols else [x[0] for x in CO]

def _add_news(c, lst, kind, pre):
    for k, t in enumerate(lst):
        h, ind_label, d, sev = t[:4]
        sens = t[4] if len(t)>4 else None
        imp = t[5] if len(t)>5 else sev*0.6
        dur = t[6] if len(t)>6 else sev+1
        
        label = "Entire market" if ind_label is None or "Entire" in ind_label else ind_label
        syms = list(set(_syms(ind_label) + list(sens.keys() if sens else [])))
        
        c.execute("INSERT OR REPLACE INTO news(id,kind,headline,descr,category,industry,symbols,direction,severity,impact,duration,sens) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
         (f"{pre}{k+1:02d}", kind, h, f"Simulated event: {h}. Affected Sectors: {label}.", "Macro" if "Entire" in label else "Sector", label, ",".join(syms), d, sev, imp, dur, json.dumps(sens) if sens else None))

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
        window_sec="60",open_sec="30",r2_cash="10000000",r2_teams="5",lots_per_co="1",lot_bp="10000",newsletter_on="1",stage_cur="idle",hold_at="",cfg_ver="7",
        borrow_limit="3000000",borrow_fee_pct="5",borrow_pen="300000",swap_ttl="180",chart_epoch="0")

def migrate(c):
    for col in ("sens TEXT","release_t REAL"):
        try: c.execute(f"ALTER TABLE news ADD COLUMN {col}")
        except Exception: pass
    for k, v in _defaults().items():
        if D.get(c, k) is None: D.put(c, k, v)
    cv = D.get(c, "cfg_ver")
    # Bumped cfg_ver to "7" to force database re-seeding on Render
    if cv != "7":
        seed_market(c)
        c.execute("DELETE FROM holdings"); c.execute("DELETE FROM orders"); c.execute("DELETE FROM leaderboard_snapshots")
        c.execute("UPDATE teams SET cash=?,brokerage=0,penalties=0,trades=0,prev_rank=0",(D.get(c,"capital"),))
        seed_news(c)
        D.put(c,"cfg_ver","7")
        if D.get(c,"status") in ("running","paused") and D.get(c,"stage_cur") in ("test","r1"): 
            assign_news_times(c, D.get(c,"stage_cur"))

def seed(c, force=False):
    if not c.execute("SELECT COUNT(*) FROM companies").fetchone()[0] or force: seed_market(c)
    migrate(c)
    if not c.execute("SELECT 1 FROM users").fetchone():
        h, s = auth.hash_pw("admin123"); c.execute("INSERT INTO users(username,pw_hash,salt) VALUES(?,?,?)",("organizer",h,s))
    import r2_engine; r2_engine.ensure_companies(c)
