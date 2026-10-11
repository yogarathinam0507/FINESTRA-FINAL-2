"""Round 2 content: default industries/companies and the newsletter generator.
News is composed offline from professionally worded templates (no network/LLM call at event time). Each card carries HIDDEN
per-company price impacts; only headline/article/severity/sentiment are ever shown to teams."""
import random, json
# code, industry, company, symbol, valuation (INR), icon
INDUSTRIES = [("BANK","Banking & Fintech","Orbis Bank","ORBK",6_000_000,"🏦"),("TECH","Information Technology","Nexora Systems","NXRA",6_500_000,"💻"),
("AUTO","Automobile & EV","Vanta Motors","VNTA",5_500_000,"🚗"),("RNEW","Renewable Energy","Heliora Power","HLRA",5_000_000,"☀️"),
("PHRM","Pharma & Healthcare","Curavita Labs","CRVT",7_000_000,"💊"),("INFR","Infrastructure & Construction","Stratos Infra","STRX",6_000_000,"🏗️"),
("METL","Metals & Mining","Ferrolux Metals","FRLX",4_500_000,"⛏️"),("RETL","Consumer & Retail","Bazaario Retail","BZRO",4_500_000,"🛍️")]
V = {"BANK":("the banking regulator","deposit and funding costs","retail lending"),"TECH":("the IT ministry","skilled-talent costs","enterprise cloud services"),
"AUTO":("the transport ministry","battery cells and chips","electric vehicles"),"RNEW":("the power ministry","solar modules and polysilicon","renewable capacity"),
"PHRM":("the drug regulator","active pharmaceutical ingredients","specialty formulations"),"INFR":("the highways authority","cement and structural steel","project execution"),
"METL":("the mines ministry","coking coal and iron ore","alloy and steel output"),"RETL":("the consumer-affairs ministry","packaging and edible-oil inputs","private-label ranges")}
SPILL = {"BANK":{"INFR":.3,"RETL":.3},"TECH":{"BANK":.25},"AUTO":{"METL":.4},"RNEW":{"INFR":.3,"AUTO":.3},"PHRM":{},"INFR":{"METL":.4},"METL":{"AUTO":.35,"INFR":.35},"RETL":{"BANK":.2}}
# key, direction, severity, category, shown sentiment, icon, headline, subhead, body, spill
T = [
("earn",1,2,"Earnings","Positive","📈","{co} posts surprise jump in quarterly profit","Margins widen as {prod} demand outpaces street estimates","{co} reported operating profit well ahead of analyst estimates, aided by softer {inp} costs and a richer mix in {prod}. Management flagged healthy order visibility for the coming quarter but cautioned that part of the gain stems from one-off efficiencies.",0),
("pol_up",1,2,"Policy","Positive","🏛️","Government unveils support framework for {ind}","{reg} outlines multi-year measures; eligibility details awaited","{reg} has tabled a framework aimed at easing capacity constraints in {ind}. Domestic players with existing capacity appear best placed, although industry bodies note that the fine print on eligibility is yet to be published.",1),
("exp_curb",-1,2,"Regulation","Negative","📜","{reg} tightens export norms for {prod}","Licensing requirement adds friction to overseas shipments","New licensing conditions announced by {reg} will apply to outbound shipments linked to {prod}. Companies with a large export share may face longer clearance cycles, while domestically focused peers could see relief on local pricing.",1),
("strike",-1,2,"Labour","Negative","🪧","Trade union serves strike notice at {co} facilities","Talks on wage revision stall for a third week","A major trade union has served a strike notice at {co}'s principal facilities after wage-revision talks failed to produce a settlement. Management says contingency inventory is in place, but analysts are tracking the risk to near-term output.",1),
("short",-1,2,"Supply Chain","Negative","⛓️","Raw-material shortage clouds {co} production outlook","Tight availability of {inp} lifts procurement costs","Suppliers have warned of constrained availability of {inp}, forcing {co} to source at spot prices. Brokerages are revisiting margin assumptions across {ind} as the squeeze appears to extend beyond a single quarter.",1),
("contract",1,3,"Contracts","Positive","📑","{co} bags marquee multi-year order","Contract tied to {prod} lifts revenue visibility","{co} has secured a large multi-year order linked to {prod}, which management says adds meaningful revenue visibility. Execution timelines and working-capital needs will determine how much of the benefit reaches earnings.",0),
("board",-1,1,"Governance","Negative","🪑","{co} announces reshuffle in senior management","Three leadership roles change hands ahead of results","{co} said three senior executives will move to new roles next month. The company described it as planned succession, but the timing ahead of results has prompted investor questions on strategic continuity.",0),
("death",-1,2,"Governance","Negative","🕯️","{co} mourns the passing of a senior board member","Audit-committee chair's seat falls vacant","{co} informed exchanges that a senior independent director, who chaired the audit committee, has passed away. Operations are unaffected, though investors will watch how quickly the board is reconstituted and whether key approvals are delayed.",0),
("ceo",-1,3,"Governance","Negative","🚪","CEO of {co} resigns with immediate effect","Board begins search; interim chief appointed","The chief executive of {co} has stepped down with immediate effect, citing personal reasons. An interim chief has been named while the board begins a search, leaving analysts to weigh execution risk against the strength of the existing franchise.",0),
("probe",-1,3,"Regulatory","Negative","🔍","{reg} opens inquiry into {co} disclosures","Questions raised over related-party dealings","{reg} has initiated an inquiry into past disclosures made by {co}. The company said it is cooperating fully and believes its reporting is compliant, but the scope and timeline of the review remain uncertain.",0),
("acq",1,3,"M&A","Positive","🤝","{co} to acquire mid-sized rival in all-cash deal","Synergies promised; funding raises balance-sheet questions","{co} has agreed to acquire a smaller rival, citing cost synergies and a stronger position in {prod}. Funding through internal accruals and fresh borrowing has drawn attention to leverage, even as management guides for earnings accretion within two years.",0),
("tech",1,2,"Technology","Positive","🔬","{co} unveils breakthrough in {prod}","Pilot results show sharp efficiency gains","{co} disclosed pilot results indicating a notable efficiency gain in its {prod} offering. Commercial rollout is expected within a few quarters, though scale-up costs and competitor responses remain open questions.",0),
("port",-1,2,"Logistics","Negative","🚢","Port congestion disrupts {co} shipments","Delays stretch delivery cycles by about two weeks","Prolonged congestion at key ports is delaying inbound and outbound consignments for {co}. The company is rerouting select cargo at higher cost, and analysts expect a temporary dent in dispatch volumes.",1),
("exp_deal",1,2,"Trade","Positive","🌐","{co} signs export agreement with overseas distributor","Three-year pact opens new markets for {prod}","{co} has signed a three-year agreement to supply {prod} through an overseas distribution partner. Volumes are indicative rather than committed, but the pact broadens the company's revenue base.",0),
("inp_up",-1,2,"Commodities","Negative","🛢️","Prices of {inp} climb sharply on tight supply","Input-cost pressure builds across {ind}","Benchmark prices of {inp} have moved higher over recent sessions, raising cost pressure for producers in {ind}. Firms with long-term procurement contracts or pricing power are expected to cope better than thin-margin peers.",1),
("inp_dn",1,1,"Commodities","Positive","📉","Easing of {inp} prices offers relief to {ind}","Lower costs could support margins into next quarter","A cooling in {inp} prices is expected to ease cost pressure for {ind} companies. The benefit may be partly passed on to customers if competitive intensity stays high.",1),
("demand",-1,1,"Demand","Negative","🛒","Demand for {prod} softens, channel checks suggest","Inventory build-up seen at distributors","Channel checks indicate slower offtake of {prod}, with distributors carrying higher inventory than usual. {co} said demand should normalise, but investors are watching for discounting.",0),
("payout",1,1,"Capital Returns","Positive","💰","{co} board approves enhanced shareholder payout","Dividend raised; buyback under evaluation","{co} announced a higher dividend and said the board will evaluate a share buyback. Analysts read it as a sign of confidence in cash generation, while noting that growth investments should not be crowded out.",0),
("recall",-1,2,"Operations","Negative","⚠️","{co} begins voluntary review of {prod} quality","Precautionary step; financial impact not quantified","{co} has begun a voluntary quality review affecting part of its {prod} line. The company called the step precautionary and has not quantified costs, leaving analysts to model a range of outcomes.",0)]
S = [("{co} order inflow tracks ahead of plan","Short-term read: supportive for {ind} earnings visibility.",1),
("Analysts trim {co} target on margin worries","Near-term cost pressure may weigh on {ind} sentiment.",-1),
("{ind} sees heavier institutional activity","Flows suggest rotation; leaders in the space likely to benefit.",1),
("Freight rates edge up for {ind} players","Higher logistics costs trim the margin cushion across peers.",-1),
("Rating agency affirms outlook on {co}","A stable credit view eases funding-cost concerns.",1),
("Unseasonal weather disrupts {ind} operations","Temporary volume hit likely; recovery expected within weeks.",-1),
("{co} secures regulatory nod for expansion","Clearance de-risks the capacity plan; timing remains key.",1),
("Currency swing squeezes {ind} importers","Costlier imported inputs tighten earnings for import-heavy firms.",-1)]
# Guaranteed story types (2 negative + 1 positive per round) so that all nine marquee story types appear once across the three newsletters.
MUST = {1: ['ceo', 'strike', 'contract'], 2: ['probe', 'death', 'acq'], 3: ['short', 'exp_curb', 'tech']}
N_NOW, N_FUT = 6, 4                   # every newsletter: exactly 10 items = 6 current-round events + 4 next-round outlooks
NOW_POS, FUT_POS = 4, 3               # 4+3 = 7 positive and 2+1 = 3 negative items per newsletter  (70% / 30%)
BASE = {1: .03, 2: .06, 3: .10}
def _impacts(rng, comps, code, d, sev, spill, mixed):
    f = rng.uniform(.8, 1.2) * (0.6 if mixed else 1); out = {}
    for cc in comps:
        if cc["code"] == code: out[cc["symbol"]] = round(d * BASE[sev] * f, 4)
        elif spill and cc["code"] in SPILL.get(code, {}): out[cc["symbol"]] = round(d * BASE[sev] * f * SPILL[code][cc["code"]], 4)
    return out
