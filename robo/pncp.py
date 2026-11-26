"""Coleta de contratos no PNCP, com pausa entre chamadas e nova tentativa em erro 429."""
import time
import requests

from . import config


def _get(params):
    for tentativa in range(config.PNCP_TENTATIVAS):
        r = requests.get(config.PNCP_BASE, params=params, timeout=60,
                         headers={"Accept": "application/json"})
        if r.status_code == 429:
            print(f"  PNCP 429, aguardando {config.PNCP_ESPERA_429_SEG}s")
            time.sleep(config.PNCP_ESPERA_429_SEG)
            continue
        if r.status_code == 204 or not r.content:
            return None, r.status_code
        return r, r.status_code
    raise RuntimeError("PNCP: limite de tentativas após 429")


def contratos_do_dia(data_aaaammdd):
    """Todos os contratos publicados no PNCP na data (todas as páginas)."""
    tamanho = None
    for t in config.PNCP_TAMANHOS_PAGINA:
        r, status = _get({"dataInicial": data_aaaammdd, "dataFinal": data_aaaammdd,
                          "pagina": 1, "tamanhoPagina": t})
        if status == 400:
            print(f"  PNCP recusou tamanhoPagina={t}, reduzindo")
            continue
        tamanho = t
        break
    if tamanho is None:
        raise RuntimeError("PNCP recusou todos os tamanhos de página")
    if r is None:
        return []
    r.raise_for_status()
    corpo = r.json()
    total_paginas = corpo.get("totalPaginas", 1)
    itens = list(corpo.get("data", []))
    print(f"  PNCP {data_aaaammdd}: {corpo.get('totalRegistros', len(itens))} contratos, "
          f"{total_paginas} páginas")
    for pagina in range(2, total_paginas + 1):
        time.sleep(config.PNCP_PAUSA_SEG)
        r, status = _get({"dataInicial": data_aaaammdd, "dataFinal": data_aaaammdd,
                          "pagina": pagina, "tamanhoPagina": tamanho})
        if r is None:
            break
        r.raise_for_status()
        itens.extend(r.json().get("data", []))
    return itens


def link_contrato(c):
    cnpj = (c.get("orgaoEntidade") or {}).get("cnpj")
    ano = c.get("anoContrato")
    seq = c.get("sequencialContrato")
    if cnpj and ano and seq:
        return f"https://pncp.gov.br/app/contratos/{cnpj}/{ano}/{seq}"
    return "https://pncp.gov.br/app/contratos"
