// ===== ROUND 2 – Industry Titans: The Stake Auction (views) =====
const PHN = {newsletter: 'NEWSLETTER / NEWS PROJECTION', discussion: 'STRATEGY & DISCUSSION – bidding disabled', auction: 'LIVE STAKE AUCTION'};
const sg = n => n.sentiment == 'Positive' ? 'pos' : n.sentiment == 'Negative' ? 'neg' : 'mix';
const arrow = n => n.sentiment == 'Positive' ? '▲' : n.sentiment == 'Negative' ? '▼' : '◆';

function r2LB(rows, admin) {
    return `<table><tr><th>Rank</th><th class="l">Team</th><th>Portfolio value</th><th>Growth</th>${admin ? '<th>Capital growth /50</th><th>Participation /20</th><th>Swap &amp; Sell /20</th><th>Diversif. /10</th>' : ''}<th>Round 1 Points</th><th>Round 2 Points</th><th>Overall Points</th></tr>${rows.map(r => `<tr style="${r.rank<=3?'font-weight:700;background:var(--bg)':''}"><td>${['🥇','🥈','🥉'][r.rank-1]||r.rank}</td><td class="l">${esc(r.team)}</td><td>${inr(r.value)}</td><td class="${cls(r.growth_pct)}">${r.growth_pct}\%</td>${admin&&r.parts?`<td>${r.parts.growth}</td><td>${r.parts.participation}</td><td>${r.parts.swap_sell}</td><td>${r.parts.diversification}</td>`:''}<td>${r.r1}</td><td>${r.r2}</td><td><b>${r.overall}</b></td></tr>`).join('')}</table>`;
}

function newsCard(n) {
    const c = sg(n), d = new Date((n.released_at || Date.now() / 1000) * 1000), co = (R.companies || []).find(x => x.symbol == n.symbol);
    return `<article class="pc ${c} ${n.kind=='future'?'fut':''}"><div class="top"><span>${n.icon} ${esc(n.industry)}</span>${n.kind=='future'?'<span class="chip on">OUTLOOK · NEXT ROUND</span>':''}<span>${esc(n.category)}</span><span>Severity ${'●'.repeat(n.severity)}${'○'.repeat(3-n.severity)}</span></div><h2>${esc(n.headline)}</h2><h4>${esc(n.subhead)}</h4><p>${esc(n.body)}</p>
    <div class="foot"><b>FINestra Financial Desk</b><span>${d.toLocaleDateString([], {day:'2-digit',month:'short',year:'numeric'})} · ${d.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}</span><span class="sent ${c}">${arrow(n)} Sentiment: ${n.sentiment}</span><span>Company: ${esc(co?co.name:n.symbol)} (${n.symbol})</span></div></article>`;
}

const roundNews = k => (R.news || []).filter(n => n.rnd == S.round && n.kind == k && n.released).sort((a, b) => a.ord - b.ord);

function newspaper() {
    const a = roundNews('now'), f = roundNews('future');
    return `<div class="paper"><div class="mast"><small>FINESTRA FINANCIAL DESK · INDUSTRY TITANS EDITION · AUCTION ROUND ${S.round}</small><h1>THE FINESTRA FINANCIAL TIMES</h1><small>${a.length+f.length} / 10 items · ${a.length} / 6 current-round events · ${f.length} / 4 outlooks for the NEXT auction round</small></div>
    <h3 class="sec">📰 CURRENT NEWS – already reflected in today's valuations</h3><div class="papergrid">${a.map(newsCard).join('')||'<p>The newsletter is being prepared…</p>'}</div>
    <h3 class="sec">🔮 OUTLOOK – hints about what may move valuations in the NEXT auction round</h3><div class="papergrid">${f.map(newsCard).join('')||'<p>Outlook pieces arrive during the newsletter…</p>'}</div></div>`;
}

function stageBanner() {
    const ph = S.phase;
    return `<div class="stage"><h2>${esc(S.label)}</h2><span class="chip on">${S.stage=='r2pre'?'PRELIMINARY AUCTION':PHN[ph]||ph}</span><div class="t" id="pc">${mm(Math.max(0,S.phase_end-S.elapsed)/(S.scale||1))}</div></div>`;
}

