import sqlite3, threading, os
DB_PATH = os.environ.get("FINESTRA_DB", os.path.join(os.path.dirname(__file__), "finestra.db"))
LOCK = threading.RLock()
SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE, pw_hash TEXT, salt TEXT);
CREATE TABLE IF NOT EXISTS teams(id TEXT PRIMARY KEY, name TEXT UNIQUE COLLATE NOCASE, leader TEXT, college TEXT, members INTEGER,
  recovery TEXT, status TEXT DEFAULT 'approved', cash REAL, brokerage REAL DEFAULT 0, penalties REAL DEFAULT 0, trades INTEGER DEFAULT 0, prev_rank INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, role TEXT, ref TEXT, created REAL);
CREATE TABLE IF NOT EXISTS companies(symbol TEXT PRIMARY KEY, name TEXT, industry TEXT, start_price REAL, price REAL, prev_price REAL,
  inventory INTEGER, issued INTEGER, volume INTEGER DEFAULT 0, beta REAL, vol REAL, fund REAL, tech REAL, trend TEXT DEFAULT 'Neutral', status TEXT DEFAULT 'Open');
CREATE TABLE IF NOT EXISTS price_history(id INTEGER PRIMARY KEY, symbol TEXT, upd INTEGER, o REAL, h REAL, l REAL, c REAL, v INTEGER);
CREATE TABLE IF NOT EXISTS holdings(team_id TEXT, symbol TEXT, qty INTEGER, avg REAL, PRIMARY KEY(team_id,symbol));
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, client_id TEXT UNIQUE, team_id TEXT, symbol TEXT, side TEXT, qty INTEGER, price REAL, brokerage REAL, mode TEXT, upd INTEGER, ts REAL);
CREATE TABLE IF NOT EXISTS news(id TEXT PRIMARY KEY, kind TEXT, headline TEXT, descr TEXT, category TEXT, industry TEXT, symbols TEXT, direction INTEGER, severity INTEGER, impact REAL, duration INTEGER, release_upd INTEGER, released INTEGER DEFAULT 0, released_upd INTEGER, sens TEXT, release_t REAL);
CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS leaderboard_snapshots(id INTEGER PRIMARY KEY, upd INTEGER, data TEXT);
CREATE TABLE IF NOT EXISTS r2_companies(symbol TEXT PRIMARY KEY, industry TEXT, name TEXT, value INTEGER, start_value INTEGER, ord INTEGER, icon TEXT, code TEXT);
CREATE TABLE IF NOT EXISTS r2_accounts(team_id TEXT PRIMARY KEY, cash INTEGER, start_cash INTEGER, swaps_total INTEGER DEFAULT 1, borrowed INTEGER DEFAULT 0, fees INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS r2_stakes(team_id TEXT, symbol TEXT, bp INTEGER, cost INTEGER, PRIMARY KEY(team_id,symbol));
CREATE TABLE IF NOT EXISTS r2_auctions(id INTEGER PRIMARY KEY, rnd INTEGER, kind TEXT, seller TEXT, symbol TEXT, bp INTEGER, cost INTEGER DEFAULT 0, ask INTEGER DEFAULT 0, status TEXT, high_bid INTEGER DEFAULT 0, high_team TEXT, opened REAL, expires REAL, cd_end REAL, closed REAL, price INTEGER, winner TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS r2_bids(id INTEGER PRIMARY KEY, auction_id INTEGER, team_id TEXT, amount INTEGER, ts REAL);
CREATE TABLE IF NOT EXISTS r2_windows(id INTEGER PRIMARY KEY, rnd INTEGER, team_id TEXT, ord INTEGER, status TEXT, deadline REAL);
CREATE TABLE IF NOT EXISTS r2_swaps(id INTEGER PRIMARY KEY, rnd INTEGER, proposer TEXT, receiver TEXT, give_sym TEXT, give_bp INTEGER, get_sym TEXT, get_bp INTEGER, status TEXT, created REAL, resolved REAL, cash INTEGER DEFAULT 0, expires REAL, note TEXT);
CREATE TABLE IF NOT EXISTS r2_news(id TEXT PRIMARY KEY, rnd INTEGER, kind TEXT, ord INTEGER, tkey TEXT, industry TEXT, symbol TEXT, headline TEXT, subhead TEXT, body TEXT, category TEXT, severity INTEGER, sentiment TEXT, icon TEXT, impacts TEXT, released INTEGER DEFAULT 0, released_at REAL, applied REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS r2_feed(id INTEGER PRIMARY KEY, ts REAL, rnd INTEGER, text TEXT);
CREATE TABLE IF NOT EXISTS r2_values(id INTEGER PRIMARY KEY, symbol TEXT, rnd INTEGER, ts REAL, value INTEGER, cause TEXT);
CREATE TABLE IF NOT EXISTS r2_finish(rnd INTEGER, team_id TEXT, ts REAL, PRIMARY KEY(rnd, team_id));
CREATE TABLE IF NOT EXISTS r2_loans(id INTEGER PRIMARY KEY, team_id TEXT, rnd INTEGER, kind TEXT, amount INTEGER, fee INTEGER DEFAULT 0, ts REAL, outstanding INTEGER);
CREATE TABLE IF NOT EXISTS r2_results(rnd INTEGER PRIMARY KEY, data TEXT);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, ts REAL, actor TEXT, action TEXT, detail TEXT);
"""
def conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c
def init(c):
    c.executescript(SCHEMA)
def get(c, k, d=None):
    r = c.execute("SELECT v FROM settings WHERE k=?", (k,)).fetchone()
    return r["v"] if r else d
def put(c, k, v):
    c.execute("INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))

from contextlib import contextmanager
@contextmanager
def tx(c):
    """Atomic transaction; nests safely inside an already-open one."""
    if c.in_transaction: yield; return
    c.execute("BEGIN IMMEDIATE")
    try:
        yield; c.execute("COMMIT")
    except Exception:
        c.execute("ROLLBACK"); raise
