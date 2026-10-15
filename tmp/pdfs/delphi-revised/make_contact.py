from pathlib import Path
from PIL import Image, ImageOps, ImageDraw

root = Path(__file__).parent
for prefix, outname in [("template", "template-contact.png"), ("delphi", "delphi-contact.png")]:
    files = sorted(root.glob(prefix + "-*.png"))
    thumbs = []
    for f in files:
        im = Image.open(f).convert("RGB")
        im.thumbnail((300, 424))
        card = Image.new("RGB", (320, 455), "white")
        card.paste(im, ((320 - im.width) // 2, 20))
        ImageDraw.Draw(card).text((12, 4), f.stem, fill="#173A5E")
        thumbs.append(card)
    sheet = Image.new("RGB", (320 * 5, 455 * 2), "#e8edf2")
    for i, im in enumerate(thumbs):
        sheet.paste(im, ((i % 5) * 320, (i // 5) * 455))
    sheet.save(root / outname)