function bump(n) {
    const e = $('#bidamt');
    if (!e) return;
    e.value = n == 'min' ? R.auction.min_bid : (+e.value || R.auction.min_bid) + n;
    FORM.bidamt = e.value;
}

async function bid() {
    try {
        await api('r2/bid', {auction_id: R.auction.id, amount: +$('#bidamt').value});
        delete FORM.bidamt;
        toast('Bid placed');
        await refresh();
    } catch(e) { toast(e.message); }
}

function auctionPanel(big) {
    const A = R.auction, meid = R.me && R.me.team_id, ph = S.phase;
    if (!A) return `<div class="card live"><h3>LIVE AUCTION</h3><div class="big" style="color:var(--mut)">${ph!='auction'?'Auction opens after the discussion phase':R.window?esc(R.window.name)+' – selling window is open':S.stage=='r2pre'&&!R.lots_left?'Preliminary lots exhausted':'Waiting for the next offer…'}</div></div>`;
    const cd = A.status == 'countdown', key = A.id + ':' + A.min_bid;
    if (FORM._aid !== key) { FORM._aid = key; delete FORM.bidamt; }
    const can = role == 'team' && R.me && R.me.participant && meid != A.seller && meid != A.high_team && ph == 'auction';
    return `<div class="card live ${cd?'hot':''}"><h3>LIVE AUCTION · ${A.kind=='prelim'?'Preliminary lot':'Team offer'} <span class="chip ${cd?'on':''}">${cd?'⏱ COUNTDOWN – going once…':'OPEN FOR BIDS'}</span></h3>
    <div class="big">${esc(A.company)} <small style="font-size:16px;color:var(--mut)">${esc(A.industry)}</small></div>
    <div class="kv"><div><span>Stake offered</span><b>${A.pct}%</b></div><div><span>Selling team</span><b>${esc(A.seller_name)}</b></div><div><span>Starting price</span><b>${inr(A.ask)}</b></div><div><span>Current highest bid</span><b>${A.high_bid?inr(A.high_bid):'—'}</b></div><div><span>Highest bidder</span><b>${A.high_name?esc(A.high_name):'—'}</b></div><div><span>Last bid</span><b>${A.last_bid?inr(A.last_bid)+' · '+esc(A.last_bid_team):'—'}</b></div><div><span>Indicative fair value</span><b>${inr(A.fair_value)}</b></div><div><span>Auction status</span><b>${cd?'Countdown':'Open – lapses in <span id="aex">'+mm(rem(A.expires))+'</span>'}</b></div></div>
    ${cd?`<div class="cdn" id="acd">${Math.min(10,Math.max(0,Math.ceil(rem(A.cd_end))))}</div><div style="text-align:center;color:var(--mut)">No higher bid before zero → stake is awarded to ${esc(A.high_name)}. Any higher bid resets the countdown to 10.</div>`:''}
    ${can?`<div class="row" style="margin-top:10px"><input id="bidamt" type="number" step="10000" value="${A.min_bid}" style="width:170px;font-size:18px"><button class="g" onclick="bump('min')">Min</button><button class="g" onclick="bump(50000)">+₹50K</button><button class="g" onclick="bump(100000)">+₹1L</button><button class="g" onclick="bump(500000)">+₹5L</button><button class="s" style="font-size:18px;padding:10px 26px" onclick="bid()">PLACE BID</button></div><small style="color:var(--mut)">Minimum next bid ${inr(A.min_bid)} · your buying capacity ${inr(R.me.capacity)}</small>`:role=='team'&&meid==A.high_team?'<div class="chip on" style="margin-top:10px">You are the highest bidder</div>':''}
    </div>`;
}

function fillAsk() {
    const st = (R.me.stakes || []).find(x => x.symbol == $('#sl_sym').value);
    if (!st) return;
    const v = Math.round(st.value * ((+$('#sl_pct').value || 0) / st.pct) / 1000) * 1000;
    $('#sl_ask').value = v;
    FORM.sl_ask = v;
}

