"""Create a QA comparison board from existing rendered evidence, not a UI asset."""
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw

base = Path("C:/Users/Abbadon/Documents/Codex/_android-build-tools")
source = Image.open("C:/Users/Abbadon/.codex/generated_images/019f9ef6-31f0-74a2-955c-d6740bf3a88b/exec-5a03f02f-42c5-4158-9a72-7547c07adf16.png").convert("RGB")
native = Image.open(base / "widget-043-tall.png").convert("RGBA")
ref = source.crop((616, 143, 1204, 1106))
ref = ImageOps.contain(ref, (472, 1103))
board = Image.new("RGB", (1024, 1180), "#e8e3da")
board.paste(ref, (24, 48))
board.paste(native, (528, 48), native)
draw = ImageDraw.Draw(board)
draw.text((24, 16), "SELECTED DESIGN (uniform scaling)", fill="#1b2232")
draw.text((528, 16), "NATIVE ANDROID 180x420dp / 2.625 density", fill="#1b2232")
board.save(base / "widget-043-comparison.png")
