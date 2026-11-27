"""Emenda Pix (transferência especial: dinheiro no caixa da prefeitura sem finalidade definida) × gasto da prefeitura.

Narrativa: prefeitura recebeu Pix de emenda e contratou show/publicidade/compra inusitada, numa cidade sem esgoto.
São dois fatos oficiais lado a lado; o post não afirma que o mesmo dinheiro pagou o show.
"""
import re
import unicodedata
from datetime import datetime

MESES = "janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro".split()
JANELA_MESES = 12
PIX_MIN = 100_000


def _n(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.upper()).strip()


def _mes_menos(am, k):
    a, m = int(am[:4]), int(am[4:6])
    t = a * 12 + (m - 1) - k
    return f"{t // 12}{t % 12 + 1:02d}"


def indice(linhas, hoje=None):
    """{(MUNICIPIO, UF): {autor: {"total": v, "ultimo_mes": "AAAAMM"}}} dos Pix pagos nos últimos 12 meses a municípios."""
    hoje = hoje or datetime.now()
    desde = _mes_menos(hoje.strftime("%Y%m"), JANELA_MESES)
    idx = {}
    for r in linhas:
        if "ESPECIA" not in (r.get("tipo") or "").upper() or (r.get("natureza") or "") != "Município":
            continue
        am = str(r.get("ano_mes") or "")
        if len(am) < 6 or am < desde or not (r.get("pago") or 0) > 0:
            continue
        k = (_n(r.get("municipio")), r.get("uf"))
        a = idx.setdefault(k, {}).setdefault(r["autor"], {"total": 0.0, "ultimo_mes": am})
        a["total"] += r["pago"]
        a["ultimo_mes"] = max(a["ultimo_mes"], am)
    return idx


def anexar(f, idx, cadastro):
    """Anexa ao fato do PNCP o maior Pix recebido pela cidade nos últimos 12 meses (se houver)."""
    from .emendas import norm
    if not re.search(r"munic|prefeit", f.get("orgao") or "", re.IGNORECASE):
        return
    autores = idx.get((_n(f.get("municipio")), f.get("uf")))
    if not autores:
        return
    autor, d = max(autores.items(), key=lambda kv: kv[1]["total"])
    if d["total"] < PIX_MIN:
        return
    cad = cadastro.get(norm(autor))
    if not cad:
        return
    f["pix"] = {"autor": f"{cad.get('cargo', '')} {cad.get('nome', autor)} ({cad.get('partido', '')}-{cad.get('uf', '')})".strip(), "total": d["total"], "mes": d["ultimo_mes"],
                "total_cidade": sum(x["total"] for x in autores.values()), "n_autores": len(autores)}


def mes_extenso(am, ano_atual):
    m = MESES[int(am[4:6]) - 1]
    return m if int(am[:4]) == ano_atual else f"{m} de {am[:4]}"
