"""Card de imagem (1200x675) com a identidade da conta: fundo verde, destaque amarelo."""
import re
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

VERDE, AMARELO, BRANCO = (15, 61, 34), (232, 178, 26), (255, 255, 255)
FONTES = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
          "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]


def _fonte(tam):
    for f in FONTES:
        if Path(f).exists():
            return ImageFont.truetype(f, tam)
    return ImageFont.load_default()


def gerar(f, destino: Path):
    img = Image.new("RGB", (1200, 675), VERDE)
    d = ImageDraw.Draw(img)
    # valor em destaque
    valor = f.get("valor_manchete", "")
    d.text((70, 60), valor, font=_fonte(110), fill=AMARELO)
    # manchete sem o valor (já está grande acima)
    manchete = f.get("manchete_padrao") or ""
    manchete = re.sub(re.escape(valor) + r"\s*", "", manchete).strip()
    y = 220
    for linha in textwrap.wrap(manchete, width=34)[:5]:
        d.text((70, y), linha, font=_fonte(52), fill=BRANCO)
        y += 66
    d.text((70, 600), "@ImpostoFoiPra  ·  dados oficiais", font=_fonte(32), fill=AMARELO)
    destino.parent.mkdir(parents=True, exist_ok=True)
    img.save(destino, "PNG", optimize=True)
    return destino
