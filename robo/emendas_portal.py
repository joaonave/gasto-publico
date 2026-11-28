"""Emendas parlamentares pelo arquivo oficial de download do Portal da Transparência (sem chave).

Arquivo "por favorecido": autor, tipo de emenda (ex.: transferência especial = "emenda Pix"), favorecido,
natureza jurídica, município/UF e valor recebido, por mês. Usado no ranking e no cruzamento Pix × prefeitura.
"""
import csv
import io
import unicodedata
import zipfile

import requests

URL = "https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares/UNICO"


def _n(txt):
    t = unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode()
    return " ".join(t.upper().replace(".", " ").split())


def _num(t):
    t = str(t or "").strip().replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return 0.0


def _col(cab, *trechos, evitar=()):
    """Acha a coluna cujo nome normalizado contém todos os trechos."""
    for c in cab:
        nc = _n(c)
        if all(t in nc for t in trechos) and not any(e in nc for e in evitar):
            return c
    return None


def baixar():
    r = requests.get(URL, timeout=600, allow_redirects=True)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    nomes = [n for n in z.namelist() if n.lower().endswith(".csv")]
    print(f"  arquivos no zip: {nomes}")
    principal = next((n for n in nomes if "PorFavorecido" in n), max(nomes, key=lambda n: z.getinfo(n).file_size))
    print(f"  usando: {principal}")
    bruto = z.read(principal)
    try:
        texto = bruto.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = bruto.decode("latin-1")
    leitor = csv.DictReader(io.StringIO(texto), delimiter=";")
    cab = leitor.fieldnames or []
    print(f"  colunas emendas: {cab}")
    c = {
        "codigo": _col(cab, "CODIGO", "EMENDA"),
        "ano": _col(cab, "ANO"),
        "tipo": _col(cab, "TIPO", "EMENDA"),
        "autor": _col(cab, "NOME", "AUTOR"),
        "municipio": _col(cab, "MUNICIPIO", evitar=("CODIGO",)),
        "uf": _col(cab, "UF", evitar=("CODIGO", "FAVORECIDO")) or _col(cab, "UF", evitar=("CODIGO",)),
        "localidade": _col(cab, "LOCALIDADE"),
        "funcao": _col(cab, "NOME", "FUNCAO", evitar=("SUB",)),
        "pago": _col(cab, "VALOR", "RECEBIDO") or _col(cab, "VALOR", "PAGO", evitar=("RESTOS",)),
        "favorecido": _col(cab, "FAVORECIDO", evitar=("CODIGO", "TIPO", "UF", "MUNICIPIO")),
        "cod_favorecido": _col(cab, "CODIGO", "FAVORECIDO"),
        "empenhado": _col(cab, "VALOR", "EMPENHADO"),
        "natureza": _col(cab, "NATUREZA"),
        "tipo_favorecido": _col(cab, "TIPO", "FAVORECIDO"),
    }
    print(f"  mapeamento: {c}")
    linhas = []
    for ln in leitor:
        reg = {k: (ln.get(v) or "").strip() if v else "" for k, v in c.items()}
        reg["pago"] = _num(reg["pago"])
        reg["empenhado"] = _num(reg["empenhado"])
        reg["ano_mes"] = reg["ano"]
        reg["ano"] = "".join(ch for ch in reg["ano"] if ch.isdigit())[:4]
        if reg["codigo"]:
            linhas.append(reg)
    print(f"  emendas no arquivo: {len(linhas)}")
    return linhas
