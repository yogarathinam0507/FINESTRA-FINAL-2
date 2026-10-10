# FINestra @Doms, AU – Real-Time Stock Market & Stake-Auction Simulator
© FINestra @Doms, AU · SIMULATION DATA – NOT REAL SECURITIES

## Setup (Windows, one time, needs internet)
1. Install Python 3.10+ from python.org (tick **Add Python to PATH**).
2. In the project folder: `pip install -r requirements.txt`
3. Start: `python server.py` (prints the URLs). Charts and sounds are bundled/synthesised – **no internet needed during the event**.
4. Organizer laptop IP: `ipconfig` → IPv4 Address. Firewall (Admin cmd): `netsh advfirewall firewall add rule name="FINestra" dir=in action=allow protocol=TCP localport=8000`
5. Everyone on the same Wi-Fi. Teams: `http://<IP>:8000` · Spectator display: `http://<IP>:8000/spectator` · Organizer: `http://localhost:8000`
6. Organizer login **organizer / admin123** (change it in the dashboard). Spectator code **SPECTATE**. Teams register themselves and get a Team ID + recovery code.

## The event (fully automatic once the organizer presses Start)
| Stage | Length | What happens |
|---|---|---|
| TEST ROUND | 5:00 | Same trading screen as Round 1 (44 s updates). Nothing counts – **all test data is wiped** when Round 1 begins |
| **ROUND 1 – Market Masters** | 45:00 | Opening bell. 15 stocks, brokerage 0.10%, **no intraday**. Prices every **44 s**; a sudden market event about every **4 min** (mostly downside, some relief); **final 5 min**: FINAL 5 MINUTES banner + warning sound, prices every **30 s**, a news card each minute, countdown ticks. Trading stops and results freeze at 45:00 |
| Transition | 1:00 | Round 1 final standings |
| **ROUND 2 – Industry Titans: The Stake Auction** | | Bell. Top **5** Round-1 teams (setting *Teams in Round 2*), **₹1 Crore each**, 8 industries / 8 companies |
| Preliminary auction | 10:00 | Promoter stakes (2 × 10% lots per company) are auctioned lot by lot to create the first holdings |
| Auction Rounds 1–3 (1:00 break between) | 3 × 15:00 | **Newsletter 2:00** (10 newspaper-style stories) → **Discussion 3:00** (calm: no news cards, bidding disabled) → **Stake Auction 10:00** |
| Final results | | Podium, Round 2 leaderboard, Round 1 standings, CSV exports |

≈ 109 minutes in total. The organizer can **Pause / Resume / Skip to next stage / Start Round 2 now / End / Restart** at any time. Rehearsal: set **Time scale** to 20 (whole event ≈ 5.5 min) or 200 (≈ 33 s).

## Round 1
15 fictional stocks: 12 industry stocks (2 in each of 6 industries) + 3 commodity-linked stocks (Gold, Crude, Industrial Metals). Commodities have their own factors – e.g. Gold has a negative beta and *rises* in risk-off shocks while equities fall. Candlestick charts, fundamentals, indicators, news, leaderboard, 100-point scoring, delete-team and restart are unchanged.

## Round 2 rules (enforced on the server inside database transactions)
* **Selling windows** (auction phase): teams are called in random order; each gets **one** window per round to **SELL** a % of a stake it holds (choosing a starting price) or **PASS** (or run out of time). Teams with no stakes are skipped. The offered stake is held in escrow, so it cannot be sold or swapped twice.
* **Buying:** any other team may bid repeatedly, up to its cash. Minimum raise = max(₹10,000, 2%). The first bid starts a **10-second countdown**; a higher bid **resets** it; at zero the stake goes to the highest bidder – cash moves, ownership transfers, the sale is logged (audit log + feed) and a win sound plays. No bid within the offer window (default 30 s) → the offer lapses and the stake returns.
* **Swap:** **1 per team per auction round**. The proposer offers x% of its stake for y% of another team's stake; the receiver must **Accept** or **Reject** (never automatic). Acceptance moves both stakes atomically and uses up the swap for **both** teams.
* **Public information:** every team sees all teams' stake percentages (Team Stake Board), the latest transaction and the live auction. Other teams' cash is not shown.
* **Newsletter & prices:** each news card carries *hidden* per-company impacts that are never sent to teams. On release 50% of the impact is applied to the company valuation; the rest is applied when the round closes – so valuations change **every round, driven by the news**. Some "Mixed" stories are deliberately ambiguous. Team value = cash + Σ stake % × valuation, so portfolio value and capital growth update automatically.

