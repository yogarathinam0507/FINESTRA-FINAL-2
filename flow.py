"""Event timeline: TEST -> ROUND 1 -> transition -> ROUND 2 (preliminary + 3 auction rounds). All values in event-seconds."""
import database as D
ORDER = ['test', 'r1', 'trans1', 'r2pre', 'brk0', 'a1', 'brk1', 'a2', 'brk2', 'a3']
R2_STAGES = ('r2pre', 'a1', 'a2', 'a3'); BREAKS = ('brk0', 'brk1', 'brk2')
ROUND_OF = {'r2pre': 0, 'a1': 1, 'a2': 2, 'a3': 3}
LABELS = {'idle': 'EVENT NOT STARTED', 'test': 'TEST ROUND', 'r1': 'ROUND 1 – Market Masters', 'trans1': 'BREAK – waiting for the organizer to start Round 2',
  'r2pre': 'ROUND 2 – Industry Titans: Preliminary Auction', 'brk0': 'BREAK – Auction Round 1 next', 'a1': 'ROUND 2 – Industry Titans: Auction Round 1',
  'brk1': 'BREAK – Auction Round 2 next', 'a2': 'ROUND 2 – Industry Titans: Auction Round 2', 'brk2': 'BREAK – Auction Round 3 next',
  'a3': 'ROUND 2 – Industry Titans: Auction Round 3', 'ended': 'EVENT COMPLETE – Final Results'}
def dur(c):
    g = lambda k: float(D.get(c, k)); a = g('news_sec') + g('disc_sec') + g('auc_sec')
    return dict(test=g('test_sec'), r1=g('r1_sec'), trans1=g('trans_sec'), r2pre=g('pre_sec'), brk0=g('brk_sec'), a1=a, brk1=g('brk_sec'), a2=a, brk2=g('brk_sec'), a3=a)
def timeline(c):
    t = 0; out = []; d = dur(c)
    for n in ORDER: out.append((n, t, t + d[n])); t += d[n]
    return out
def total(c): return timeline(c)[-1][2]
def bounds(c, name):
    for n, s, e in timeline(c):
        if n == name: return s, e
    return (total(c), total(c))
def stage_at(c, el):
    for n, s, e in timeline(c):
        if el < e: return n, s, e
    return 'ended', total(c), total(c)
def phase(c, name, rel):
    if name == 'r2pre': return 'auction'
    if name in ('a1', 'a2', 'a3'):
        n = float(D.get(c, 'news_sec')); d = float(D.get(c, 'disc_sec'))
        return 'newsletter' if rel < n else 'discussion' if rel < n + d else 'auction'
    return name
