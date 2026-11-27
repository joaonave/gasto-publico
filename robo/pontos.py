"""Sistema de pontos: decide o que vira post no dia.

Nota = tamanho relativo + indício + interesse do público.
- Tamanho relativo: R$ por habitante do município (IBGE). Contrato de R$ 400 mil em cidade de
  8 mil habitantes pesa mais que em BH.
- Indício: sinais que se somam (sem licitação, verba fora do estado do parlamentar, gasto alto na cota...).
- Interesse: peso por categoria. Começa igual para todas; depois é ajustado pelo engajamento (Buffer).
Depois da nota, valem os limites por categoria e o teto do dia.
"""
import json
import re
import unicodedata
from pathlib import Path

import requests

LIMITE_DIA = {"show": 3, "midia": 2, "inusitada": 2, "emenda": 3, "cota": 3, "raiox": 2}
TETO_DIA = 10
INTERESSE = {"show": 1, "midia": 1, "inusitada": 1, "emenda": 1, "cota": 1, "raiox": 99}

IBGE_MUN = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
IBGE_POP = ("https://servicodados.ibge.gov.br/api/v3/agregados/6579/periodos/-1/variaveis/9324"
            "?localidades=N6[all]")
_SEM_LICITACAO = re.compile(r"inexigibilidade|inexig[íi]vel|dispensa de licita", re.IGNORECASE)


def _n(t):
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    return " ".join(t.upper().split())


def categoria(f):
    t = f.get("tipo", "")
    return next((c for c in LIMITE_DIA if t.startswith(c)), "show")


class Populacao:
    def __init__(self, arq: Path):
        self.por_cod, self.por_nome = {}, {}
        try:
            if arq.exists():
                d = json.loads(arq.read_text(encoding="utf-8"))
            else:
                d = self._baixar()
                arq.parent.mkdir(parents=True, exist_ok=True)
                arq.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            self.por_cod = d["por_cod"]
            self.por_nome = d["por_nome"]
            print(f"  população IBGE: {len(self.por_cod)} municípios")
        except Exception as e:  # noqa: BLE001
            print(f"  população IBGE indisponível: {e}")

    @staticmethod
    def _baixar():
        pop = {}
        dados = requests.get(IBGE_POP, timeout=120).json()
        for serie in dados[0]["resultados"][0]["series"]:
            valores = [v for v in serie["serie"].values() if str(v).isdigit()]
            if valores:
                pop[str(serie["localidade"]["id"])] = int(valores[-1])
        nomes = {}
        for m in requests.get(IBGE_MUN, timeout=120).json():
            try:
                uf = (m.get("microrregiao") or {})["mesorregiao"]["UF"]["sigla"]
            except (KeyError, TypeError):
                uf = m["regiao-imediata"]["regiao-intermediaria"]["UF"]["sigla"]
            nomes[f"{_n(m['nome'])}|{uf}"] = str(m["id"])
        return {"por_cod": pop, "por_nome": nomes}

    def cod(self, f):
        cod = str(f.get("cod_ibge") or "")[:7]
        if not cod and f.get("municipio") and f.get("uf"):
            cod = self.por_nome.get(f"{_n(f['municipio'])}|{f['uf']}", "")
        return cod

    def de(self, f):
        return self.por_cod.get(self.cod(f))


def nota(f, pop):
    cat = categoria(f)
    pontos = INTERESSE.get(cat, 1)
    # tamanho relativo
    hab = pop.de(f) if pop else None
    if hab:
        por_hab = f["valor"] / hab
        f["por_habitante"] = por_hab
        pontos += 3 if por_hab >= 10 else 2 if por_hab >= 2 else 1 if por_hab >= 0.5 else 0
    elif cat == "cota":
        pontos += 2 if f["valor"] >= 20_000 else 1 if f["valor"] >= 5_000 else 0
    # indícios
    if _SEM_LICITACAO.search(f.get("objeto", "")):
        pontos += 1
    if f.get("tipo") == "emenda_fora":
        pontos += 3
    if f.get("tipo") in ("cota_fds", "cota_refeicao", "cota_fornecedor"):
        pontos += 1
    if f.get("qtd_contratos", 1) > 1:
        pontos += 1
    # público: artista identificado dá busca e engajamento; MC (funk) mais ainda
    if f.get("artista"):
        pontos += 2
        if re.search(r"\bMC\b", f["artista"], re.IGNORECASE):
            pontos += 2
    elif categoria(f) == "show" and re.search(r"\bMC\b", f.get("fornecedor", ""), re.IGNORECASE):
        pontos += 3
    pontos += f.get("mencoes", 0)  # raio-X: mais citado no noticiário vem primeiro
    f["nota"] = pontos
    return pontos


def escolher(candidatos, estado, hoje, pop):
    """Aplica a nota, os limites por categoria e o teto do dia (somando as execuções do dia)."""
    if estado.get("pub_dia") != hoje:
        estado["pub_dia"], estado["pub_qtd"], estado["pub_cat"] = hoje, 0, {}
    usados = estado.setdefault("pub_cat", {})
    for f in candidatos:
        nota(f, pop)
    escolhidos = []
    for f in sorted(candidatos, key=lambda f: (-f["nota"], -f["valor"])):
        cat = categoria(f)
        if estado["pub_qtd"] + len(escolhidos) >= TETO_DIA:
            break
        ja = usados.get(cat, 0) + sum(1 for e in escolhidos if categoria(e) == cat)
        if ja < LIMITE_DIA.get(cat, 2):
            escolhidos.append(f)
    # volume: se os limites por categoria deixaram vaga no teto, completa com as maiores notas restantes
    for f in sorted(candidatos, key=lambda f: (-f["nota"], -f["valor"])):
        if estado["pub_qtd"] + len(escolhidos) >= TETO_DIA:
            break
        if f not in escolhidos and f["nota"] > 0:
            escolhidos.append(f)
    # intercala categorias na ordem de publicação
    fila, restantes = [], list(escolhidos)
    while restantes:
        vistos_cat = set()
        for f in list(restantes):
            c = categoria(f)
            if c not in vistos_cat:
                fila.append(f)
                vistos_cat.add(c)
                restantes.remove(f)
    return fila


def registrar(estado, publicados):
    for f in publicados:
        c = categoria(f)
        estado["pub_cat"][c] = estado["pub_cat"].get(c, 0) + 1
        estado["pub_qtd"] += 1
