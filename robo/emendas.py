"""Cadastro de deputados e senadores em exercício (APIs da Câmara e do Senado), com cópia salva."""
import json
import time
import unicodedata
from pathlib import Path

import requests

CAMARA = "https://dadosabertos.camara.leg.br/api/v2/deputados"
SENADO = "https://legis.senado.leg.br/dadosabertos/senador/lista/atual.json"


def norm(txt):
    t = unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode()
    return " ".join(t.upper().replace(".", " ").split())


def _get_json(url, params=None, tentativas=4, timeout=90):
    for i in range(tentativas):
        try:
            r = requests.get(url, params=params, timeout=timeout, headers={"Accept": "application/json"})
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(20 * (i + 1))
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            print(f"  erro {url}: {e}")
            time.sleep(20 * (i + 1))
    raise RuntimeError(f"falhou: {url} {params}")


_CACHE_CAD = Path(__file__).resolve().parent.parent / "dados" / "parlamentares.json"


def parlamentares():
    """Dicionário NOME NORMALIZADO -> {nome, cargo, partido, uf}. Se a API da Câmara cair, usa a última cópia
    salva (teste integrado de 27/11: a API ficou fora 17 min e derrubou ranking e Pix)."""
    try:
        lista = _parlamentares_api()
        if len(lista) > 500:
            _CACHE_CAD.parent.mkdir(exist_ok=True)
            _CACHE_CAD.write_text(json.dumps(lista, ensure_ascii=False), encoding="utf-8")
        return lista
    except Exception as e:  # noqa: BLE001
        if _CACHE_CAD.exists():
            print(f"  cadastro: API indisponível ({str(e)[:80]}); usando cópia salva")
            return json.loads(_CACHE_CAD.read_text(encoding="utf-8"))
        raise


def _parlamentares_api():
    lista = {}
    dep = _get_json(CAMARA, {"itens": 1000, "ordem": "ASC", "ordenarPor": "nome"}, tentativas=2, timeout=40)
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
