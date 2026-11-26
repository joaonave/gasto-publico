"""Gatilho: contratos de show/cachê acima do valor mínimo."""
import re
from datetime import date, timedelta

from . import config
from .pncp import link_contrato

_SHOW = re.compile("|".join(config.PALAVRAS_SHOW), re.IGNORECASE)
_EXCLUIR = re.compile("|".join(config.PALAVRAS_EXCLUIR), re.IGNORECASE)
_ESTRUTURA = re.compile("|".join(config.PALAVRAS_ESTRUTURA), re.IGNORECASE)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def valor_manchete(v):
    """Valor arredondado para a manchete, sempre exibido do mesmo jeito."""
    if v < 10_000:
        return "R$ " + f"{round(v):,}".replace(",", ".")
    if round(v / 1000) >= 1000:
        mi = round(v / 1_000_000, 2)
        txt = f"{mi:.2f}".rstrip("0").rstrip(".").replace(".", ",")
        return f"R$ {txt} {'MILHÃO' if mi < 2 else 'MILHÕES'}"
    return f"R$ {round(v / 1000):,} MIL".replace(",", ".")


def valor_exato(v):
    s = f"{v:,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def _local(c):
    u = c.get("unidadeOrgao") or {}
    return u.get("municipioNome") or "", u.get("ufSigla") or ""


_ASPAS = re.compile(r'[“"«]([^”"»]{3,60})[”"»]')


_GENERICOS = re.compile(r"\b(LTDA|ME|EPP|EIRELI|S/?A|PRODU[CÇ][OÕ]ES|PRODU[CÇ][AÃ]O|ARTISTIC[AO]S?|ART[IÍ]STIC[AO]S?|"
                        r"MUSICA[LIS]*|EVENTOS?|SHOWS?|EDITORA|ADMINISTRADORA|PROMO[CÇ][OÕ]ES|ENTRETENIMENTO|"
                        r"EMPREENDIMENTOS|COMUNICA[CÇ][AÃ]O|SERVI[CÇ]OS|AGENCIA|AG[EÊ]NCIA|PRODUTORA|GRAVADORA|"
                        r"ART[IÍ]ST|[0-9.\-/]+)\b", re.IGNORECASE)
_CONECTORES = {"OS", "AS", "O", "A", "E", "DE", "DO", "DA", "DOS", "DAS", "&"}


def _sem_acento(t):
    import unicodedata
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().upper()


def artista(objeto, fornecedor=""):
    """Nome do artista: entre aspas no contrato; ou o nome próprio do fornecedor, se ele aparece no objeto."""
    m = _ASPAS.search(objeto or "")
    if m:
        return m.group(1).strip()
    palavras = _GENERICOS.sub(" ", fornecedor or "").split()
    while palavras and palavras[0].upper() in _CONECTORES:
        palavras.pop(0)
    while palavras and palavras[-1].upper() in _CONECTORES:
        palavras.pop()
    nucleo = " ".join(palavras)
    if len(nucleo) >= 4 and _sem_acento(nucleo) in _sem_acento(objeto):
        return nucleo.title()
    return ""


def fatos(c):
    v = _num(c.get("valorGlobal") or c.get("valorInicial"))
    municipio, uf = _local(c)
    data = (c.get("dataAssinatura") or "")[:10]
    return {
        "id": c.get("numeroControlePNCP") or link_contrato(c),
        "tipo": "show",
        "orgao": (c.get("orgaoEntidade") or {}).get("razaoSocial", ""),
        "municipio": municipio,
        "cod_ibge": (c.get("unidadeOrgao") or {}).get("codigoIbge", ""),
        "uf": uf,
        "fornecedor": c.get("nomeRazaoSocialFornecedor", ""),
        "objeto": (c.get("objetoContrato") or "").strip(),
        "valor": v,
        "valor_manchete": valor_manchete(v),
        "valor_exato": valor_exato(v),
        "data_assinatura": "/".join(reversed(data.split("-"))) if data else "",
        "link": link_contrato(c),
        "inclui_estrutura": bool(_ESTRUTURA.search(c.get("objetoContrato") or "")),
        "artista": artista(c.get("objetoContrato"), c.get("nomeRazaoSocialFornecedor")),
    }


def _recente(c):
    d = (c.get("dataAssinatura") or "")[:10]
    if not d:
        return True
    return d >= (date.today() - timedelta(days=config.IDADE_MAX_DIAS)).isoformat()


def selecionar(contratos):
    achados = []
    for c in contratos:
        if not _recente(c):
            continue
        objeto = c.get("objetoContrato") or ""
        v = _num(c.get("valorGlobal") or c.get("valorInicial"))
        if v >= config.VALOR_MINIMO and _SHOW.search(objeto) and not _EXCLUIR.search(objeto):
            achados.append(fatos(c))
    achados.sort(key=lambda f: f["valor"], reverse=True)
    return agrupar(achados)


def agrupar(fatos_lista):
    """Mesmo órgão + mesmo objeto = mesma licitação com vários fornecedores: vira um fato só."""
    grupos = {}
    for f in fatos_lista:
        chave = (f["orgao"], f["objeto"][:150].upper())
        if chave in grupos:
            g = grupos[chave]
            g["qtd_contratos"] += 1
            g["ids_extras"].append(f["id"])
        else:
            grupos[chave] = dict(f, qtd_contratos=1, ids_extras=[])
    return list(grupos.values())
