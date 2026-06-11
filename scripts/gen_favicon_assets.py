"""Generate the binary favicon set from the Ask Hava mark — pure Pillow.

The SVG favicon (app/static/img/favicon.svg) covers modern browsers, but legacy
browsers want a real multi-size favicon.ico and iOS home-screen wants a PNG
apple-touch-icon. Those are binary assets that can't be hand-written.

The mark is simple geometry (rounded square, sun disc, ridge), so this script
redraws it with Pillow's ImageDraw rather than rasterizing the SVG — that keeps
the only dependency Pillow (no cairo / GTK native libs, which are painful on
Windows). Anti-aliased by drawing at 4x and downsampling.

Run from repo root:
    pip install pillow --quiet          # usually already in the venv
    .venv\\Scripts\\python.exe scripts\\gen_favicon_assets.py

Outputs (committed):
    app/static/img/favicon.ico          (16/32/48 multi-size)
    app/static/img/apple-touch-icon.png (180)
    app/static/img/icon-192.png
    app/static/img/icon-512.png

Keep in sync with app/static/img/favicon.svg if the mark changes.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

_IMG = Path(__file__).resolve().parents[1] / "app" / "static" / "img"

# Palette (matches favicon.svg): ink #171310, sun #d4581e, ridge #11324d.
_INK = (23, 19, 16, 255)
_SUN = (212, 88, 30, 255)
_RIDGE = (17, 50, 77, 255)
# Ridge polygon in the 64x64 viewBox (from favicon.svg path).
_RIDGE_PTS = [(6, 51), (22, 40), (34, 47), (48, 37), (58, 43), (58, 58), (6, 58)]


def render(size: int) -> Image.Image:
    """Render the mark at ``size`` px (RGBA, transparent rounded corners)."""
    ss = size * 4  # supersample for anti-aliasing
    s = ss / 64.0
    img = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, ss - 1, ss - 1], radius=14 * s, fill=_INK)
    d.ellipse([(32 - 15) * s, (27 - 15) * s, (32 + 15) * s, (27 + 15) * s], fill=_SUN)
    d.polygon([(x * s, y * s) for x, y in _RIDGE_PTS], fill=_RIDGE)
    # Re-clip to the rounded square so the ridge can't square off the bottom corners.
    mask = Image.new("L", (ss, ss), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, ss - 1, ss - 1], radius=14 * s, fill=255)
    img.putalpha(mask)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    render(180).save(_IMG / "apple-touch-icon.png")
    render(192).save(_IMG / "icon-192.png")
    render(512).save(_IMG / "icon-512.png")
    render(256).save(
        _IMG / "favicon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48)]
    )
    print("done — wrote favicon.ico, apple-touch-icon.png, icon-192.png, icon-512.png")


if __name__ == "__main__":
    main()