async function sellNow() {
    try {
        await api('r2/sell', {symbol: $('#sl_sym').value, pct: +$('#sl_pct').value, ask: +$('#sl_ask').value});
        delete FORM.sl_pct; delete FORM.sl_ask;
        toast('Offer is live');
        await refresh();
    } catch(e) { toast(e.message); }
}

async function passNow() {
    try {
        await api('r2/pass', {});
        toast('You passed');
        await refresh();
    } catch(e) { toast(e.message); }
}

function windowPanel() {
    const W = R.window, me = R.me;
    if (!W || S.phase != 'auction' || S.stage == 'r2pre') return '';
    if (W.status == 'offered') return `<div class="window"><h2>${esc(W.name)} has offered a stake</h2>Bidding is open.</div>`;
    if (role == 'team' && me && W.team == me.team_id) {
        const st = me.stakes || [], s0 = st[0];
        return `<div class="window"><h2>${esc(W.name)} – YOUR SELLING SESSION</h2><div>Decide within <b id="wcd">${mm(rem(W.deadline))}</b></div>
        <div class="row" style="justify-content:center;margin-top:8px"><select id="sl_sym" onchange="fillAsk()" style="width:auto">${st.map(x=>`<option value="${x.symbol}">${esc(x.company)} (${x.pct}% held)</option>`).join('')}</select><input id="sl_pct" type="number" step="5" min="5" max="100" value="${s0?Math.min(5,s0.pct):''}" oninput="fillAsk()" style="width:90px"><span>% stake</span><input id="sl_ask" type="number" step="10000" value="${s0?Math.round(s0.value*Math.min(5,s0.pct)/s0.pct/1000)*1000:''}" style="width:150px"><span>₹ starting price</span></div>
        <div class="row" style="justify-content:center"><button class="s" style="font-size:18px;padding:10px 26px" onclick="sellNow()">OFFER FOR SALE</button><button class="g" style="font-size:18px;padding:10px 26px" onclick="passNow()">DONE / PASS</button></div></div>`;
    }
    return `<div class="window"><h2>${esc(W.name)} – SELLING SESSION</h2>deciding… <b id="wcd">${mm(rem(W.deadline))}</b></div>`;
}

const nm = sym => ((R.companies || []).find(x => x.symbol == sym) || {}).name || sym;
const val = (sym, pct) => {
    const c = (R.companies || []).find(x => x.symbol == sym);
    return c ? Math.round(c.value * pct / 100) : 0;
};

async function swapGo() {
    try {
        const d = +$('#sw_cd').value, amt = +$('#sw_ca').value || 0;
        await api('r2/swap/propose', {receiver: $('#sw_to').value, give_symbol: $('#sw_g').value, give_pct: +$('#sw_gp').value, get_symbol: $('#sw_r').value, get_pct: +$('#sw_rp').value, cash: d * amt});
        ['sw_gp', 'sw_rp', 'sw_ca'].forEach(k => delete FORM[k]);
        toast('Swap proposed');
        await refresh();
    } catch(e) { toast(e.message); }
}

async function swapAns(id, a) {
    try {
        await api('r2/swap/' + id + '/' + a, {});
        toast('Swap updated');
    } catch(e) { toast(e.message); }
    await refresh();
}

function swSum() {
    const e = $('#sw_sum');
    if (!e) return;
    const g = val($('#sw_g').value, +$('#sw_gp').value || 0), r = val($('#sw_r').value, +$('#sw_rp').value || 0);
    e.textContent = `You give ≈ ${inr(g)} · you get ≈ ${inr(r)}`;
}

