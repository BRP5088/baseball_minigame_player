"""A 3D map of where the character has been: level, plus a position on it.

WHY A MAP AND NOT MORE BEARINGS
-------------------------------
Everything before this recorded routes as headings — "face 358, walk 5s". That
is a 2D description of a world with FLOORS, and it failed exactly where the
floors matter: the spawn is upstairs, and four separate attempts walked at a
street-level doorway from an upper landing, jamming into railings and geometry
each time. No amount of tuning a bearing fixes standing on the wrong floor.

POSITIONS ARE DEAD-RECKONED, and that is sound here for one specific reason:
heading is known EXACTLY. The compass reads to a fraction of a degree, walking
never changes heading (measured: constant to 0.01 degrees across whole legs),
and turn control lands within half a degree. So integrating heading and time
accumulates almost no angular error — which is the term that normally destroys
dead reckoning.

UNITS ARE WALK-SECONDS, not metres. There is no way to measure true distance
from inside the game, and no need to: navigating back to somewhere only needs
positions that are consistent with each other.

LEVEL CHANGES ARE ASSERTED, NOT OBSERVED — AND THAT HAS ALREADY GONE WRONG.
change_level() is called by the caller because it believes it went up or down.
On the first mapped run the caller walked 8s north from spawn, called
change_level(-1), and marked "street_outside_office" — while the character was
still standing in the upstairs office looking at a window with blinds. The map
was confidently wrong, and being wrong about the FLOOR is the one error it was
built to prevent.

A wrong level is worse than a wrong position: bearing_to() silently refuses
everything on the floor you think you left, and answers for the floor you never
reached. Until descending can be DETECTED rather than declared, call
change_level only from a frame you have actually looked at.

WHAT THIS CANNOT DO
-------------------
It does not know about walls. A straight line between two mapped points may go
through a building. It records where the character HAS been and what was
visible from there; finding a way between two points is still walking and
looking.
"""

import heapq
import json
import math
import os

STORE = "world_map.json"


