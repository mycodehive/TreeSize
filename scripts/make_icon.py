"""Generate the project's own geometric disk-map icon, without downloaded assets."""

from pathlib import Path
import sys

from PIL import Image, ImageDraw


def make_icon(destination: Path) -> None:
    image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, 248, 248), radius=54, fill="#13243A")
    draw.rounded_rectangle((42, 42, 140, 214), radius=12, fill="#38BDF8")
    draw.rounded_rectangle((152, 42, 214, 122), radius=10, fill="#34D399")
    draw.rounded_rectangle((152, 134, 214, 214), radius=10, fill="#A78BFA")
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


if __name__ == "__main__":
    make_icon(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("build/app.ico"))