def _fill(t, cc):
    reg, inp, prod = V.get(cc["code"], ("the regulator", "input costs", "core products"))
    return t.format(co=cc["name"], ind=cc["industry"], reg=reg[0].upper() + reg[1:] if t.startswith("{reg}") else reg, inp=inp, prod=prod)
# ---- FUTURE-BASED news: strategic hints about the NEXT auction round. (key, direction, severity, category, shown sentiment, headline, subhead, body)
F = [
("f_pol_up",1,2,"Outlook","Positive","{reg} is expected to unveil a support package for {ind} within weeks","Draft proposals reportedly favour domestic capacity","People familiar with the discussions say {reg} is finalising incentives for {ind}. Nothing is official, but industry bodies are lobbying hard and early signals point towards a favourable announcement before the next review cycle."),
("f_pol_dn",-1,2,"Outlook","Negative","{reg} likely to tighten norms on {prod} in the coming weeks","Consultation paper circulated to industry","A consultation paper doing the rounds suggests stricter conditions on {prod}. If adopted, compliance costs for {ind} players could rise from the next cycle, and smaller firms may find the transition harder than leaders."),
("f_earn_up",1,2,"Outlook","Positive","Analysts expect {co} to beat estimates when next results arrive","Order checks point to firmer volumes and better mix","Channel checks and supplier commentary suggest {co} is tracking ahead of consensus on {prod}. Several brokerages are said to be nudging estimates higher ahead of the next reporting window."),
("f_earn_dn",-1,2,"Outlook","Negative","{co} flags softer guidance; estimate cuts anticipated","Management commentary hints at margin pressure ahead","On a recent call, {co} executives hinted that {inp} costs and pricing pressure could weigh on coming quarters. Analysts are widely expected to trim forecasts before the next window."),
("f_inp_dn",1,1,"Outlook","Positive","Prices of {inp} expected to ease from next month","Futures curve slopes downward for the first time this year","The forward curve for {inp} has flattened sharply. If it holds, {ind} companies could see cost relief feed into margins during the next cycle."),
("f_inp_up",-1,2,"Outlook","Negative","Supply of {inp} seen tightening further; cost pressure likely to build","Producers warn of constrained availability into next quarter","Suppliers have cautioned that availability of {inp} will stay tight, raising procurement costs for {ind} firms from the next cycle unless demand softens."),
("f_deal",1,3,"Outlook","Positive","{co} in advanced talks for a large contract, announcement expected soon","Sources say terms are largely agreed","Sources familiar with the matter say {co} is in the final stage of negotiating a sizeable order linked to {prod}. A formal announcement could land before the next review of valuations."),
("f_probe",-1,3,"Outlook","Negative","{reg} set to widen inquiry into {co}; hearing scheduled","Questions on past disclosures expected to be taken up","{reg} is expected to broaden its examination of {co}'s past disclosures, with a hearing reportedly scheduled soon. The company says it will cooperate, but uncertainty may linger into the next cycle."),
("f_trade",1,2,"Outlook","Positive","Export demand for {prod} set to rise on new trade arrangement","Tariff relief expected to take effect next cycle","A trade arrangement under negotiation is expected to lower tariffs on {prod}. Exporters in {ind}, including {co}, may be early beneficiaries once the pact takes effect."),
("f_labour",-1,2,"Outlook","Negative","Wage talks at {co} heading for deadlock; strike risk rising","Union sets deadline for management response","Negotiations between {co} and its union have stalled, and a deadline has been set. Analysts warn that a stoppage would hit output of {prod} in the next cycle."),
("f_mix",1,2,"Outlook","Positive","{co} expected to announce acquisition, though funding questions linger","Strategic fit seen, balance-sheet impact unclear","Reports suggest {co} is preparing to acquire a smaller rival. Supporters cite synergies in {prod}; sceptics point to leverage and integration risk, leaving the near-term picture unclear."),
]
FUT_UP=[f for f in F if f[1]>0]; FUT_DN=[f for f in F if f[1]<0]
NOW_UP=[t for t in T if t[1]>0]; NOW_DN=[t for t in T if t[1]<0]
def coverage(comps, rnd, cover_seed):
    """Which companies get a CURRENT item and which get an OUTLOOK item in round `rnd` (1..3).  With 8 companies: current covers 6 and
    skips two (different pair every round), the outlooks cover those two plus two others - so every industry appears in EVERY newsletter and
    at least twice as current news (and at least once as an outlook) over the three rounds."""
    n = len(comps); order = random.Random(cover_seed).sample(comps, n); n_cur = min(N_CUR_MAX, n); miss = n - n_cur
    skip = [(miss * (rnd - 1) + j) % n for j in range(miss)]; extra = [(miss * (rnd - 1) + miss * 3 + j) % n for j in range(miss)]
    cur = [order[i] for i in range(n) if i not in skip]; out = [order[i] for i in skip] + [order[i] for i in extra if i not in skip]
    return cur[:N_NOW], out[:N_FUT]
