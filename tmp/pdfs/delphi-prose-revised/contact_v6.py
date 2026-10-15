from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).parent
files = sorted(root.glob("delphi-v6-??.png"))
sheet = Image.new("RGB", (1600, 910), "#e8edf2")
for i, path in enumerate(files):
    im = Image.open(path).convert("RGB")
    im.thumbnail((300, 424))
    x, y = (i % 5) * 320, (i // 5) * 455
    sheet.paste(im, (x + (320 - im.width) // 2, y + 20))
    ImageDraw.Draw(sheet).text((x + 12, y + 4), path.stem, fill="#173A5E")
sheet.save(root / "delphi-v6-contact.png")
