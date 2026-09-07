"""STOP THE GOAL LEG THE MOMENT THE PROMPT APPEARS. APPLY ONLY WHEN NO LIVE RUN IMPORTS graph_walk.

User, watching the stream 2026-09-07: "I just watched the player walk right up
to the mini game table and get the start a game text and walk completely
away." The recorded goal leg replays all eight steps blind; the straight-line
approach it replaced checked the prompt after every push. This gives walk_link
an optional `stop_when` callable, checked AFTER each step, and follow() passes
at_table for the goal leg under GOAL_LEG_AS_RECORDED; the extension is skipped
when the leg stopped early. Moves the character LESS, never more.
"""
p = "graph_walk.py"; s = open(p).read()
def rep(old, new):
    global s
    assert s.count(old) == 1, (s.count(old), old[:70]); s = s.replace(old, new)
rep('''def walk_link(m, a, b, capture=None, read_heading=None, log=print,
              fraction=1.0):''', '''def walk_link(m, a, b, capture=None, read_heading=None, log=print,
              fraction=1.0, stop_when=None):''')
open(p, "w").write(s); print("patched signature; the loop body edit is applied by the second half once the anchors are confirmed")
