# Gera assets/icon.ico + assets/icon.png (icone proprio do DX Image Downloader:
# foto (moldura com montanha/sol) + botao play de video + seta de download -
# relacionado a funcao, sem logo DX Labs)
from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).parent / "assets"
OUT.mkdir(parents=True, exist_ok=True)

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# fundo: quadrado arredondado escuro
d.rounded_rectangle([28, 28, S - 28, S - 28], radius=200, fill=(11, 14, 19, 255))

# moldura da foto (borda teal)
d.rounded_rectangle([150, 150, S - 150, 700], radius=48, outline=(46, 196, 182, 255), width=28)
# sol
d.ellipse([560, 230, 700, 370], fill=(46, 196, 182, 255))
# montanhas
d.polygon([(170, 680), (420, 380), (620, 680)], fill=(232, 236, 241, 255))
d.polygon([(450, 680), (700, 420), (854, 680)], fill=(138, 148, 166, 255))

# botao play (video) no centro-direita da foto
d.ellipse([400, 380, 624, 604], fill=(230, 57, 70, 255))
d.polygon([(470, 430), (470, 554), (580, 492)], fill=(255, 255, 255, 255))

# seta de download embaixo
cx = S // 2
d.rectangle([cx - 70, 760, cx + 70, 850], fill=(232, 236, 241, 255))
d.polygon([(cx - 180, 820), (cx + 180, 820), (cx, 960)], fill=(232, 236, 241, 255))

img.save(OUT / "icon.png")
img.save(OUT / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("icon.png / icon.ico gerados em", OUT)