function swapCard(w, me) {
    const mine = w.proposer == me.team_id, st = w.status;
    return `<div class="flash" style="border-color:${st=='accepted'?'var(--up)':st=='pending'?'#ff9f1a':'var(--mut)'}"><div><b>${esc(w.proposer_name)}${mine?' (you)':''}</b> gives <b>${w.give_bp/100}% ${esc(nm(w.give_sym))}</b> ⇄ <b>${esc(w.receiver_name)}${!mine?' (you)':''}</b> gives <b>${w.get_bp/100}% ${esc(nm(w.get_sym))}</b><br>
    <span class="chip ${st=='pending'?'on':''}">${st.toUpperCase()}</span>
    ${st=='pending'&&!mine?`<button class="s" onclick="swapAns(${w.id},'accept')">ACCEPT</button> <button class="r" onclick="swapAns(${w.id},'reject')">REJECT</button>`:''}${st=='pending'&&mine?`<button class="g" onclick="swapAns(${w.id},'cancel')">WITHDRAW</button>`:''}</div></div>`;
}

function swapPanel() {
    const me = R.me, sw = R.swaps || [], others = Object.entries(R.teams).filter(([id]) => id != me.team_id), pend = sw.filter(w => w.status == 'pending'), mineP = pend.filter(w => w.proposer == me.team_id);
    const to = others.some(([id]) => id == FORM.sw_to) ? FORM.sw_to : (others[0] || [])[0], theirs = (R.holdings[to] || []), ok = me.can_act && me.swaps_left > 0 && !mineP.length && others.length && (me.stakes || []).length && theirs.length;
    return `<div class="card"><h3>STAKE SWAP · remaining: <b>${me.swaps_left} of ${me.swaps_total}</b></h3>
    ${pend.filter(w => w.receiver == me.team_id).map(w => swapCard(w, me)).join('')}
    <div class="row" style="margin-top:8px"><span>I give</span><select id="sw_g" style="width:auto">${(me.stakes || []).map(x=>`<option value="${x.symbol}">${esc(x.company)} (${x.pct}% held)</option>`).join('')||'<option value="">no stakes</option>'}</select><input id="sw_gp" type="number" step="5" min="5" max="100" placeholder="% I give" oninput="swSum()" style="width:90px"><b>⇄</b>
    <select id="sw_to" onchange="render()" style="width:auto">${others.map(([id,n])=>`<option value="${id}">${esc(n)}</option>`).join('')}</select><select id="sw_r" onchange="swSum()" style="width:auto">${theirs.map(x=>`<option value="${x.symbol}">${esc(x.company)} (${x.pct}% held)</option>`).join('')||'<option value="">no stakes</option>'}</select><input id="sw_rp" type="number" step="5" min="5" max="100" placeholder="% I get" oninput="swSum()" style="width:90px"></div>
    <div class="row"><span>Cash adj.</span><select id="sw_cd" onchange="swSum()" style="width:auto"><option value="0">none</option><option value="1">I add cash</option><option value="-1">they add cash</option></select><input id="sw_ca" type="number" step="10000" min="0" placeholder="₹ amount" oninput="swSum()" style="width:140px"><button ${ok?'':'disabled'} onclick="swapGo()">PROPOSE SWAP</button></div><div id="sw_sum" style="font-size:12px;color:var(--mut);margin:4px 0"></div>
    ${sw.filter(w => !(pend.includes(w) && w.receiver == me.team_id)).slice(0, 6).map(w => swapCard(w, me)).join('')}</div>`;
}

async function finishGo() {
    try {
        await api('r2/finish', {});
        toast('Marked as finished');
        await refresh();
    } catch(e) { toast(e.message); }
}

function finishPanel() {
    const f = R.finish || {done: 0, total: 0};
    return `<div class="card"><h3>FINISH ROUND <span class="chip ${f.me?'on':''}">${f.done} / ${f.total} ready</span></h3><div class="row" style="margin-top:8px"><button ${f.me||!R.me.can_act?'disabled':''} onclick="finishGo()">${f.me?'✔ FINISHED':'FINISH ROUND'}</button></div></div>`;
}

async function borrowGo() {
    try {
        const r = await api('r2/borrow', {amount: +$('#bw_amt').value});
        delete FORM.bw_amt;
        toast('Borrowed ' + inr(r.amount));
        await refresh();
    } catch(e) { toast(e.message); }
}