### Round 2 scoring (100 points, shown on the Round 2 leaderboard)
| Component | Pts | Formula |
|---|---|---|
| Capital growth | 50 | growth = value / ₹1 Cr − 1; −10% → 0, +30% → 50 (linear, clamped) |
| Auction participation | 20 | 20 × min(1, (auctions bid on + 2 × purchases + 2 × sell offers) / 12) |
| Use of Swap & Sell | 20 | 10 × min(1, (sales completed + ½ unsold offers) / 3) + 10 × min(1, (swaps completed + ½ proposals not completed) / 3) |
| Diversification | 10 | 10 × min(1, industries held / 5), reduced by up to 50% if one industry exceeds 40% of holdings |

## Organizer dashboard
Event flow chips; Settings (all durations, lot sizes, capital, *Teams in Round 2* …); **Round 2 control centre** – edit the 8 industries/companies/valuations (before Round 2), start/stop newsletter, release newsletter now, generate a fresh newsletter, cancel / force-complete a live auction, per-team cash/stakes/score, selling-window order, bids, auction history, swaps, all news with hidden impacts, audit log, CSV export. Restart needs typing RESTART and saves a backup in `backups/`.

## Sounds
Synthesised in the browser (no audio files): opening bell (Round 1, Round 2, each auction round), 10-second auction ticks, final-10-second ticks, FINAL 5 MINUTES warning, sudden-event alert, bid and win chimes. The 🔊 button mutes. If the browser blocks audio until the first click, the app still works and sound starts after the first click/keypress.

## Honest notes
* **The "AI-generated" news is produced by an offline template engine** (18 big-story templates × 8 industries, 8 flash templates, with spill-over to related industries) written in a financial-journalism style. There is no live LLM call, so it works without internet. "Generate AI news" re-rolls rounds that have not started.
* If more teams than *Teams in Round 2* register, the others watch Round 2 as spectators.
* Tests: `python -m pytest tests -q` (43 tests, including a bot-driven simulation of the entire event).


---
## Update – Round 1 & Round 2 (FINestra @Doms, AU)

**Round 1 (40 min, test round 5 min unchanged)**
- First 30 min: price update every 45 s · surprise market event every 4 min (3:00, 7:00 … 27:00). *(The regular 2-minute news cards were removed – see the bug-fix update below.)*
- Every news card / surprise event / mega event is announced by a large full-screen banner 10 s before it lands ("NEWSLETTER INCOMING", etc.).
- Last 10 min: price update every 30 s · no regular news · MEGA events at exactly 31:00 and 36:00 (very large, sector-rotating moves) · team dashboard switches to **Fast Trading Mode** (one-tap BUY/SELL, order-size presets, live clock and update countdown).
- After Round 1 the break is **unlimited**: nothing starts until the organizer presses **START ROUND 2**.

