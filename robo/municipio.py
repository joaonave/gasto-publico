"""Dados oficiais do município para o 1º comentário: IDHM (PNUD via IBGE Cidades) e saneamento (IBGE, Censo 2022).

Consulta por município, só para os posts do dia, com cache em dados/municipios.json.
Tabelas verificadas pela sonda (dados/sonda): SIDRA 6909 (água), 7555 (esgoto), IBGE Cidades pesquisa 10111 (IDHM).
"""
import json
from pathlib import Path

import requests

SIDRA = "https://apisidra.ibge.gov.br/values"
CIDADES = "https://servicodados.ibge.gov.br/api/v1/pesquisas/10111/resultados/{cod}"
IDHM_IND = 329756
# % dos moradores (variável 1000382), total de idade (c58/95253) e cor (c86/95251)
AGUA = "/t/6909/n6/{cod}/v/1000382/p/2022/c301/31471/c1817/72125/c58/95253/c86/95251"  # rede geral de distribuição
ESGOTO = "/t/7555/n6/{cod}/v/1000382/p/2022/c11558/46290/c58/95253/c86/95251"           # rede geral, pluvial ou fossa ligada à rede


def faixa_idhm(v):
    # faixas do PNUD/Atlas Brasil
    return ("muito baixo" if v < 0.5 else "baixo" if v < 0.6 else "médio" if v < 0.7
            else "alto" if v < 0.8 else "muito alto")


def _num(t):
    t = str(t).strip().replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None  # "-", "X" (sigilo), "..."


def _sidra(caminho, cod):
    r = requests.get(SIDRA + caminho.format(cod=cod), timeout=60)
    r.raise_for_status()
    linhas = r.json()
    return _num(linhas[1]["V"]) if len(linhas) > 1 else None


def _idhm(cod):
    r = requests.get(CIDADES.format(cod=cod), timeout=60)
    r.raise_for_status()
    for ind in r.json():
        if ind.get("id") == IDHM_IND and ind.get("res"):
            return _num(ind["res"][0]["res"].get("2010"))
    return None


class Municipios:
    def __init__(self, arq: Path):
        self.arq = arq
        self.cache = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}

    def dados(self, cod):
        cod = str(cod or "")[:7]
        if len(cod) != 7:
            return {}
        if cod in self.cache:
            return self.cache[cod]
        d = {}
        for chave, fn in (("idhm", lambda: _idhm(cod)), ("agua", lambda: _sidra(AGUA, cod)),
                          ("esgoto", lambda: _sidra(ESGOTO, cod))):
            try:
                v = fn()
                if v is not None:
                    d[chave] = v
            except Exception as e:  # noqa: BLE001
                print(f"  município {cod}: {chave} indisponível ({str(e)[:80]})")
        if d:
            self.cache[cod] = d
        return d

    def salvar(self):
        self.arq.parent.mkdir(parents=True, exist_ok=True)
        self.arq.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")


def _pct(v):
    return f"{v:.1f}".replace(".", ",") + "%"


def comentario(f, d, populacao=None):
    """Texto do 1º comentário (sem o link). Vazio se não houver dado."""
    if not d or not f.get("municipio"):
        return ""
    linhas = [f"📊 {f['municipio'].upper()} ({f.get('uf', '')})"]
    if populacao:
        linhas.append(f"População: {populacao:,}".replace(",", ".") + " (IBGE)")
    if "idhm" in d:
        linhas.append(f"IDHM {d['idhm']:.3f}".replace(".", ",") + f", {faixa_idhm(d['idhm'])} (PNUD, 2010)")
    if "agua" in d:
        linhas.append(f"Água da rede geral: {_pct(d['agua'])} dos moradores")
    if "esgoto" in d:
        linhas.append(f"Esgoto na rede geral: {_pct(d['esgoto'])} dos moradores")
    if "agua" in d or "esgoto" in d:
        linhas.append("(IBGE, Censo 2022)")
    return "\n".join(linhas) if len(linhas) > 1 else ""
