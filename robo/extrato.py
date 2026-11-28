"""Extrato de emendas de um parlamentar, com recorte de uma região (região geográfica imediata do IBGE).

Uso: python -m robo.extrato "REGINALDO LOPES" "São João del-Rei"
Fonte: arquivo oficial de emendas por favorecido do Portal da Transparência (valor recebido pelo favorecido).
"""
import sys
import unicodedata
from collections import defaultdict

import requests

from . import emendas_portal

IBGE = "https://servicodados.ibge.gov.br/api/v1/localidades"


def _n(t):
    return " ".join(unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().upper().replace("-", " ").split())


def regiao(cidade, uf="MG"):
    """Municípios da região geográfica imediata (IBGE) da cidade."""
    muns = requests.get(f"{IBGE}/estados/{uf}/municipios", timeout=60).json()
    m = next(x for x in muns if _n(x["nome"]) == _n(cidade))
    ri = m["regiao-imediata"]
    lista = requests.get(f"{IBGE}/regioes-imediatas/{ri['id']}/municipios", timeout=60).json()
    return ri["nome"], {_n(x["nome"]) for x in lista}


def mi(v):
    return f"R$ {v / 1e6:,.2f} mi".replace(",", "X").replace(".", ",").replace("X", ".")


def extrato(autor, cidade, uf="MG"):
    nome_reg, reg = regiao(cidade, uf)
    linhas = [r for r in emendas_portal.baixar() if autor in _n(r["autor"])]
    out = [f"# Extrato de emendas – {autor}", f"Fonte: Portal da Transparência (emendas por favorecido, valor recebido). "
           f"Região: imediata de {nome_reg} ({len(reg)} municípios, IBGE).", ""]
    if not linhas:
        return "\n".join(out + ["Nenhuma emenda encontrada para esse autor."])
    tot = sum(r["pago"] or 0 for r in linhas)
    na_reg = [r for r in linhas if r["uf"] == uf and _n(r["municipio"]) in reg]
    tot_reg = sum(r["pago"] or 0 for r in na_reg)
    anos = sorted({str(r["ano_mes"])[:4] for r in linhas})
    out += [f"**Total recebido pelos favorecidos ({anos[0]}–{anos[-1]}): {mi(tot)}**",
            f"**Região de {nome_reg}: {mi(tot_reg)} ({100 * tot_reg / tot:.1f}% do total)**", ""]

    def tabela(titulo, chave, rows, n=15):
        g = defaultdict(float)
        for r in rows:
            g[chave(r)] += r["pago"] or 0
        out.append(f"## {titulo}")
        for k, v in sorted(g.items(), key=lambda kv: -kv[1])[:n]:
            out.append(f"- {k}: {mi(v)} ({100 * v / max(sum(g.values()), 1):.1f}%)")
        out.append("")

    tabela("Por ano (total)", lambda r: str(r["ano_mes"])[:4], linhas, 20)
    tabela("Por ano (região)", lambda r: str(r["ano_mes"])[:4], na_reg, 20)
    tabela("Por UF de destino", lambda r: r["uf"] or "?", linhas, 10)
    tabela("Maiores cidades de destino (total)", lambda r: f"{r['municipio'] or '?'} ({r['uf']})", linhas, 20)
    tabela("Cidades da região", lambda r: r["municipio"], na_reg, 30)
    tabela("Tipo de emenda (total)", lambda r: r["tipo"], linhas, 6)
    tabela("Tipo de emenda (região)", lambda r: r["tipo"], na_reg, 6)
    tabela("Favorecidos na região", lambda r: f"{r['favorecido']} [{r['natureza']}] – {r['municipio']}", na_reg, 25)
    tabela("Maiores favorecidos (total)", lambda r: f"{r['favorecido']} [{r['natureza']}] – {r['municipio']} ({r['uf']})",
           linhas, 20)
    tabela("Natureza do favorecido (total)", lambda r: r["natureza"] or "?", linhas, 8)
    return "\n".join(out)


if __name__ == "__main__":
    print(extrato(_n(sys.argv[1]), sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "MG"))
