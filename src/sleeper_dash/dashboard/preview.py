"""The link-preview image (Phase 5, owner 2026-10-05): a 1200×630 PNG of the latest week's top five, shown when the
page's link is pasted into a group chat (the page's Open Graph and Twitter card tags point to it).

Drawn with Pillow in the page's own fonts (Barlow and Barlow Condensed, bundled in fonts/ under the SIL Open Font
License) and colours (docs/UI_GUIDE.md "Color"; a test checks they equal the CSS tokens): the masthead's turf green,
chalk text, muted secondary text, and the pylon on the #1 numeral only, which at 64px bold is large text. Written by
build_site next to index.html, so every run of the weekly workflow makes a fresh one. A 32-colour palette keeps it
small (about 30 KB). The season and week are stored in the PNG's text chunks, so a test can check the image is this
week's without reading pixels.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

FONTS = Path(__file__).parent / "fonts"
SIZE = (1200, 630)  # what chat apps and social sites expect for a large preview
FILENAME = "preview.png"
# CSS tokens from templates/styles.css (the masthead band and its text; the dark-mode pylon and rule colours,
# which are the ones made for a dark background).
COLOURS = {"masthead": "#18392B", "chalk": "#F6F8F4", "on-mast-muted": "#9DADA3", "pylon": "#FF7A2E", "bar": "#5E7066"}
TOP = 5


def _font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def _fit(draw, text, font, width):
    """The text, cut with '…' to fit `width` pixels (long team names)."""
    if draw.textlength(text, font=font) <= width:
        return text
    while text and draw.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def _rgb(hex_colour):
    return tuple(int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))


def _palette(steps=12):
    """A palette of the token colours and the shades between each and the background (the anti-aliased edges of
    text), so the small palette PNG keeps every colour exact: a generic 32-colour reduction turned the one pylon
    numeral brown."""
    background = _rgb(COLOURS["masthead"])
    colours = {background}
    for name, value in COLOURS.items():
        target = _rgb(value)
        colours |= {tuple(round(b + (t - b) * k / steps) for b, t in zip(background, target)) for k in range(1, steps + 1)}
    flat = [channel for colour in sorted(colours) for channel in colour]
    palette = Image.new("P", (1, 1))
    palette.putpalette(flat + list(background) * (256 - len(colours)))
    return palette


def render(view, path):
    """Draw the preview for the view's latest week to `path`. Returns its season, week, and size in bytes."""
    latest = view["latest"]
    image = Image.new("RGB", SIZE, COLOURS["masthead"])
    draw = ImageDraw.Draw(image)
    league, title = _font("BarlowCondensed-SemiBold.ttf", 34), _font("BarlowCondensed-Bold.ttf", 68)
    numeral, name = _font("BarlowCondensed-Bold.ttf", 64), _font("Barlow-SemiBold.ttf", 34)
    small, score = _font("Barlow-Regular.ttf", 24), _font("BarlowCondensed-Bold.ttf", 44)

    left, right = 64, SIZE[0] - 64
    draw.text((left, 40), _fit(draw, view["league_name"], league, right - left), font=league, fill=COLOURS["on-mast-muted"])
    draw.text((left, 76), latest["title"], font=title, fill=COLOURS["chalk"])

    top, row = 178, 76
    for i, team in enumerate(latest["ladder"][:TOP]):
        y = top + i * row
        draw.line([(left, y), (right, y)], fill=COLOURS["bar"], width=1)
        draw.text((left + 56, y + row / 2), str(team["rank"]), font=numeral, anchor="rm",
                  fill=COLOURS["pylon"] if team["rank"] == 1 else COLOURS["chalk"])
        draw.text((right, y + row / 2), team["score"], font=score, anchor="rm", fill=COLOURS["chalk"])
        text_left, text_right = left + 84, right - 120
        draw.text((text_left, y + 10), _fit(draw, team["team"], name, text_right - text_left), font=name, fill=COLOURS["chalk"])
        record = team["record"].split(",")[0]  # the overall record; the all-play record doesn't fit
        draw.text((text_left, y + 48), _fit(draw, f"{team['user']} · {record}", small, text_right - text_left),
                  font=small, fill=COLOURS["on-mast-muted"])
    footer = top + TOP * row
    draw.line([(left, footer), (right, footer)], fill=COLOURS["bar"], width=1)
    draw.text((left, SIZE[1] - 36), f"Power score: league average 50 · Updated {view['updated']}", font=small,
              anchor="ls", fill=COLOURS["on-mast-muted"])

    info = PngImagePlugin.PngInfo()
    info.add_text("Title", latest["title"])
    info.add_text("season", str(view["season"]))
    info.add_text("week", str(latest["week"]))
    path = Path(path)
    image.quantize(palette=_palette(), dither=Image.Dither.NONE).save(path, optimize=True, pnginfo=info)
    return {"season": view["season"], "week": latest["week"], "bytes": path.stat().st_size}


def read_week(path):
    """(season, week) stored in a preview image's text chunks."""
    with Image.open(path) as image:
        return int(image.text["season"]), int(image.text["week"])
