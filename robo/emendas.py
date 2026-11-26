"""Emendas Pix (Transferegov) + cadastro de parlamentares (Câmara e Senado).

Fase 1:
- "emenda nova": compara o retrato de hoje com o de ontem e acha planos de ação novos.
- "fora do estado": destino em UF diferente da UF do parlamentar.
- "raio-x": um parlamentar por dia, em rodízio sorteado e fixo, com tudo o que mandou desde 2020.
"""
import json
import random
import time
import unicodedata
from datetime import datetime
from collections import defaultdict
from pathlib import Path

import requests

TRANSFEREGOV = "https://api.transferegov.gestao.gov.br/transferenciasespeciais/plano_acao_especial"
CAMARA = "https://dadosabertos.camara.leg.br/api/v2/deputados"
SENADO = "https://legis.senado.leg.br/dadosabertos/senador/lista/atual.json"
ANOS = list(range(2020, datetime.now().year + 1))
PAGINA = 1000


def norm(txt):
    t = unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode()
    return " ".join(t.upper().replace(".", " ").split())


def _get_json(url, params=None, tentativas=4):
    for i in range(tentativas):
        try:
            r = requests.get(url, params=params, timeout=90, headers={"Accept": "application/json"})
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(20 * (i + 1))
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            print(f"  erro {url}: {e}")
            time.sleep(20 * (i + 1))
    raise RuntimeError(f"falhou: {url} {params}")


# ---------- Transferegov ----------

def _campo(reg, *trechos):
    """Acha o valor do primeiro campo cujo nome contém todos os trechos (nomes da API são longos)."""
    for k, v in reg.items():
        if all(t in k for t in trechos):
            return v
    return None


def _valor(reg):
    total = 0.0
    for k, v in reg.items():
        if k.startswith("valor_") and ("custeio" in k or "investimento" in k):
            try:
                total += float(v or 0)
            except (TypeError, ValueError):
                pass
    return total


def planos_do_ano(ano):
    itens, offset = [], 0
    while True:
        lote = _get_json(TRANSFEREGOV, {"ano_plano_acao": f"eq.{ano}", "limit": PAGINA, "offset": offset})
        itens.extend(lote)
        if len(lote) < PAGINA:
            break
        offset += PAGINA
        time.sleep(2)
    return itens


def resumir(reg):
    return {
        "id": str(_campo(reg, "id_plano_acao") or _campo(reg, "codigo_plano_acao")),
        "ano": _campo(reg, "ano_plano_acao"),
        "parlamentar": norm(_campo(reg, "nome_parlamentar") or ""),
        "emenda": str(_campo(reg, "numero_emenda") or ""),
        "beneficiario": (_campo(reg, "nome_beneficiario") or "").strip(),
        "uf_destino": _campo(reg, "uf_beneficiario") or "",
        "situacao": _campo(reg, "situacao_plano_acao") or "",
        "valor": _valor(reg),
    }


# ---------- Parlamentares ----------

def parlamentares():
    """Dicionário NOME NORMALIZADO -> {nome, cargo, partido, uf}."""
    lista = {}
    dep = _get_json(CAMARA, {"itens": 1000, "ordem": "ASC", "ordenarPor": "nome"})
    for d in dep.get("dados", []):
        lista[norm(d["nome"])] = {"nome": d["nome"], "cargo": "Dep.", "partido": d.get("siglaPartido", ""),
                                  "uf": d.get("siglaUf", "")}
    try:
        sen = _get_json(SENADO)
        for p in sen["ListaParlamentarEmExercicio"]["Parlamentares"]["Parlamentar"]:
            i = p["IdentificacaoParlamentar"]
            lista[norm(i["NomeParlamentar"])] = {"nome": i["NomeParlamentar"], "cargo": "Sen.",
                                                 "partido": i.get("SiglaPartidoParlamentar", ""),
                                                 "uf": i.get("UfParlamentar", "")}
    except Exception as e:  # noqa: BLE001
        print(f"  Senado indisponível: {e}")
    return lista


# ---------- Gatilhos ----------

def novos_planos(hoje, ontem_ids):
    return [p for p in hoje if p["id"] not in ontem_ids and p["valor"] > 0]


def proximo_raio_x(estado, cadastro):
    """Rodízio fixo: sorteia a ordem uma vez (semente pública) e avança um por dia."""
    if not estado.get("ordem_raio_x"):
        nomes = sorted(cadastro)
        random.Random(2026).shuffle(nomes)
        estado["ordem_raio_x"] = nomes
        estado["pos_raio_x"] = 0
    ordem = estado["ordem_raio_x"]
    nome = ordem[estado.get("pos_raio_x", 0) % len(ordem)]
    estado["pos_raio_x"] = estado.get("pos_raio_x", 0) + 1
    return nome


def raio_x(nome, todos_planos, cadastro):
    p = cadastro.get(nome, {})
    meus = [x for x in todos_planos if x["parlamentar"] == nome and x["valor"] > 0]
    if not meus:
        return None
    total = sum(x["valor"] for x in meus)
    por_destino = defaultdict(float)
    por_ano = defaultdict(float)
    fora = 0.0
    for x in meus:
        por_destino[(x["beneficiario"], x["uf_destino"])] += x["valor"]
        por_ano[x["ano"]] += x["valor"]
        if p.get("uf") and x["uf_destino"] and x["uf_destino"] != p["uf"]:
            fora += x["valor"]
    top = sorted(por_destino.items(), key=lambda kv: kv[1], reverse=True)[:5]
    return {
        "nome": p.get("nome", nome.title()), "cargo": p.get("cargo", ""), "partido": p.get("partido", ""),
        "uf": p.get("uf", ""), "total": total, "qtd": len(meus), "destinos": len(por_destino),
        "top": [{"destino": d, "uf": u, "valor": v} for (d, u), v in top],
        "por_ano": dict(sorted(por_ano.items())), "fora_do_estado": fora,
    }


def carregar_tudo(pasta: Path, anos=ANOS):
    """Baixa todos os anos (cache em disco para anos fechados) e devolve lista resumida."""
    pasta.mkdir(parents=True, exist_ok=True)
    todos = []
    ano_atual = max(anos)
    for ano in anos:
        arq = pasta / f"pix_{ano}.json"
        if ano < ano_atual and arq.exists():
            todos.extend(json.loads(arq.read_text(encoding="utf-8")))
            continue
        brutos = planos_do_ano(ano)
        if ano == ano_atual and brutos:
            print(f"  campos Transferegov: {sorted(brutos[0].keys())}")
        resumidos = [resumir(b) for b in brutos]
        print(f"  Transferegov {ano}: {len(resumidos)} planos")
        arq.write_text(json.dumps(resumidos, ensure_ascii=False), encoding="utf-8")
        todos.extend(resumidos)
    return todos