N_CUR_MAX = N_NOW
def gen_round(rnd, comps, used, seed, cover_seed=None):
    """10 newsletter items per auction round: 6 PRESENT/current events + 4 FUTURE outlooks about the NEXT round, 7 positive / 3 negative.
    `used` = set of (code, template) already issued so every round brings new stories.  Present news re-prices companies at once;
    an outlook only hints - its (hidden) price effect lands when the next auction round starts (Round 3's lands in the final settlement)."""
    rng = random.Random(seed * 100 + rnd); rows = []; cur, out = coverage(comps, rnd, seed if cover_seed is None else cover_seed); items = []; round_keys = set()
    dirs = [1] * NOW_POS + [-1] * (len(cur) - NOW_POS); rng.shuffle(dirs); forced = list(MUST.get(rnd, []))
    # present news: place the guaranteed story types first (they fix the direction of their slot), the rest is drawn at random
    slots = list(zip(cur, dirs)); rng.shuffle(slots)
    for key in forced:
        t0 = next(t for t in T if t[0] == key); want = t0[1]; i = next((i for i, (cc, d) in enumerate(slots) if d == want and (cc["code"], key) not in used), None)
        if i is None: i = next((i for i, (cc, d) in enumerate(slots) if d == want), None)
        if i is None: continue
        cc, d = slots.pop(i); items.append(("now", cc, t0)); used.add((cc["code"], key)); round_keys.add(key)
    for cc, d in slots:
        pool = NOW_UP if d > 0 else NOW_DN; p = [t for t in pool if (cc["code"], t[0]) not in used and t[0] not in round_keys] or [t for t in pool if (cc["code"], t[0]) not in used] or pool
        t = rng.choice(p); used.add((cc["code"], t[0])); round_keys.add(t[0]); items.append(("now", cc, t))
    fdirs = [1] * FUT_POS + [-1] * (len(out) - FUT_POS); rng.shuffle(fdirs)
    for cc, d in zip(out, fdirs):
        pool = FUT_UP if d > 0 else FUT_DN; p = [t for t in pool if (cc["code"], t[0]) not in used and t[0] not in round_keys] or [t for t in pool if (cc["code"], t[0]) not in used] or pool
        t = rng.choice(p); used.add((cc["code"], t[0])); round_keys.add(t[0]); items.append(("future", cc, t))
    rng.shuffle(items); ex = []
    for kind, cc, t in items:
        if kind == "now": key, d, sev, cat, shown, icon, head, sub, body, spill = t
        else: key, d, sev, cat, shown, head, sub, body = t; icon = "🔮"; spill = 1
        ex.append(dict(kind=kind, cc=cc, tkey=key, sev=sev, cat=cat, shown=shown, icon=icon, head=head, sub=sub, body=body, d=d, spill=spill))
    for i, it in enumerate(ex):
        cc = it["cc"]
        rows.append(dict(id=f"R{rnd}N{i+1:02d}", rnd=rnd, kind=it["kind"], ord=i, tkey=it["tkey"], industry=cc["industry"], symbol=cc["symbol"], headline=_fill(it["head"], cc), subhead=_fill(it["sub"], cc),
            body=_fill(it["body"], cc), category=it["cat"], severity=it["sev"], sentiment=it["shown"], icon=it["icon"], impacts=json.dumps(_impacts(rng, comps, cc["code"], it["d"], it["sev"], it["spill"], False))))
    return rows
