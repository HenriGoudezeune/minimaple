"""Maakt assets/mini-Maple.ico naar het favicon (Hg-logo). Vereist Pillow."""
import sys
from PIL import Image, ImageDraw, ImageFont
out = sys.argv[1]
S = 256
im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(im)
k = S / 32
d.rounded_rectangle([0, 0, S - 1, S - 1], radius=int(8 * k), fill="#1d1d1f")
f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", int(15 * k))
d.text((16 * k, 19.5 * k), "Hg", font=f, fill="#ffffff", anchor="ms")
d.rectangle([9 * k, 23 * k, 23 * k, 25.4 * k], fill="#FF7A1A")
im.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
