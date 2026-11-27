"""Assuntos quentes do dia: manchetes do Google Notícias (RSS público) e buscas em alta do Google Trends.

Uso: casar parlamentares citados nas manchetes com o raio-X de emendas (fonte oficial) e postar no embalo.
"""
import html
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import requests

UA = {"User-Agent": "gasto-publico-bot/1.0 (+https://github.com/joaonave/gasto-publico)"}
GNEWS = "https://news.google.com/rss/search?q={q}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
TOPO = "https://news.google.com/rss?hl=pt-BR&gl=BR&ceid=BR:pt-419"
TRENDS = "https://trends.google.com/trending/rss?geo=BR"
BUSCAS = ["emendas parlamentares", "deputado federal", "senador", "Congresso orçamento",
          "prefeitura show cachê", "Câmara dos Deputados", "Senado Federal"]


def _n(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.upper()).strip()


def _rss(url):
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    itens = []
    for it in ET.fromstring(r.content).iter("item"):
        titulo = html.unescape(it.findtext("title") or "")
        quando = it.findtext("pubDate")
        try:
            dt = parsedate_to_datetime(quando) if quando else None
        except (TypeError, ValueError):
            dt = None
        itens.append({"titulo": titulo, "link": it.findtext("link") or "", "data": dt,
                      "fonte": (it.findtext("source") or "").strip()})
    return itens


def manchetes(horas=24):
    """Manchetes recentes (sem duplicar), mais o termo das buscas em alta."""
    limite = datetime.now(timezone.utc) - timedelta(hours=horas)
    vistos, out = set(), []
    urls = [TOPO] + [GNEWS.format(q=quote(q + " when:1d")) for q in BUSCAS]
    for u in urls:
        try:
            for it in _rss(u):
                if it["data"] and it["data"] < limite:
                    continue
                k = _n(it["titulo"])[:90]
                if k not in vistos:
                    vistos.add(k)
                    out.append(it)
        except Exception as e:  # noqa: BLE001
            print(f"  notícias: {u[:60]} indisponível ({str(e)[:80]})")
    try:
        for it in _rss(TRENDS):
            out.append(dict(it, tendencia=True))
    except Exception as e:  # noqa: BLE001
        print(f"  trends indisponível ({str(e)[:80]})")
    return out


def _nome_curto(cad):
    """Nome pelo qual o parlamentar aparece em manchete (nome parlamentar do cadastro)."""
    return _n(cad.get("nome", ""))


def parlamentares_citados(itens, cadastro):
    """{chave_cadastro: [manchetes]} para parlamentares cujo nome parlamentar (2+ palavras) aparece na manchete."""
    idx = {}
    for chave, cad in cadastro.items():
        nome = _nome_curto(cad)
        if len(nome.split()) >= 2 and len(nome) >= 8:
            idx.setdefault(nome, chave)
    achados = {}
    for it in itens:
        t = " " + _n(it["titulo"]) + " "
        for nome, chave in idx.items():
            if f" {nome} " in t:
                achados.setdefault(chave, []).append(it)
    return achados


if __name__ == "__main__":
    from . import emendas
    itens = manchetes()
    print(f"{len(itens)} manchetes/tendências")
    for it in itens[:15]:
        print(" -", it.get("fonte"), "|", it["titulo"][:110])
    cad = emendas.parlamentares()
    for chave, lst in sorted(parlamentares_citados(itens, cad).items(), key=lambda kv: -len(kv[1])):
        print(f"{len(lst):3d} | {cadastro_nome if (cadastro_nome := cad[chave].get('nome')) else chave} | {lst[0]['titulo'][:100]}")
