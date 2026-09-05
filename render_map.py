"""Draw what is known about the world, per level.

Positions are walk-seconds, dead-reckoned. Anything not directly observed is
drawn dashed and labelled as unconfirmed, because a map that does not
distinguish "I stood here" from "I think it is over there" is how a guess turns
into a fact.
"""
from PIL import Image, ImageDraw

W, H = 1100, 640
SCALE = 34.0          # pixels per walk-second


def draw(path="world_map.png"):
    img = Image.new("RGB", (W, H), (22, 22, 26))
    d = ImageDraw.Draw(img)

    def panel(x0, y0, x1, y1, title):
        d.rectangle([x0, y0, x1, y1], outline=(90, 90, 100))
        d.text((x0 + 10, y0 + 8), title, fill=(255, 210, 90))

    def node(cx, cy, label, seen=True):
        r = 7
        col = (120, 230, 140) if seen else (150, 150, 160)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
        d.text((cx + 12, cy - 6), label, fill=(230, 230, 235))

    def link(a, b, seen=True):
        col = (120, 200, 255) if seen else (110, 110, 120)
        d.line([a, b], fill=col, width=2)

    # ---- LEVEL 1: upstairs office ------------------------------------------
    panel(20, 20, 530, 610, "LEVEL 1  —  upstairs (spawn)")
    spawn = (200, 300)
    typewriter = (270, 250)
    safe = (330, 330)
    private_door = (140, 380)
    landing = (150, 480)
    link(spawn, private_door); link(private_door, landing)
    node(*spawn, "spawn (typewriter desk)")
    node(*typewriter, "typewriter  57-117 deg")
    node(*safe, "safe  111-153 deg")
    node(*private_door, "PRIVATE door  ~270 deg")
    node(*landing, "landing + banister")
    d.text((40, 545), "stairs descend from the landing", fill=(255, 160, 160))

    # ---- LEVEL 0: street ---------------------------------------------------
    panel(560, 20, 1080, 610, "LEVEL 0  —  street")
    street = (700, 480)
    lb = (760, 250)
    bar_sign = (900, 330)
    bar_in = (960, 200)
    link(street, lb); link(lb, bar_in, seen=False); link(street, bar_sign, seen=False)
    node(*street, "out of the office")
    node(*lb, "L&B doorway  ~358 deg")
    node(*bar_sign, "BRIE SHOT / FETA MUG", seen=False)
    node(*bar_in, "bar: counter, barman", seen=False)
    d.text((580, 545), "dashed/grey = seen but route not confirmed",
           fill=(180, 180, 190))

    # ---- the connection ----------------------------------------------------
    d.line([(150, 500), (700, 500)], fill=(255, 160, 160), width=3)
    d.text((300, 508), "STAIRS  —  the leg that is still unreliable",
           fill=(255, 160, 160))
    img.save(path)
    return path


if __name__ == "__main__":
    print(draw())
