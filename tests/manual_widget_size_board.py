"""Compose unchanged native widget renders into a labeled QA size matrix."""
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw

base=Path("C:/Users/Abbadon/Documents/Codex/_android-build-tools")
board=Image.new("RGB",(1200,1320),"#e8e3da")
draw=ImageDraw.Draw(board)
for row,cols in enumerate((2,3)):
    for col,cells in enumerate((1,2,3,4)):
        image=Image.open(base/f"widget-043-grid-{cols}x{cells}.png").convert("RGBA")
        image=ImageOps.contain(image,(280,600))
        x=10+col*300
        y=35+row*660
        draw.text((x,y-24),f"{cols} x {cells}",fill="#1b2232")
        board.paste(image,(x,y),image)
board.save(base/"widget-043-size-matrix.png")