async function repayGo(all) {
    try {
        const m = R.me, amt = all ? Math.min(m.borrowed, m.capacity) : +$('#bw_rp').value;
        const r = await api('r2/repay', {amount: amt});
        delete FORM.bw_rp;
        toast('Repaid ' + inr(r.amount));
        await refresh();
    } catch(e) { toast(e.message); }
}

function bwSet(n) { const e = $('#bw_amt'); e.value = n; FORM.bw_amt = n; }

function borrowPanel() {
    const m = R.me, ok = m.can_act;
    return `<div class="card"><h3>EXTRA CASH · BORROWING <span class="chip ${m.borrowed>0?'on':''}">${m.borrowed>0?'DEBT '+inr(m.borrowed):'NO DEBT'}</span></h3>
    <div class="live"><div class="kv"><div><span>Spendable cash</span><b>${inr(m.cash)}</b></div><div><span>Outstanding debt</span><b class="${m.borrowed>0?'dn':''}">${inr(m.borrowed)}</b></div><div><span>Can borrow</span><b>${inr(m.borrow_room)}</b></div></div></div>
    <div class="row" style="margin-top:8px"><input id="bw_amt" type="number" step="10000" min="10000" placeholder="₹ to borrow" style="width:150px"><button class="g" onclick="bwSet(${m.borrow_room})">Max</button><button ${ok&&m.borrow_room>0?'':'disabled'} onclick="borrowGo()">BORROW</button>
    <span style="width:18px"></span><input id="bw_rp" type="number" step="10000" min="10000" placeholder="₹ to repay" style="width:150px"><button class="g" ${ok&&m.borrowed>0?'':'disabled'} onclick="repayGo(false)">REPAY</button></div></div>`;
}

function stakeBoard() {
    const hs = R.holdings, me = R.me && R.me.team_id;
    return `<div class="card"><h3>TEAM STAKE BOARD</h3><div class="grid g3">${Object.entries(R.teams).map(([id, n])=>`<div class="tb ${id==me?'me':''}"><h4>${esc(n)}${id==me?' (you)':''}</h4>${(hs[id]||[]).map(x=>`<div class="st"><span>${esc(x.industry)}</span><b>${x.pct}%</b></div>`).join('')||'<small style="color:var(--mut)">No stakes</small>'}</div>`).join('')}</div></div>`;
}

const feedBox = () => `<div class="card"><h3>AUCTION ACTIVITY FEED</h3><div class="feed">${(R.feed || []).map(f => `<div><small>${new Date(f.ts*1000).toLocaleTimeString()}</small>${esc(f.text)}</div>`).join('') || 'Nothing yet'}</div></div>`;
const valTable = () => `<div class="card"><h3>Company valuations</h3><table><tr><th class="l">Industry</th><th class="l">Company</th><th>Valuation</th><th>Change</th></tr>${R.companies.map(x=>`<tr><td class="l">${x.icon}${esc(x.industry)}</td><td class="l">${esc(x.name)}</td><td>${inr(x.value)}</td><td class="${cls(x.change_pct)}">${x.change_pct}%</td></tr>`).join('')}</table></div>`;

