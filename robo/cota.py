"""Cota parlamentar (CEAP) da Câmara — modelo Rosie/OPS, com a voz do canal.

Fonte: arquivo anual oficial da Câmara (https://www.camara.leg.br/cotas/Ano-AAAA.csv.zip).
Primeira execução só cria a base; depois, posta notas novas que disparam um gatilho.
"""
import csv
import io
import zipfile
from collections import defaultdict
from datetime import date, timedelta

import requests

from .shows import valor_exato, valor_manchete

URL = "https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip"

# Cortes iniciais (ajustáveis)
REFEICAO_MIN = 300          # R$ numa única nota de alimentação
MAIOR_DO_DIA_MIN = 5_000    # R$ para o "maior gasto do dia" virar post
FORNECEDOR_GABINETES = 30   # fornecedor atendendo N ou mais deputados no ano
MAX_POSTS = 3
JANELA_DIAS = 60            # só olha notas emitidas nos últimos N dias (mantém o estado pequeno)

CAMPOS = {  # nome lógico -> nomes possíveis no CSV
    "id": ["ideDocumento", "idDocumento"],
    "nome": ["txNomeParlamentar", "nomeParlamentar"],
    "uf": ["sgUF"],
    "partido": ["sgPartido"],
    "tipo": ["txtDescricao", "descricao"],
    "fornecedor": ["txtFornecedor", "fornecedor"],
    "cnpj": ["txtCNPJCPF", "cnpjCPF"],
    "data": ["datEmissao", "dataEmissao"],
    "valor": ["vlrLiquido", "valorLiquido"],
    "url": ["urlDocumento"],
}


def _pega(linha, campo):
    for k in CAMPOS[campo]:
        if k in linha and linha[k] not in (None, ""):
            return linha[k]
    return ""


def _num(txt):
    t = str(txt).strip()
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return 0.0


def baixar(ano):
    r = requests.get(URL.format(ano=ano), timeout=300)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    nome = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
    texto = z.read(nome).decode("utf-8-sig", errors="replace")
    sep = ";" if texto[:2000].count(";") > texto[:2000].count(",") else ","
    linhas = list(csv.DictReader(io.StringIO(texto), delimiter=sep))
    if linhas:
        print(f"  colunas cota: {list(linhas[0].keys())[:30]}")
    notas = []
    for ln in linhas:
        n = {c: _pega(ln, c) for c in CAMPOS}
        n["valor"] = _num(n["valor"])
        n["data"] = (n["data"] or "")[:10]
        n["tipo"] = n["tipo"].strip().rstrip(".")
        if n["id"] and n["valor"] > 0:
            notas.append(n)
    print(f"  cota {ano}: {len(notas)} notas")
    return notas


def _quem(n):
    sigla = f"{n['partido']}-{n['uf']}".strip("-")
    return f"DEP. {n['nome']} ({sigla})".upper()


def _data_br(iso):
    try:
        a, m, d = iso.split("-")
        return f"{d}/{m}/{a}"
    except ValueError:
        return iso


def _fim_de_semana(iso):
    try:
        return date.fromisoformat(iso).weekday() >= 5
    except ValueError:
        return False


def _fato(n, manchete, tipo):
    return {
        "id": "cota-" + str(n["id"]),
        "tipo": tipo,
        "valor": n["valor"],
        "valor_manchete": valor_manchete(n["valor"]),
        "manchete_padrao": manchete,
        "linha_fato": f"{n['fornecedor']} | {valor_exato(n['valor'])} | nota de {_data_br(n['data'])}",
        "contexto": "Cota parlamentar: verba que reembolsa despesas do mandato (comida, combustível, "
                    "passagens, divulgação). É legal; o post só mostra o gasto.",
        "link": n["url"] or "https://www.camara.leg.br/cota-parlamentar/",
    }


def recentes(notas):
    corte = (date.today() - timedelta(days=JANELA_DIAS)).isoformat()
    return [n for n in notas if n["data"] >= corte]


def gatilhos(notas, vistos):
    """Notas novas (recentes) que disparam algum gatilho, já em formato de post."""
    novas = [n for n in recentes(notas) if ("cota-" + str(n["id"])) not in vistos]
    gabinetes = defaultdict(set)
    for n in notas:
        if n["cnpj"]:
            gabinetes[n["cnpj"]].add(n["nome"])

    fatos, usados = [], set()

    def add(n, manchete, tipo):
        if n["id"] not in usados:
            usados.add(n["id"])
            fatos.append(_fato(n, manchete, tipo))

    if novas:
        maior = max(novas, key=lambda n: n["valor"])
        if maior["valor"] >= MAIOR_DO_DIA_MIN:
            add(maior, f"{_quem(maior)} TEM O MAIOR GASTO DO DIA NA COTA: {valor_manchete(maior['valor'])} "
                       f"EM {maior['tipo'].upper()}", "cota_maior")
    for n in sorted(novas, key=lambda n: -n["valor"]):
        t = n["tipo"].upper()
        if "ALIMENTA" in t and n["valor"] >= REFEICAO_MIN:
            add(n, f"{_quem(n)} PEDE REEMBOLSO DE {valor_manchete(n['valor'])} EM UMA REFEIÇÃO", "cota_refeicao")
        elif _fim_de_semana(n["data"]) and "PASSAGEM" not in t and n["valor"] >= 1_000:
            add(n, f"{_quem(n)} USA A COTA NUM FIM DE SEMANA: {valor_manchete(n['valor'])} "
                   f"EM {t}", "cota_fds")
        elif n["cnpj"] and len(gabinetes[n["cnpj"]]) >= FORNECEDOR_GABINETES and n["valor"] >= 5_000:
            add(n, f"{n['fornecedor'].upper()} JÁ ATENDE {len(gabinetes[n['cnpj']])} GABINETES. "
                   f"AGORA {_quem(n)}: {valor_manchete(n['valor'])}", "cota_fornecedor")
    return fatos[:MAX_POSTS], [("cota-" + str(n["id"])) for n in recentes(notas)]
