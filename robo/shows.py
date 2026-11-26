"""Gatilho: contratos de show/cachê acima do valor mínimo."""
import re

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
    if v < 500:
        return "R$ 0"
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


def fatos(c):
    v = _num(c.get("valorGlobal") or c.get("valorInicial"))
    municipio, uf = _local(c)
    data = (c.get("dataAssinatura") or "")[:10]
    return {
        "id": c.get("numeroControlePNCP") or link_contrato(c),
        "orgao": (c.get("orgaoEntidade") or {}).get("razaoSocial", ""),
        "municipio": municipio,
        "uf": uf,
        "fornecedor": c.get("nomeRazaoSocialFornecedor", ""),
        "objeto": (c.get("objetoContrato") or "").strip(),
        "valor": v,
        "valor_manchete": valor_manchete(v),
        "valor_exato": valor_exato(v),
        "data_assinatura": "/".join(reversed(data.split("-"))) if data else "",
        "link": link_contrato(c),
        "inclui_estrutura": bool(_ESTRUTURA.search(c.get("objetoContrato") or "")),
    }


def selecionar(contratos):
    achados = []
    for c in contratos:
        objeto = c.get("objetoContrato") or ""
        v = _num(c.get("valorGlobal") or c.get("valorInicial"))
        if v >= config.VALOR_MINIMO and _SHOW.search(objeto) and not _EXCLUIR.search(objeto):
            achados.append(fatos(c))
    achados.sort(key=lambda f: f["valor"], reverse=True)
    return achados