function r2TeamView() {
    const me = R.me;
    if (!me || !me.participant) return r2SpecView(`<div class="bar" style="background:#7a5cff;color:#fff">Spectator mode</div>`);
    const ph = S.phase, rows = me.stakes || [], kp = [['Cash', inr(me.cash)], ['Stakes', inr(me.held)], ['Portfolio', inr(me.value)], ['Growth', me.growth_pct + '%', me.growth_pct], ['Overall', me.points.overall]];

    let privNewsHtml = '';
    if (ph == 'discussion' && me.private_news && me.private_news.length > 0) {
        privNewsHtml = `
            <div class="card" style="border: 2px solid #ff9f1a; background: var(--paper); margin-bottom: 12px;">
                <h3 style="color: #ff9f1a; margin-bottom: 6px;">🔒 CONFIDENTIAL PRIVATE INTELLIGENCE (Discussion Phase)</h3>
                <ul style="margin: 0; padding-left: 18px; font-family: Georgia, serif; font-size: 14.5px; line-height: 1.5;">
                    ${me.private_news.map(item => `<li style="margin-bottom: 6px;">${esc(item)}</li>`).join('')}
                </ul>
            </div>
        `;
    }

    let main = '';
    if (S.stage == 'r2pre') main = `<div class="card"><h3>Preliminary auction</h3>Each company is auctioned as a 100% stake (${R.lots_left} lots left).</div>${auctionPanel()}`;
    else if (ph == 'newsletter') main = newspaper();
    else if (ph == 'discussion') main = `${privNewsHtml}<div class="card"><h3>Discussion time</h3><p>Review your intelligence and plan your strategy.</p></div>${valTable()}${newspaper()}`;
    else main = `${windowPanel()}${auctionPanel()}`;

    if (S.stage != 'r2pre') main += `${finishPanel()}<div class="grid gh">${swapPanel()}${borrowPanel()}</div>`;

    H(head(`<span class="pill">${esc(R.teams[me.team_id] || '')}</span>`) + `<main>${stageBanner()}<div class="grid g4" style="margin:12px 0">${kp.map(k=>`<div class="card kpi"><h3>${k[0]}</h3><b class="${k[2]!=null?cls(k[2]):''}">${k[1]}</b></div>`).join('')}</div>
    <div class="grid" style="gap:12px">${main}${stakeBoard()}<div class="grid gh"><div class="card"><h3>My stake holdings</h3><table><tr><th class="l">Industry</th><th class="l">Company</th><th>Stake %</th><th>Current value</th></tr>${rows.map(x=>`<tr><td class="l">${esc(x.industry)}</td><td class="l">${esc(x.company)}</td><td>${x.pct}\%</td><td>${inr(x.value)}</td></tr>`).join('')||'<tr><td colspan=4>No stakes yet</td></tr>'}</table></div>${valTable()}</div>
    <div class="grid gh">${feedBox()}<div class="card"><h3>Round 2 leaderboard</h3>${r2LB(R.leaderboard)}</div></div></div></main>${WM}`);
}

function r2SpecView(banner) {
    const heads = (R.news || []).filter(n => n.released).slice(0, 4), ph = S.phase, pre = S.stage == 'r2pre';
    const mid = pre || ph == 'auction' ? auctionPanel(true) + windowPanel() : ph == 'newsletter' ? newspaper() : `<div class="card"><h3>Discussion time</h3></div>${valTable()}`;
    H(head() + (banner || '') + `<main class="${role=='spectator'?'big':''}">${stageBanner()}<div class="grid" style="gap:12px;margin-top:12px">${mid}
    <div class="card"><h3>Round 2 leaderboard</h3>${r2LB(R.leaderboard)}</div>${stakeBoard()}<div class="grid gh">${feedBox()}</div></div></main>${WM}`);
}

async function r2cfg() {
    try {
        await api('r2/org/config', {companies: R.companies.map(x => ({symbol: x.symbol, name: $('#c_n_' + x.symbol).value, industry: $('#c_i_' + x.symbol).value, value: +$('#c_v_' + x.symbol).value}))});
        FORM = {};
        toast('Industries saved');
        await refresh();
    } catch(e) { toast(e.message); }
}

async function r2act(p, b) {
    try {
        const r = await api('r2/' + p, b || {});
        await refresh();
        return r;
    } catch(e) { toast(e.message); }
}

function orgR2() {
    if (!R) return '';
    const live = R2LIVE.includes(S.stage), started = live || BRK.includes(S.stage) || S.stage == 'ended', A = R.auction;
    return `<div class="card" style="margin-top:12px"><h3>ROUND 2 – Industry Titans · control centre</h3>
    <div class="row"><button class="g" onclick="r2act('org/news/toggle',{on:${!R.newsletter_on}})">${R.newsletter_on?'Stop':'Start'} newsletter</button><button class="g" onclick="r2act('org/news/release')">Release news</button>
    <button class="r" ${A?'':'disabled'} onclick="r2act('org/auction/cancel')">Cancel auction</button><button class="s" ${A?'':'disabled'} onclick="r2act('org/auction/force')">Force complete</button></div></div>`;
}
