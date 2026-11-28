"""Checagem do contrato pelos ITENS da compra no PNCP antes de postar.

O título do contrato engana ("Roteiro do Vinho" era passeio de idosos; "blindado" estava na especificação de um
compressor odontológico). Os itens dizem o que foi comprado, em que quantidade e a que preço.
Regra: só publica se algum item confirma a manchete. O item confirmado vai para o 1º comentário.
"""
import re

import requests

API = "https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/itens"
_CTRL = re.compile(r"^(\d{14})-\d-(\d+)/(\d{4})$")

SHOW = re.compile(r"\bshows?\b|apresenta[çc][ãa]o (art[íi]stica|musical)|art[íi]stic|cach[êe]|\bbanda\b|cantor|"
                  r"dupla|m[úu]sic", re.IGNORECASE)
MIDIA = re.compile(r"publicidade|propaganda|ag[êe]ncia|comunica[çc][ãa]o|divulga[çc][ãa]o|m[íi]dia|veicula[çc][ãa]o",
                   re.IGNORECASE)


_UN_SERVICO = re.compile(r"pessoa|servi[çc]o|di[áa]ria|evento|pacote|hora|m[êe]s", re.IGNORECASE)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def buscar(controle):
    """Itens da compra a partir de numeroControlePncpCompra ('CNPJ-1-SEQ/ANO'). None se não der para consultar."""
    m = _CTRL.match((controle or "").strip())
    if not m:
        return None
    cnpj, seq, ano = m.group(1), int(m.group(2)), m.group(3)
    try:
        r = requests.get(API.format(cnpj=cnpj, ano=ano, seq=seq), params={"pagina": 1, "tamanhoPagina": 100},
                         timeout=40, headers={"Accept": "application/json"})
        if r.status_code in (400, 422):  # parâmetros de página não aceitos: tenta sem
            r = requests.get(API.format(cnpj=cnpj, ano=ano, seq=seq), timeout=40)
        if r.status_code == 204 or not r.content:
            return []
        r.raise_for_status()
        d = r.json()
        return d if isinstance(d, list) else d.get("data", [])
    except Exception as e:  # noqa: BLE001
        print(f"  itens {controle}: indisponível ({str(e)[:80]})")
        return None


def _resumo(it):
    desc = re.sub(r"\s+", " ", it.get("descricao") or "").strip()
    return {"descricao": desc, "quantidade": _num(it.get("quantidade")),
            "unidade": (it.get("unidadeMedida") or "").strip(),
            "unitario": _num(it.get("valorUnitarioEstimado")), "total": _num(it.get("valorTotal"))}


def verificar(f, itens=None):
    """(ok, motivo, item_confirmado). Compra inusitada exige item; show/mídia exigem que nenhum item contradiga."""
    tipo = f.get("tipo")
    if tipo not in ("show", "midia", "inusitada"):
        return True, "", None
    itens = buscar(f.get("compra")) if itens is None else itens
    if itens is None or not itens:
        if tipo == "inusitada":
            return False, "itens da compra indisponíveis: não dá para confirmar o item", None
        return True, "", None
    res = [_resumo(i) for i in itens]
    if tipo == "inusitada":
        from .outros_pncp import INUSITADA_EXCLUIR
        rx = re.compile(f.get("item_rx") or "$^", re.IGNORECASE)
        # o item tem que SER a coisa: "Roteiro do Vinho" (unidade: pessoa) não é vinho
        ok = [i for i in res if rx.search(i["descricao"]) and not INUSITADA_EXCLUIR.search(i["descricao"])
              and not _UN_SERVICO.search(i["unidade"])]
        if not ok:
            return False, f"nenhum item da compra é {f.get('item', '').lower()} (itens: {res[0]['descricao'][:60]})", None
        return True, "", max(ok, key=lambda i: i["total"] or i["quantidade"] * i["unitario"])
    if tipo == "show":
        art = (f.get("artista") or "").lower()
        ok = [i for i in res if SHOW.search(i["descricao"]) or (art and art in i["descricao"].lower())]
        if not ok:
            return False, f"nenhum item da compra é show (itens: {res[0]['descricao'][:60]})", None
        return True, "", max(ok, key=lambda i: i["total"])
    ok = [i for i in res if MIDIA.search(i["descricao"])]
    if not ok:
        return False, f"nenhum item da compra é publicidade (itens: {res[0]['descricao'][:60]})", None
    return True, "", max(ok, key=lambda i: i["total"])


def _brl(v):
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


_UNIDADES = {"ser": "serviço", "serv": "serviço", "sv": "serviço", "uni": "unidade", "un": "unidade",
             "und": "unidade", "unid": "unidade", "cx": "caixa", "gf": "garrafa", "grf": "garrafa", "kg": "kg"}


def _corta(t, n=70):
    t = t.strip()
    if len(t) <= n:
        return t.rstrip(" ,.;-")
    return t[:n].rsplit(" ", 1)[0].rstrip(" ,.;-:") + "…"


def linha(item):
    """Linha do 1º comentário com o item confirmado (preço é o estimado na compra)."""
    if not item:
        return ""
    q = item["quantidade"]
    desc = _corta(item["descricao"])
    if not item["unitario"] or not q:
        return f"🧾 Item: {desc}"
    if q == 1:
        return f"🧾 Item: {desc} (estimado: {_brl(item['unitario'])})"
    qtd = f"{q:,.0f}".replace(",", ".") if q == int(q) else f"{q:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    un = re.sub(r"\s*\(.*\)", "", (item["unidade"] or "un")).strip().lower()
    un = _UNIDADES.get(un, un)
    if q > 1 and un.isalpha() and len(un) > 3 and not un.endswith("s"):
        un += "s"
    return f"🧾 Item: {desc}. {qtd} {un} a {_brl(item['unitario'])} cada (estimado)"
