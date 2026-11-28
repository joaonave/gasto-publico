"""Busca emendas no arquivo principal do Portal (ação, programa, localidade) por um termo.

Uso: python -m robo.busca_emenda "BR-265" ["REGINALDO LOPES"]
Mostra as emendas cuja ação/plano/localidade cita o termo: autor, ano, ação, empenhado e pago.
"""
import csv
import io
import re
import sys
import unicodedata
import zipfile
from collections import defaultdict

import requests

from .emendas_portal import URL


def _n(t):
    return " ".join(unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().upper().split())


def _v(t):
    try:
        return float((t or "0").replace(".", "").replace(",", "."))
    except ValueError:
        return 0.0


def buscar(termo, autor=""):
    z = zipfile.ZipFile(io.BytesIO(requests.get(URL, timeout=600).content))
    bruto = z.read("EmendasParlamentares.csv")
    try:
        texto = bruto.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = bruto.decode("latin-1")
    rx = re.compile(re.sub(r"[\s\-]+", r"[\\s\\-/]*", re.escape(_n(termo)).replace("\\", "")) + r"(?!\d)", re.IGNORECASE)
    achadas, por_autor = [], defaultdict(lambda: [0.0, 0.0])
    for ln in csv.DictReader(io.StringIO(texto), delimiter=";"):
        alvo = " ".join(_n(ln.get(k, "")) for k in ln if k and any(t in _n(k) for t in ("ACAO", "PLANO", "LOCALIDADE", "SUBTITULO")))
        if not rx.search(alvo):
            continue
        nome = ln.get("Nome do Autor da Emenda", "")
        pago = _v(ln.get("Valor Pago")) + _v(ln.get("Valor Restos A Pagar Pagos"))
        por_autor[nome][0] += _v(ln.get("Valor Empenhado"))
        por_autor[nome][1] += pago
        if not autor or _n(autor) in _n(nome):
            achadas.append(ln)
    out = [f"# Emendas que citam '{termo}'" + (f" – autor {autor}" if autor else ""), "",
           "Fonte: Portal da Transparência, arquivo de emendas (empenhado e pago, incluindo restos a pagar pagos).", ""]
    for ln in sorted(achadas, key=lambda l: l.get("Ano da Emenda", "")):
        campos = {k: v for k, v in ln.items() if k and v and v.strip() not in ("0,00", "0", "-")}
        out.append("- " + " | ".join(f"{k}: {v}" for k, v in campos.items() if any(
            t in _n(k) for t in ("ANO", "NUMERO", "AUTOR", "TIPO", "LOCALIDADE", "FUNCAO", "ACAO", "PLANO", "EMPENHADO", "PAGO"))
            and "CODIGO" not in _n(k)))
    out += ["", "## Todos os autores com emenda que cita o termo (empenhado | pago)"]
    for nome, (e, p) in sorted(por_autor.items(), key=lambda kv: -kv[1][1]):
        out.append(f"- {nome}: R$ {e/1e6:.2f} mi | R$ {p/1e6:.2f} mi")
    return "\n".join(out)


if __name__ == "__main__":
    print(buscar(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ""))
