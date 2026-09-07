"""ab_fast: no return walk after an ARRIVAL; a RETURN_LOOP switch. APPLY ONLY WHEN ab_fast IS NOT RUNNING."""
p = "overnight/ab_fast.py"; s = open(p).read()
def rep(old, new):
    global s
    assert s.count(old) == 1, (s.count(old), old[:70]); s = s.replace(old, new)
rep('''SETUP_ATTEMPTS = 3
''', '''SETUP_ATTEMPTS = 3
# The return loop: walk the leg backwards after a MISS so the next trial can
# skip the reset. Never after an ARRIVAL (the user watched the character win the
# table and walk away, 2026-09-07). Judged on the extend run: if fewer than
# half the return walks gave a setup under 30 s, set False.
RETURN_LOOP = True
''')
rep('''    # RETURN LOOP: walk the leg backwards (in-memory link only; the map on disk
    # is never touched -- assert_map_pristine in main() would catch it).
    t2 = time.time()
    try:''', '''    # RETURN LOOP: walk the leg backwards (in-memory link only; the map on disk
    # is never touched -- assert_map_pristine in main() would catch it). Never
    # after an arrival: a won table is left alone and the next trial resets.
    if not RETURN_LOOP or outcome == "arrived":
        row["returned_to"] = "not attempted (arrived)" if outcome == "arrived" else "off"
        return row
    t2 = time.time()
    try:''')
open(p, "w").write(s); print("patched ab_fast: no return after arrival; RETURN_LOOP switch")
