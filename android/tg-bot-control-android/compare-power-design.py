"""Normalize native capture density and produce a source/implementation QA board."""
from pathlib import Path
from PIL import Image, ImageDraw
root=Path(__file__).parent/"design-evidence"
source=Image.open(root/"selected-power-page.png").convert("RGB")
native=Image.open(root/"power-page-native.png").convert("RGB")
# Native child includes its reserved OS inset padding; remove only that area.
native=native.crop((0,128,native.width,native.height-63))
def fit_width(im,w=390):
    return im.resize((w,round(im.height*w/im.width)),Image.Resampling.LANCZOS)
a,b=fit_width(source),fit_width(native)
a.save(root/"power-source-normalized.png");b.save(root/"power-native-normalized.png")
board=Image.new("RGB",(820,max(a.height,b.height)+30),"#e4e4e4")
board.paste(a,(10,30));board.paste(b,(420,30))
draw=ImageDraw.Draw(board);draw.text((10,8),"Selected visual target",fill="black");draw.text((420,8),"Native Android implementation",fill="black")
board.save(root/"power-comparison.png")
# Focused readable top section to inspect icons, type and semantic colors.
focus=Image.new("RGB",(820,580),"#e4e4e4");focus.paste(a.crop((0,0,390,550)),(10,30));focus.paste(b.crop((0,0,390,550)),(420,30));focus.save(root/"power-focus.png")
matrix=Image.new("RGB",(1200,700),"#e4e4e4");draw=ImageDraw.Draw(matrix)
for col,w in enumerate((180,260)):
    for row,h in enumerate((80,180,300,420)):
        im=Image.open(root/f"widget-045-{w}x{h}.png").convert("RGBA")
        im.thumbnail((230,430),Image.Resampling.LANCZOS)
        x=row*300+(300-im.width)//2;y=40+col*330
        if im.height>280:
            im=im.resize((round(im.width*280/im.height),280),Image.Resampling.LANCZOS)
        matrix.paste(im,(row*300+(300-im.width)//2,y),im)
        draw.text((row*300+20,y-20),f"{2+col} x {row+1} ({w}x{h} dp)",fill="black")
matrix.save(root/"widget-045-matrix.png")
print("Source:",source.size,"Native full:",native.size,"Normalized:",a.size,b.size)
