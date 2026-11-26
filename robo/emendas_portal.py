"""Emendas parlamentares pelo arquivo oficial de download do Portal da Transparência (sem chave).

Arquivo único com todas as emendas desde 2014: autor, localidade do gasto (município/UF),
valores empenhado, liquidado e pago. O robô compara o "valor pago" de hoje com o de ontem:
a diferença é o que foi pago no dia.
"""
import csv
import io
import json
import unicodedata
import zipfile
from pathlib import Path

import requests

URL = "https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares/UNICO"
MAX_POSTS = 3
PAGO_MIN = 300_000  # R$ pagos no dia para virar post


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


def _chave(r):
    # uma emenda pode ter várias linhas (uma por localidade/função): a chave junta tudo
    return "|".join([r["codigo"], r.get("cod_favorecido", ""), r.get("ano_mes", ""), r["funcao"]])


def pagamentos_do_dia(linhas, arq_estado: Path, ano):
    """Compara o valor pago acumulado com o da última execução. Retorna (pagamentos, primeira_vez)."""
    atuais = {}
    for r in linhas:
        if str(r["ano"]) == str(ano):
            k = _chave(r)
            if k in atuais:
                atuais[k] = dict(atuais[k], pago=atuais[k]["pago"] + r["pago"])
            else:
                atuais[k] = r
    anteriores = json.loads(arq_estado.read_text(encoding="utf-8")) if arq_estado.exists() else None
    arq_estado.parent.mkdir(parents=True, exist_ok=True)
    arq_estado.write_text(json.dumps({k: r["pago"] for k, r in atuais.items()}), encoding="utf-8")
    if anteriores is None:
        return [], True
    pagos = []
    for k, r in atuais.items():
        delta = r["pago"] - anteriores.get(k, 0.0)
        if delta >= PAGO_MIN:
            pagos.append(dict(r, pago_dia=delta))
    return pagos, False


def para_planos(linhas):
    """Formato usado pelo raio-X (soma do valor pago por emenda/destino)."""
    return [{"id": _chave(r), "ano": r["ano"], "parlamentar": _n(r["autor"]), "emenda": r["codigo"],
             "beneficiario": r["municipio"] or r["localidade"], "uf_destino": r["uf"],
             "situacao": "", "valor": r["pago"]} for r in linhas]
