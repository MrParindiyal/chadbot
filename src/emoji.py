from PIL import Image, ImageDraw, ImageFont

dim = 128
colors = {
    "green" : (4,110,0),
    "yellow" : (138,131,0),
    "grey" : (48,48,48)
}

for color in colors:
	for char_idx in range(26):	
		img = Image.new('RGB', (dim, dim), color=colors[color])
		draw = ImageDraw.Draw(img)
		try:
			font = ImageFont.truetype("./font/ARLRDBD.TTF", 128)
		except IOError:
			print("Falling to default")
			font = ImageFont.load_default(size=140)
		text = chr(65+char_idx)
		draw.text((dim/2,dim/2), text, fill=(255, 255, 255), font=font, anchor="mm")
		img.save(f"./emoji_output/{color}_{text}.png")