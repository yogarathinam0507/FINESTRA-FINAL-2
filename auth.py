import hashlib, secrets, hmac, time
def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex(), salt
def check_pw(pw, h, salt):
    return hmac.compare_digest(hash_pw(pw, salt)[0], h)
def new_session(c, role, ref=""):
    t = secrets.token_urlsafe(32)
    c.execute("INSERT INTO sessions VALUES(?,?,?,?)", (t, role, ref, time.time()))
    return t
def who(c, token):
    if not token: return None
    r = c.execute("SELECT role,ref FROM sessions WHERE token=?", (token,)).fetchone()
    return dict(r) if r else None