class WorldMap:
    def __init__(self, level=0, x=0.0, y=0.0):
        self.level = level
        self.x = x
        self.y = y
        self.landmarks = {}
        # Legs actually WALKED between landmarks, and how long they took.
        # bearing_to() answers with a straight line and says so in this
        # module's own docstring: "a straight line between two mapped points
        # may go through a building". These are the edges that are known to be
        # walkable, because the character walked them.
        self.links = {}
        # Pairs of nodes the LOCALISER cannot tell apart, measured rather than
        # assumed. They stay separate nodes because the walk between them is
        # real; this records that appearance must not be used to choose between
        # them. Empty is the honest default: unmeasured is not the same as none.
        self.confusable = []
        self.trail = [(level, x, y, "start")]

    # --- movement ---------------------------------------------------------
    def walk(self, bearing_deg, seconds):
        """Integrate a walk. 0 deg = north = +y, 90 deg = east = +x."""
        r = math.radians(bearing_deg)
        self.x += math.sin(r) * seconds
        self.y += math.cos(r) * seconds
        self.trail.append((self.level, self.x, self.y, f"walk {bearing_deg:.0f}"))
        return self.here()

    def change_level(self, delta, note="stairs"):
        """Up or down a floor. Position on the new level continues from here.

        Stairs move you horizontally as well, and that displacement is captured
        by the walk() calls made while descending — this only records that the
        floor changed, which is the part no bearing can express.
        """
        self.level += delta
        self.trail.append((self.level, self.x, self.y, note))
        return self.here()

    # --- places -----------------------------------------------------------
    def mark(self, name):
        self.landmarks[name] = (self.level, round(self.x, 2), round(self.y, 2))
        return self.landmarks[name]

    def here(self):
        return (self.level, round(self.x, 2), round(self.y, 2))

    def connect(self, a, b, cost_or_steps, one_way=True, note=""):
        """Record that a->b is WALKABLE, with what it takes to WALK it.

        Only ever called after actually making the trip. A link invented from
        two positions being near each other is the straight-line answer again,
        wearing a graph's clothes.

        A DURATION IS NOT EXECUTABLE. This used to store a bare float, which
        made a routed path a list of names that nothing could follow: no
        heading, no speed, and bearing_to() answering None for the very names
        route() had just returned. `steps` is a list of
        {"bearing", "dur", "speed"} in the shape walk_steps already consumes,
        so a leg can be replayed rather than re-derived. A curve keeps all its
        sub-steps — averaging a 26-degree bend into one heading walks into a
        wall.

        ONE-WAY BY DEFAULT, which is the reverse of what this did before. One
        trip is evidence about one direction. Fabricating the return leg is how
        an unwalked climb gets planned over a stairway or a drop.
        """
        if a not in self.landmarks or b not in self.landmarks:
            missing = [n for n in (a, b) if n not in self.landmarks]
            raise ValueError(
                f"connect({a!r}, {b!r}): {missing} not marked. An unmarked "
                f"endpoint is a silent orphan island — route() would hand back "
                f"a name that bearing_to() then refuses.")
        if isinstance(cost_or_steps, (int, float)):
            steps, cost = [], float(cost_or_steps)
        else:
            steps = [dict(s) for s in cost_or_steps]
            if not steps:
                raise ValueError(f"connect({a!r}, {b!r}): empty steps")
            cost = float(sum(s["dur"] for s in steps))
        if not math.isfinite(cost) or cost <= 0:
            # A negative cost makes route()'s path reconstruction spin forever;
            # NaN compares false against everything and silently hides the leg.
            raise ValueError(
                f"connect({a!r}, {b!r}): cost {cost!r} must be finite and > 0")
        link = {"cost": cost, "steps": steps}
        if note:
            link["recorded"] = note
        self.links.setdefault(a, {})[b] = link
        if not one_way:
            self.links.setdefault(b, {})[a] = dict(link)
        return self.links[a]

    @staticmethod
    def _cost(link):
        """Cost of a link, tolerating the legacy bare-float form."""
        return float(link["cost"]) if isinstance(link, dict) else float(link)

    def steps_for(self, a, b):
        """The walkable steps of a->b. Raises if the leg cannot be walked.

        LOUD ON PURPOSE. A leg with no steps is unwalkable, and an executor
        that skipped it would report a completed route while standing still —
        the exact "did nothing, looked like working" shape this codebase keeps
        producing.
        """
        link = self.links.get(a, {}).get(b)
        if link is None:
            raise KeyError(f"no recorded leg {a!r} -> {b!r}")
        steps = link.get("steps") if isinstance(link, dict) else []
        if not steps:
            raise ValueError(
                f"leg {a!r} -> {b!r} has a cost but no steps, so it cannot be "
                f"walked. It was recorded before legs carried headings; re-walk "
                f"it rather than guessing a bearing.")
        return steps

    def route(self, start, goal):
        """Cheapest walkable path start->goal as a list of names, or None.

        Dijkstra over `links`. Costs are walk-seconds, which are always
        positive, so no negative-edge case exists.

        Returns None rather than a straight line when the two are not
        connected. That refusal is the point: an unreachable goal that answers
        with a bearing is what walked four attempts into railings.
        """
        if start == goal:
            return [start] if start in self.links or start in self.landmarks else None
        if start not in self.links:
            return None
        dist = {start: 0.0}
        prev = {}
        seen = set()
        q = [(0.0, start)]
        while q:
            d, node = heapq.heappop(q)
            if node in seen:
                continue
            seen.add(node)
            if node == goal:
                path = [node]
                while path[-1] != start:
                    path.append(prev[path[-1]])
                return path[::-1]
            for nxt, link in self.links.get(node, {}).items():
                nd = d + self._cost(link)
                if nd < dist.get(nxt, float("inf")):
                    dist[nxt] = nd
                    prev[nxt] = node
                    heapq.heappush(q, (nd, nxt))
        return None

    def route_reason(self, start, goal):
        """Why route() gave what it gave: ok | same | unknown_start |
        unknown_goal | unreachable.

        route() answers None for four different reasons, and an unattended run
        that logs "no route" cannot tell a typo from a genuinely disconnected
        goal from an empty map. Each needs a different fix.
        """
        known = set(self.links) | set(self.landmarks)
        for name, tag in ((start, "unknown_start"), (goal, "unknown_goal")):
            if name not in known:
                return tag
        if start == goal:
            return "same"
        return "ok" if self.route(start, goal) else "unreachable"

    def route_cost(self, path):
        """Walk-seconds along a path from route(), or None if it is not walkable."""
        if not path or len(path) < 2:
            return 0.0 if path else None
        total = 0.0
        for a, b in zip(path, path[1:]):
            if b not in self.links.get(a, {}):
                return None
            total += self._cost(self.links[a][b])
        return total

    def bearing_to(self, name):
        """(bearing, distance_in_walk_seconds) to a landmark on THIS level.

        Returns None when the landmark is on another floor, because a heading
        toward it would be meaningless — that is the failure this map exists to
        prevent. Find the stairs first.
        """
        if name not in self.landmarks:
            return None
        level, lx, ly = self.landmarks[name]
        if level != self.level:
            return None
        dx, dy = lx - self.x, ly - self.y
        dist = math.hypot(dx, dy)
        if dist < 1e-6:
            return (None, 0.0)
        return ((math.degrees(math.atan2(dx, dy)) + 360) % 360, dist)

    # --- persistence ------------------------------------------------------
    def save(self, path=STORE):
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump({"level": self.level, "x": self.x, "y": self.y,
                       "landmarks": self.landmarks, "links": self.links,
                       "confusable": self.confusable,
                       "trail": self.trail}, fh, indent=1)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path=STORE):
        with open(path) as fh:
            d = json.load(fh)
        m = cls(d["level"], d["x"], d["y"])
        m.landmarks = {k: tuple(v) for k, v in d["landmarks"].items()}
        # LINKS ARE MANDATORY, trail is not. This was the other way round, so a
        # hand-authored map died on a missing "trail" while a map with NO LINKS
        # AT ALL loaded as perfectly valid — and then route() returned None for
        # every pair, which reads as "no path exists" rather than "there is no
        # map here". An empty graph must not be able to masquerade as a full one.
        if "links" not in d:
            raise KeyError(
                f"{path} has no 'links' — that is not an empty map, it is a "
                f"map with no edges, and routing over it would silently report "
                f"every destination as unreachable")
        m.links = {k: dict(v) for k, v in d["links"].items()}
        m.confusable = [list(c) for c in d.get("confusable", [])]
        m.trail = [tuple(t) for t in d.get("trail", [])]
        return m
