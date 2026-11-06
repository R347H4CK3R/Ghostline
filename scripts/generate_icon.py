"""Build a deterministic, original deep-purple GHOSTLINE icon.
Uses Pillow locally to emit AppIcon.png; generated PNG is tracked for Xcode CI.
No text or copyrighted character likenesses are used.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
import math

SIZE = 1024
out = Path(__file__).resolve().parents[1] / "Ghostline" / "Assets.xcassets" / "AppIcon.appiconset" / "AppIcon-1024.png"
out.parent.mkdir(parents=True, exist_ok=True)

# Edge-darkened violet background with a soft central stage light.
image = Image.new("RGB", (SIZE, SIZE))
pixels = image.load()
for y in range(SIZE):
    for x in range(SIZE):
        r = math.hypot((x - 512) / 690, (y - 430) / 740)
        light = max(0.0, 1.0 - r * 1.05)
        pixels[x, y] = (int(10 + 29 * light), int(2 + 4 * light), int(24 + 51 * light))

def bloom(draw_fn, tint, blur=42, alpha=150):
    layer = Image.new("RGBA", (SIZE, SIZE))
    mask = Image.new("L", (SIZE, SIZE))
    draw_fn(ImageDraw.Draw(mask))
    mask = mask.filter(ImageFilter.GaussianBlur(blur)).point(lambda p: int(p * alpha / 255))
    layer.paste(tint, (0, 0, SIZE, SIZE), mask)
    image.paste(Image.alpha_composite(image.convert("RGBA"), layer).convert("RGB"))

def polygon(points, fill):
    ImageDraw.Draw(image).polygon(points, fill=fill)

# Hood and mantle silhouette; original symbolic design, not a movie costume.
outer = [(95, 773), (174, 595), (238, 399), (337, 223), (430, 126),
         (512, 100), (594, 126), (686, 223), (786, 399),
         (850, 595), (929, 773), (796, 892), (666, 950),
         (512, 970), (358, 950), (228, 892)]
bloom(lambda d: d.polygon(outer, fill=255), (140, 22, 255, 255), 57, 185)
polygon(outer, (72, 10, 141))
inner_hood = [(160, 778), (238, 560), (284, 402), (377, 253),
              (448, 197), (512, 183), (576, 197), (647, 253),
              (740, 402), (786, 560), (864, 778),
              (708, 900), (512, 939), (316, 900)]
polygon(inner_hood, (110, 19, 186))
face = [(275, 575), (318, 432), (390, 342), (462, 298),
        (512, 283), (562, 298), (634, 342), (706, 432),
        (749, 575), (698, 783), (512, 849), (326, 783)]
bloom(lambda d: d.polygon(face, fill=255), (10, 0, 18, 255), 16, 180)
polygon(face, (12, 3, 29))

# Oversized inward-tilted violet eyes for a recognizable small icon.
left_eye = [(362, 493), (415, 503), (458, 530), (475, 556), (421, 544), (382, 520)]
right_eye = [(662, 493), (609, 503), (566, 530), (549, 556), (603, 544), (642, 520)]
bloom(lambda d: [d.polygon(s, fill=255) for s in (left_eye, right_eye)], (220, 86, 255, 255), 26, 230)
for s in (left_eye, right_eye):
    polygon(s, (231, 102, 255))

# Neon horizontal baseline and symmetric audio spectrum.
bloom(lambda d: d.rounded_rectangle((100, 724, 924, 731), radius=4, fill=255), (213, 23, 255, 255), 24, 225)
ImageDraw.Draw(image).rounded_rectangle((113, 726, 911, 729), radius=2, fill=(227, 120, 255))
heights = [28, 58, 91, 151, 218, 168, 272, 394, 270, 172, 220, 155, 95, 60, 28]
center_x, center_y, gap, width = 512, 728, 42, 22
start_x = center_x - (len(heights) - 1) * gap / 2
bloom(lambda d: [d.rounded_rectangle((int(start_x+i*gap-width/2), int(center_y-h/2),
                                      int(start_x+i*gap+width/2), int(center_y+h/2)),
                                     radius=11, fill=255) for i, h in enumerate(heights)],
      (201, 32, 255, 255), 29, 235)
draw = ImageDraw.Draw(image)
for i, h in enumerate(heights):
    x = int(start_x + i * gap)
    draw.rounded_rectangle((x - width//2, center_y-h//2, x+width//2, center_y+h//2),
                           radius=11, fill=(202, 61, 252))
    draw.line((x, center_y-h//2+10, x, center_y+h//2-10),
              fill=(247, 146, 255), width=3)

# Subtle rim illumination to separate the cloak from the background.
rim = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
rimdraw = ImageDraw.Draw(rim)
rimdraw.line(outer[3:10], fill=(255, 86, 251, 125), width=10, joint="curve")
rim = rim.filter(ImageFilter.GaussianBlur(7))
image = Image.alpha_composite(image.convert("RGBA"), rim).convert("RGB")
image.save(out, format="PNG", optimize=True)
print(out, out.stat().st_size)
