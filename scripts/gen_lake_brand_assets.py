"""Generate the Lake Ink & Brass binary brand assets from the line mark — pure Pillow.

Companion to ``app/static/img/lake/favicon.svg`` (the vector mark, which covers
modern browsers). Legacy browsers want a real ``favicon.ico``; iOS / Android /
PWA installs want PNG app icons + a maskable variant; social cards want a
1200x630 OG image. Those are binary and can't be hand-written, so this script
redraws the mark with ``PIL.ImageDraw`` — same dependency-light approach as
``scripts/gen_favicon_assets.py`` (the desert generator), no cairo/SVG raster.

The mark = the Lake Havasu London Bridge monoline: an ink rounded tile, a paper
arch with deck + piers, and a brass cannon-lamp standard. Drawn at 4x and
downsampled for anti-aliasing. Geometry is ported from the ``icoLine`` / ``favTile``
symbols in ``askhava-redesign/askhava-logo.html`` (64-unit viewBox).

Run from repo root:
    .venv\\Scripts\\python.exe scripts\\gen_lake_brand_assets.py

Outputs (committed, under app/static/img/lake/):
    favicon.ico            (16/32/48 multi-size, single bold arch)
    apple-touch-icon.png   (180)
    icon-192.png  icon-512.png  icon-1024.png
    icon-maskable-512.png  (mark inset into the safe zone)
    og-default.png         (1200x630 social card)

Keep in sync with app/static/img/lake/favicon.svg + mockups/lake.css if the mark
or palette changes.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_ROOT = Path(__file__).resolve().parents[1]
_IMG = _ROOT / "app" / "static" / "img" / "lake"
_FONTS = _ROOT / "app" / "static" / "fonts"

# Palette — Lake Ink & Brass (matches mockups/lake.css tokens).
_INK = (16, 32, 43, 255)  # --ink #10202b
_PAPER = (238, 243, 247, 255)  # paper line #eef3f7
_BRASS = (216, 166, 78, 255)  # --brass-light #d8a64e
_MUTED = (144, 163, 174, 255)  # footer muted #90a3ae


def _arch_bbox(cx: float, cy: float, rx: float, ry: float) -> list[float]:
    return [cx - rx, cy - ry, cx + rx, cy + ry]


def _draw_mark(d: ImageDraw.ImageDraw, s: float, *, bold: bool, lamp: bool) -> None:
    """Draw the paper arch + (optional) brass lamp at scale ``s`` (64-unit space).

    ``bold`` thickens strokes for tiny favicon sizes; ``lamp`` adds the brass
    cannon-lamp standard (omit it only where it would turn to mush).
    """
    pw = (4.0 if bold else 2.9) * s  # paper stroke
    bw = 3.2 * s  # brass stroke

    def line(x1: float, y1: float, x2: float, y2: float, w: float, fill) -> None:
        d.line([(x1 * s, y1 * s), (x2 * s, y2 * s)], fill=fill, width=int(round(w)))

    # Deck.
    line(12, 28, 52, 28, pw, _PAPER)
    # Arch (top half-ellipse, centre 32,44).
    d.arc(
        [c * s for c in _arch_bbox(32, 44, 16, 12.5)],
        180, 360, fill=_PAPER, width=int(round(pw)),
    )
    # Piers + baseline.
    line(16, 44, 16, 50, pw, _PAPER)
    line(48, 44, 48, 50, pw, _PAPER)
    if not bold:
        line(15, 50, 49, 50, pw * 0.85, _PAPER)
    # Round the deck/pier ends so they don't read as blunt at small sizes.
    for cx, cy in ((12, 28), (52, 28), (16, 50), (48, 50)):
        r = pw / 2
        d.ellipse([cx * s - r, cy * s - r, cx * s + r, cy * s + r], fill=_PAPER)
    # Brass cannon-lamp standard.
    if lamp:
        line(32, 28, 32, 18, bw, _BRASS)
        r = 3.0 * s
        d.ellipse(
            [32 * s - r, 14.4 * s - r, 32 * s + r, 14.4 * s + r],
            outline=_BRASS, width=int(round(bw)),
        )


def render_icon(size: int, *, maskable: bool = False, bold: bool = False) -> Image.Image:
    """Render the ink-tile app icon at ``size`` px (RGBA)."""
    ss = size * 4
    img = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Maskable icons must keep the mark inside the central ~80% safe zone, so the
    # ink tile bleeds full-bleed and the mark is inset.
    inset = ss * 0.10 if maskable else 0
    radius = 0 if maskable else 14 / 64 * ss
    d.rounded_rectangle([0, 0, ss - 1, ss - 1], radius=radius, fill=_INK)
    mark_box = ss - 2 * inset
    s = mark_box / 64.0
    md = ImageDraw.Draw(img)
    # Translate the mark into the inset region by drawing on an offset layer.
    layer = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    _draw_mark(ld, s, bold=bold, lamp=True)
    if inset:
        layer = layer.transform(
            (ss, ss), Image.AFFINE, (1, 0, -inset, 0, 1, -inset), resample=Image.BILINEAR
        )
    img = Image.alpha_composite(img, layer)
    if not maskable:
        # Re-clip to rounded square.
        mask = Image.new("L", (ss, ss), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, ss - 1, ss - 1], radius=radius, fill=255)
        img.putalpha(mask)
    del d, md
    return img.resize((size, size), Image.LANCZOS)


def render_favicon_ico() -> Image.Image:
    """Bold single-arch tile for the multi-size .ico (renders crisp at 16px)."""
    return render_icon(256, bold=True)


def _font(name: str, px: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(_FONTS / name), px)
    except OSError:
        return ImageFont.load_default()


def render_og() -> Image.Image:
    """1200x630 default social card — ink field, icon tile, wordmark + tagline."""
    W, H = 1200, 630
    img = Image.new("RGBA", (W, H), _INK)
    d = ImageDraw.Draw(img)
    # Subtle top glow.
    for i in range(160):
        a = int(18 * (1 - i / 160))
        d.line([(0, i), (W, i)], fill=(27, 47, 58, a))
    # Icon tile, left.
    icon = render_icon(248).convert("RGBA")
    img.alpha_composite(icon, (96, (H - 248) // 2))
    # Wordmark + tagline, right of the tile.
    x = 392
    fr = _font("fraunces-600.ttf", 116)
    d.text((x, 196), "Ask ", font=fr, fill=_PAPER)
    ask_w = d.textlength("Ask ", font=fr)
    d.text((x + ask_w, 196), "Hava", font=fr, fill=_BRASS)
    sub = _font("inter-400.ttf", 33)
    d.text((x + 4, 340), "Lake Havasu City's local concierge", font=sub, fill=_PAPER)
    d.text((x + 4, 388), "Events, conditions & the best local spots.", font=sub, fill=_MUTED)
    # Brass hairline under the wordmark.
    d.rectangle([x + 4, 322, x + 4 + 120, 326], fill=_BRASS)
    return img.convert("RGB")


def main() -> None:
    _IMG.mkdir(parents=True, exist_ok=True)
    render_favicon_ico().save(
        _IMG / "favicon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48)]
    )
    render_icon(180).save(_IMG / "apple-touch-icon.png")
    render_icon(192).save(_IMG / "icon-192.png")
    render_icon(512).save(_IMG / "icon-512.png")
    render_icon(1024).save(_IMG / "icon-1024.png")
    render_icon(512, maskable=True).save(_IMG / "icon-maskable-512.png")
    render_og().save(_IMG / "og-default.png")
    print("done — wrote favicon.ico, apple-touch-icon.png, icon-192/512/1024.png, "
          "icon-maskable-512.png, og-default.png to", _IMG)


if __name__ == "__main__":
    main()
