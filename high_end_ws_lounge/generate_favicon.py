from PIL import Image
import os

source = "static/img/main_logo.png"
output = "static/img/favicon.png"

img = Image.open(source).convert("RGBA")

alpha = img.getchannel("A")
bbox = alpha.getbbox()

if bbox:
    img = img.crop(bbox)

padding = 20
size = max(img.width, img.height) + (padding * 2)

canvas = Image.new("RGBA", (size, size), "white")

x = (size - img.width) // 2
y = (size - img.height) // 2

canvas.alpha_composite(img, (x, y))

canvas = canvas.resize((256, 256), Image.Resampling.LANCZOS)

canvas.save(output, "PNG")

print(f"Favicon generated: {output}")