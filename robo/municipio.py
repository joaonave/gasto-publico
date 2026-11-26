"""Dados oficiais do município para o 1º comentário: IDHM (PNUD via IBGE Cidades) e saneamento (IBGE, Censo 2022).

Consulta por município, só para os posts do dia, com cache em dados/municipios.json.
Tabelas verificadas em 26/11/2026: SIDRA 6909 (água), 7555 (esgoto), IBGE Cidades pesquisa 10111 (IDHM).
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
# fossa rudimentar ou buraco, vala, rio/lago/córrego/mar, sem banheiro nem sanitário
PRECARIO = "/t/7555/n6/{cod}/v/1000382/p/2022/c11558/72113,92858,72114,92861/c58/95253/c86/95251"


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
    """Soma as linhas de valor (uma por categoria pedida)."""
    r = requests.get(SIDRA + caminho.format(cod=cod), timeout=60)
    r.raise_for_status()
    vals = [_num(l["V"]) for l in r.json()[1:]]
    vals = [v for v in vals if v is not None]
    return round(sum(vals), 2) if vals else None


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
        if cod in self.cache and "precario" in self.cache[cod]:
            return self.cache[cod]
        d = {}
        for chave, fn in (("idhm", lambda: _idhm(cod)), ("agua", lambda: _sidra(AGUA, cod)),
                          ("esgoto", lambda: _sidra(ESGOTO, cod)), ("precario", lambda: _sidra(PRECARIO, cod))):
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


# cidade com infra boa: ironia em vez de número neutro
IRONIA = {
    "show": ["🇩🇰 Parece a Dinamarca: {esg} com rede de esgoto. Aí sobra pro show.",
             "Saneamento resolvido ({esg} com esgoto na rede). Agora é festa.",
             "Infra em dia: {esg} com esgoto na rede. Prioridade agora é o palco."],
    "midia": ["🇩🇰 Parece a Dinamarca: {esg} com rede de esgoto. Falta só contar pra todo mundo.",
              "Com {esg} de esgoto na rede, o problema agora é a divulgação."],
    "outro": ["🇩🇰 Parece a Dinamarca: {esg} com rede de esgoto. Pode gastar.",
              "Saneamento resolvido ({esg} com esgoto na rede). Sobrou."],
}


def comentario(f, d, populacao=None, hom=None, anos_hom=""):
    """Texto do 1º comentário (sem o link): o dado que choca primeiro. Vazio se não houver dado.
    hom = (taxa por 100 mil/ano, vezes a média do país, óbitos no período)."""
    if not f.get("municipio") or not (d or hom):
        return ""
    d = d or {}
    choque = []  # (gravidade, linha)
    if hom and hom[1] >= 1.5 and hom[2] >= 5:
        vezes = f"{hom[1]:.1f}".replace(".", ",")
        choque.append((hom[1] * 40, f"🔪 {hom[0]:.0f} homicídios por 100 mil hab. ao ano, {vezes}x a média do país"
                       f" (DataSUS, {anos_hom})"))
    if "esgoto" in d:
        sem = 100 - d["esgoto"]
        if sem >= 20:
            choque.append((sem, f"🚽 {_pct(sem)} dos moradores sem rede de esgoto"))
    if d.get("precario", 0) >= 5:
        choque.append((d["precario"], f"💩 {_pct(d['precario'])} despejam em fossa rudimentar, vala, rio ou não têm banheiro"))
    if "agua" in d:
        sem = 100 - d["agua"]
        if sem >= 10:
            choque.append((sem, f"🚱 {_pct(sem)} sem água da rede geral"))
    linhas = [f"📊 {f['municipio'].upper()} ({f.get('uf', '')})"]
    linhas += [l for _, l in sorted(choque, key=lambda x: -x[0])]
    if any("IBGE" not in l and ("🚽" in l or "💩" in l or "🚱" in l) for _, l in choque):
        linhas.append("(IBGE, Censo 2022)")
    elif not choque and d.get("esgoto", 0) >= 90 and d.get("agua", 0) >= 95:
        banco = IRONIA.get(f.get("tipo"), IRONIA["outro"])
        frase = banco[sum(map(ord, f.get("id", f["municipio"]))) % len(banco)]
        linhas += [frase.format(esg=_pct(d["esgoto"])), "(IBGE, Censo 2022)"]
    if "idhm" in d:
        linhas.append(f"IDHM {d['idhm']:.3f}".replace(".", ",") + f", {faixa_idhm(d['idhm'])} (PNUD, 2010)")
    if populacao:
        linhas.append(f"População: {populacao:,}".replace(",", ".") + " (IBGE)")
    return "\n".join(linhas) if len(linhas) > 1 else ""
