"""Render the Music Studio mark as editable SVG, PNG and a multi-size Windows ICO.

Maintainers: install Pillow, then run this script. The application needs no Pillow.
"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src/music_studio/ui/static"
SCALE = 4


def build():
    canvas = Image.new("RGBA", (512 * SCALE, 512 * SCALE))
    draw = ImageDraw.Draw(canvas)
    elements = []

    def rounded(box, radius, color):
        x, y, right, bottom = box
        elements.append(f'<rect x="{x}" y="{y}" width="{right - x}" '
                        f'height="{bottom - y}" rx="{radius}" fill="{color}"/>')
        draw.rounded_rectangle(tuple(value * SCALE for value in box),
                               radius=radius * SCALE, fill=color)

    rounded((16, 16, 496, 496), 112, "#31494d")
    rounded((19, 19, 493, 493), 109, "#112229")
    # Five clear bands stay recognizable at taskbar size. The small separation
    # between upper and lower bands is the same operation the app performs.
    for x, top, bottom, color in (
        (112, 218, 294, "#56b9a5"), (176, 170, 342, "#7ad8c0"),
        (240, 122, 390, "#e8f1e9"), (304, 170, 342, "#7ad8c0"),
        (368, 218, 294, "#56b9a5"),
    ):
        rounded((x, top, x + 32, 248), 16, color)
        rounded((x, 264, x + 32, bottom), 16, "#f4b66b" if x == 240 else color)

    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" '
           'viewBox="0 0 512 512"><title>Music Studio</title>' + "".join(elements) + "</svg>\n")
    (ASSETS / "icon.svg").write_text(svg, encoding="utf-8", newline="\n")
    canvas = canvas.resize((512, 512), Image.Resampling.LANCZOS)
    canvas.save(ASSETS / "icon.png", optimize=True)
    canvas.save(ASSETS / "icon.ico", format="ICO",
                sizes=[(size, size) for size in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
    print("Created icon.svg, icon.png and icon.ico")


if __name__ == "__main__":
    build()