**Round 2**
- Preliminary: ₹1 Cr per team, each company auctioned as a **100% stake**; every team must own at least one company (bids that would starve another team are refused; a safety net allocates a company at close if needed). Ends early when everything is placed. 1-min break.
- 3 auction rounds: newsletter 2 min → discussion 3 min → live auction 10 min → 1 min break. The auction ends early once every team has finished its selling session.
- Newsletter = 10 items: 6 present events (re-price companies immediately) + 4 future/outlook items (hints; their price effect lands when the next round starts; Round 3's land in the final settlement).
- Stakes trade only in 5% steps. One selling session per team per round. Swaps only inside your own session; rank #1 after Round 1 has 2 swaps for the whole of Round 2, everyone else 1. A rejected swap is not consumed and gives no extra selling session; only the initiator uses a swap when it succeeds.
- Points: Round 2 = Capital Growth 50 + Participation 20 + Swap & Sell 20 + Diversification 10. **Overall = Round 1 points + Round 2 points.** Teams only see Round 1 / Round 2 / Overall points; the organizer sees the full breakdown.
- After Round 3 the event ends automatically and the Top-5 final leaderboard (🥇🥈🥉 4th 5th, team name + overall points) is shown.

**Registration fix:** `static/app.js` no longer reads form fields through global ids (a function named `tn` in `sound.js` hid the Team-name input); the server also accepts alternative field names. Teams are stored in SQLite and survive restarts.

**Interpretations to confirm:** "31st/36th minute" = clock reads 31:00 / 36:00; surprise events are offset 1 min from news cards so they never collide; company valuations were lowered to ₹45–70 L so a 100% stake is affordable with ₹1 Cr; the first run of this version resets event state once (teams are kept).


---
## Bug-fix & gameplay update (supersedes anything above that conflicts)

**1. Candlestick chart** – the whole page used to be rebuilt (and the chart redrawn from scratch) on every WebSocket push and every 5-second poll. Now the chart is **one persistent object**: its DOM node is re-inserted after a page refresh, the page is not re-rendered at all when nothing changed, and live data arrives through `GET /api/chart/{symbol}?since=N` (only the newest candle(s)) and is applied with `series.update()`. Zoom, pan, crosshair and the chosen **timeframe** (every update / 2 / 4 / 8 updates, buttons above the chart) are kept; the chart is only re-fitted on first open, when you change the timeframe, or when the server wipes the price history (restart / new round – detected through `epoch`). An OHLC legend follows the crosshair.

**2. Round 1 events** – regular 2-minute news cards are gone (also from the database, banners and UI). Remaining: a **surprise market event every 4 minutes** (3:00 … 27:00) plus the two MEGA events (31:00, 36:00). The 7 timed events hit each of the 6 industries + the commodity group exactly once with a large single-sector impact (≈4 % per update for 4 updates on the target stocks, only small spill-over); 5 positive / 2 negative. MEGA: one panic (negative), one stimulus rotation (positive). The manual surprise pool is 14 positive / 6 negative. Overall ≈ 70 % positive.

**3. Round 2 newsletter** – exactly **10 items per auction round: 6 current-round events + 4 next-round outlooks**, always **7 positive / 3 negative**, no "Mixed" stories any more (shown sentiment = real price direction). Every industry appears in every newsletter, at least twice as current news and at least once as an outlook over the three rounds. Outlooks move the relevant (and spill-over) valuations when the **next auction round starts** (Round 3's at the final settlement); a feed line tells everyone when they have played out.

**4. Swaps (rebuilt)** – a swap can be proposed **at any time during an auction round** (newsletter, discussion or live auction), as long as swaps are left (rank #1 after Round 1: 2, everyone else: 1; only a *completed* swap uses one up). Rules enforced on the server: valid 5 % steps, two different companies, both sides must really hold the stakes (a stake on offer in the auction cannot be swapped), no duplicate / mirror proposals, one pending proposal per team, proposals lapse after *swap validity* (default 180 s) and can be withdrawn. **Nothing moves until the other team confirms.** On confirmation everything is re-validated and both stakes (and an optional **cash adjustment** – the way a cash-short buyer can pay with a stake) move in ONE transaction; if anything is no longer valid the proposal expires and nothing moves. All dashboards update immediately. (Old bug: a failed acceptance rolled back its own "expired" status, so the proposal stayed clickable forever; and swaps were only possible inside your own selling session.)

**5. Borrowing** – each team may borrow up to **₹30 lakh per auction round** (multiples of ₹10,000; repaying does not restore the round's allowance). Funds are tracked separately (`borrowed`, ledger table `r2_loans`) and shown as *Outstanding borrowing*. Cost: a **5 % fee** on every draw, and **−1 point per ₹3 lakh still owed** when scoring (max −30). Team value = cash + stakes − outstanding borrowing, so borrowed money is never double counted. Cash promised in a live bid cannot be repaid or lent twice. Limit, fee and penalty are organizer settings (locked once the event starts).

**6. Scoreboard** – fixed: a stake on offer in the auction used to vanish from its owner's value/diversification while the auction ran; borrowing is netted; Round 1 no longer gives free hard-coded points for not trading (discipline 10, risk 5); deactivated teams are no longer ranked; ties share a rank instead of an invented order; the borrowing penalty is part of Round 2 points. Rankings come from one backend function and are pushed to all dashboards at once.

**7. Discussion** – nothing is released automatically during the discussion (the newsletter is only released during the newsletter phase; a one-time catch-up covers a server stall). The spectator screen shows a calm "Discussion time" panel; the unused flash-card code was removed.

Organizer settings added: borrowing limit / fee / penalty unit, swap validity. CSV export has borrowing and swap-cash columns.

### Follow-up fixes
- **Swap "Method Not Allowed"** – accept / reject / withdraw were sent as a body-less request, which the browser makes a GET, while the server only accepts POST (HTTP 405). They are now POST requests.
- **Round no longer ends when the last selling session ends.** It runs until the timer is over, or until **every team has pressed "Finish round" and no swap is pending** (a team with its own pending proposal must wait/withdraw first). Swaps and borrowing stay available meanwhile.
- **Chart self-healing** – every 60 s (and when the tab becomes visible or the network returns) the chart is re-measured and its data reloaded in place, keeping zoom/pan; a failed update triggers a full reload on the next sync.
