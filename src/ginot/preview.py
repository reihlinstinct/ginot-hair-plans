"""Social preview card (Open Graph image, 1200x630) drawn at build time.

Public data only: the committed council boundary polygon plus a few counts
from the plan table. Returns False (and writes nothing) when Pillow or a
Hebrew-capable font is missing, so the page then omits the og:image tags.
"""
import json
import math

W, H = 1200, 630
FONT_PATHS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
)
NAVY, TEAL, GOLD, PAPER = (20, 33, 61), (42, 157, 143), (252, 163, 17), (245, 240, 230)


def _font(size):
    from PIL import ImageFont
    for p in FONT_PATHS:
        try:
            return ImageFont.truetype(p, size, layout_engine=ImageFont.Layout.BASIC)
        except OSError:
            continue
    return None


def _heb(s: str) -> str:
    """Visual order for pure-Hebrew text (Pillow without raqm draws left-to-right)."""
    return s[::-1]


def _rings(geojson_path):
    with open(geojson_path, encoding="utf-8") as fh:
        d = json.load(fh)
    feats = d["features"] if d.get("type") == "FeatureCollection" else [d]
    rings = []
    for f in feats:
        g = f.get("geometry", f)
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        rings += [p[0] for p in polys]
    return rings


def _draw_map(draw, rings, box):
    x0, y0, x1, y1 = box
    pts = [pt for r in rings for pt in r]
    k = math.cos(math.radians(sum(p[1] for p in pts) / len(pts)))
    xs = [p[0] * k for p in pts]
    ys = [p[1] for p in pts]
    sx, sy = max(xs) - min(xs), max(ys) - min(ys)
    scale = min((x1 - x0) / sx, (y1 - y0) / sy)
    ox = x0 + ((x1 - x0) - sx * scale) / 2
    oy = y0 + ((y1 - y0) - sy * scale) / 2
    for gx in range(x0, x1 + 1, 40):
        draw.line([(gx, y0), (gx, y1)], fill=(36, 52, 88), width=1)
    for gy in range(y0, y1 + 1, 40):
        draw.line([(x0, gy), (x1, gy)], fill=(36, 52, 88), width=1)
    for ring in rings:
        poly = [(ox + (p[0] * k - min(xs)) * scale, oy + (max(ys) - p[1]) * scale) for p in ring]
        draw.polygon(poly, fill=(42, 157, 143, 255), outline=GOLD)
        draw.line(poly + [poly[0]], fill=GOLD, width=4)


def render_preview(rows, council_name, generated, geojson_path, out_path) -> bool:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False
    big, mid, small = _font(64), _font(40), _font(28)
    if big is None:
        return False
    img = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 14], fill=GOLD)
    try:
        _draw_map(d, _rings(geojson_path), (60, 90, 520, 550))
    except (OSError, KeyError, ValueError, TypeError, ZeroDivisionError):
        pass  # card still renders without the map

    def right(text, y, font, fill, x=W - 70):
        t = _heb(text)
        w = d.textlength(t, font=font)
        d.text((x - w, y), t, font=font, fill=fill)

    right("תכניות תכנון ובנייה", 80, big, PAPER)
    right(council_name, 165, big, GOLD)
    right("מעקב אחר תכניות והיתרים", 255, mid, (190, 200, 220))
    active = sum(1 for r in rows if any(k in (r.get("station_desc") or "") for k in
                                        ("הפקדה", "תנאים", "הכרעה", "בדיקה", "בהליך")))
    open_obj = sum(1 for r in rows if r.get("_open_obj"))
    cards = [(len(rows), "תכניות במעקב"), (active, "בהליך"), (open_obj, "פתוח להתנגדות")]
    x = W - 70
    for n, label in cards:
        cw = 210
        d.rounded_rectangle([x - cw, 340, x, 500], radius=18, fill=(30, 48, 86), outline=TEAL, width=2)
        num = str(n)
        d.text((x - cw / 2 - d.textlength(num, font=big) / 2, 355), num, font=big, fill=GOLD)
        t = _heb(label)
        d.text((x - cw / 2 - d.textlength(t, font=small) / 2, 450), t, font=small, fill=PAPER)
        x -= cw + 20
    d.text((W - 70 - d.textlength(str(generated), font=small), 545), str(generated), font=small,
           fill=(150, 165, 195))
    right("עודכן", 545, small, (150, 165, 195), x=W - 70 - d.textlength(str(generated), font=small) - 14)
    img.save(out_path, "PNG", optimize=True)
    return True


def render_review_preview(row, generated, out_path):
    """Public-data review card. Derived deadlines are deliberately omitted.

    Requires RAQM for correct mixed Hebrew/numeric text. Without it, use the
    default site card instead of publishing reversed identifiers. No tiles.
    """
    import os
    try:
        from PIL import Image, ImageDraw, ImageFont, features
    except ImportError:
        return False
    if not features.check("raqm"):
        return False
    engine = ImageFont.Layout.RAQM
    font_path = next((p for p in FONT_PATHS if os.path.exists(p)), None)
    if not font_path:
        return False
    img = Image.new("RGB", (W, H), "#f3f6ff")
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, W, 18), fill="#51b89a")

    def font(size):
        return ImageFont.truetype(font_path, size, layout_engine=engine)

    def text(value, y, size, color="#101f5b", rtl=True):
        value = str(value)
        kw = {"direction": "rtl"} if rtl else {}
        f = font(size)
        if draw.textlength(value, font=f, **kw) > W - 140:
            while value and draw.textlength(value + "…", font=f, **kw) > W - 140:
                value = value[:-1]
            value += "…"
        width = draw.textlength(value, font=f, **kw)
        draw.text((W - 70 - width, y), value, font=f, fill=color, **kw)

    text("גינות העיר | סקירת AI", 50, 38)
    text(row.get("pl_number") or "", 115, 68, rtl=False)
    name = str(row.get("pl_name") or "תכנית ללא שם")
    words, lines, current = name.split(), [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if draw.textlength(candidate, font=font(43)) > 1060 and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    for i, line in enumerate(lines[:2]):
        if i == 1 and len(lines) > 2:
            line = line[:43] + "…"
        text(line, 220 + i * 60, 43)
    status = str(row.get("station_desc") or "סטטוס לא זמין")
    if len(status) > 60:
        status = status[:57] + "…"
    text(status, 365, 31)
    # No deadline displayed: snapshot-derived +60d is not source verification.
    text("סיכום אוטומטי לעיון - לא מסמך רשמי", 460, 28)
    text("עודכן: " + str(generated), 525, 25)
    img.save(out_path, "PNG", optimize=True)
    return True
