"""Update schedule: normal phase every `tick` s, intraday phase every `itick` s. All values in event-seconds."""
def _k(tick, ia): return int(ia // tick)
def update_time(n, tick, itick, ia):
    k = _k(tick, ia)
    return n * tick if n <= k else k * tick + (n - k) * itick
def max_update(tick, itick, ia, total):
    k = _k(tick, ia); base = k * tick
    return int(total // tick) if total <= base else k + int((total - base) // itick + 1e-9)
def due_updates(el, tick, itick, ia, total):
    k = _k(tick, ia); base = k * tick
    d = int(el // tick) if el < base else k + int((el - base) // itick + 1e-9)
    return min(d, max_update(tick, itick, ia, total))
def is_intraday_update(n, tick, ia): return n > _k(tick, ia)
