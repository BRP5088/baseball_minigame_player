"""test_success_control_frames: pin WHICH frame each control file holds."""
p = "tests/routing/test_success_control_frames.py"; s = open(p).read()
old_img = '''class Img:
    """Stands in for a PIL image; records where it was written."""
    def __init__(self, saved):
        self.saved = saved
    def save(self, path, *a, **k):
        self.saved.append(path)
    def convert(self, *a):
        return self
'''
new_img = '''class Img:
    """Stands in for a PIL image; records where it was written, and as what."""
    def __init__(self, saved, tag="BEFORE"):
        self.saved = saved
        self.tag = tag
    def save(self, path, *a, **k):
        self.saved.append((path, self.tag))
    def convert(self, *a):
        return self
'''
assert s.count(old_img) == 1; s = s.replace(old_img, new_img)
old_run = '''    gw.go_to_node_verified = lambda *a, **k: arrives
'''
new_run = '''    def fake_go(m, node, **kw):
        # A real arrival or failure publishes the frame the leg ended on.
        gw._LAST_LEG_END[node] = Img(saved, tag="LEG-END")
        return arrives
    gw.go_to_node_verified = fake_go
'''
assert s.count(old_run) == 1; s = s.replace(old_run, new_run)
old_checks = '''ok_files = run(True)
bad_files = run(False)
check("an ARRIVAL writes a control frame",
      any(os.sep + "success" + os.sep in f for f in ok_files))
check("an arrival's frame is NOT filed as a failure",
      not any("fail_" in os.path.basename(f) for f in ok_files))
check("a FAILURE still writes its frame",
      any("fail_" in os.path.basename(f) for f in bad_files))
check("a failure is NOT filed as a control",
      not any(os.sep + "success" + os.sep in f for f in bad_files))
'''
new_checks = '''ok_files = run(True)
bad_files = run(False)
def stems(files):
    return {os.path.basename(f).rsplit("_", 1)[0]: tag for f, tag in files}
ok, bad = stems(ok_files), stems(bad_files)
check("an ARRIVAL writes a control frame",
      any(os.sep + "success" + os.sep in f for f, _ in ok_files))
check("...the START pose, from the frame taken before the attempt",
      ok.get("start_bar_jukebox") == "BEFORE")
check("...AND the leg's END frame, the twin of fail_<node>",
      ok.get("ok_bar_jukebox") == "LEG-END")
check("an arrival's frame is NOT filed as a failure",
      not any("fail_" in os.path.basename(f) for f, _ in ok_files))
check("a FAILURE still writes its frame",
      any("fail_" in os.path.basename(f) for f, _ in bad_files))
check("...from the leg's END, not the start",
      bad.get("fail_bar_jukebox") == "LEG-END")
check("...and its START pose beside it, so the control has both groups",
      bad.get("start_bar_jukebox") == "BEFORE")
check("a failure is NOT filed as a control",
      not any(os.sep + "success" + os.sep in f for f, _ in bad_files))
'''
assert s.count(old_checks) == 1; s = s.replace(old_checks, new_checks)
s = s.replace('"""follow_verified must save the start pose on ARRIVAL, not only on failure.',
              '"""follow_verified must save the START pose on ARRIVAL, and the leg END on both.')
open(p, "w").write(s); print("patched test_success_control_frames.py")
