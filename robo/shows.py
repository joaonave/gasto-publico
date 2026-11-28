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
                        r"ART[IÍ]ST|FONOGR[AÁ]FIC[AO]S?|[0-9.\-/]+)\b", re.IGNORECASE)
_CONECTORES = {"OS", "AS", "O", "A", "E", "DE", "DO", "DA", "DOS", "DAS", "&"}


def _sem_acento(t):
    import unicodedata
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().upper()


# palavra que encerra o nome do artista ("show do cantor TIERRY NO EVENTO..." → "TIERRY")
_PARA = {"NO", "NA", "NOS", "NAS", "PARA", "EM", "DIA", "DIAS", "PREVISTO", "PREVISTA", "DURANTE", "AO", "AOS", "A",
         "COM", "REALIZADO", "REALIZADA", "REALIZAR", "EVENTO", "FESTA", "FESTEJOS", "FESTIVIDADES", "ANIVERSARIO",
         "CARNAVAL", "REVEILLON", "NATAL", "PROGRAMACAO", "EMANCIPACAO", "MUNICIPIO", "CIDADE", "VALOR", "REFERENTE",
         "CONFORME", "SEGUNDO", "QUE", "SENDO", "REPRESENTADO", "REPRESENTADA", "POR", "ATRAVES", "VIA", "COMO",
         "SHOW", "SHOWS", "APRESENTACAO", "OBJETO", "LOCAL", "PRACA", "PARQUE", "ESTADIO", "AVENIDA", "RUA",
         "RENOME", "NACIONAL", "REGIONAL", "INTERNACIONAL", "-", "–"}
_CONECT_FIM = {"E", "&", "DE", "DA", "DO", "DOS", "DAS", "A", "O"}
# fornecedor cujo "nome próprio" é palavra comum de evento: não serve como nome de artista
_FORNECEDOR_COMUM = re.compile(r"^(S[AÃ]O JO[AÃ]O|CIDADE|CARNAVAL|NATAL|FESTA|FESTAS|BRASIL|NORDESTE|REGIONAL|"
                               r"MUNICIPAL|NACIONAL|CULTURA|CULTURAL|ARTE|ARTES|SOM|LUZ|PALCO|MIX|TOP|MAIS|REAL|NOVA|"
                               r"NOVO|GRUPO|BANDA|SHOW|VIP|PREMIUM|PRIME)$", re.IGNORECASE)

# prefixo em qualquer caixa; o nome tem que começar com maiúscula
_NOMEADO = re.compile(
    r"(?i:\b(?:d[oa]s?|pel[oa]s?|com\s+[oa]s?|com)\s+(?:artistas?|cantor(?:a|es|as)?|bandas?|grupos?(?: musical)?|"
    r"duplas?(?: sertanejas?)?|mc|dj)\s+(?:de\s+renome\s+(?:nacional|regional|internacional)\s*[-–:,]?\s*)?)"
    r"((?:DJ |MC |Dj |Mc )?[A-ZÀ-Ý0-9][\wÀ-ÿ'&]*(?:\s+(?:[A-ZÀ-Ý0-9&][\wÀ-ÿ'&]*|e|&|de|da|do|dos|das))*)")
# antes das aspas tem que vir cantor/banda/artista/show ("evento “Carnaval 2027”" não é artista)
_ASPAS_ARTISTA = re.compile(r"(?i:(?:artistas?|cantor(?:a|es|as)?|bandas?|grupos?|duplas?(?: sertanejas?)?|mc|dj|"
                            r"show(?: musical)?(?: d[oa]s?)?|apresenta[çc][ãa]o(?: musical| art[íi]stica)?(?: d[oa]s?)?)"
                            r"\s*[:\-]?\s*)[“\"«]([^”\"»]{3,60})[”\"»]")
# vários artistas num contrato só: não dá para pôr um nome na manchete
_VARIOS = re.compile(r"(?i:\b(?:d[oa]s|pel[oa]s)\s+(?:artistas|bandas|cantor(?:es|as)|duplas|atra[çc][õo]es)\b)|"
                     r"(?i:\b(?:cantor(?:a)?|banda|artista|dupla)\b[^.;]{3,60}\be\s+(?:d[oa]|[oa])\s+(?:cantor(?:a)?|banda|artista|dupla)\b)")


def _limpar_nome(nome):
    # "DUPLA DE RENOME NACIONAL - DIEGO & ARNALDO" → "DIEGO & ARNALDO"
    nome = re.sub(r"(?i)^(?:de\s+)?renome\s+(?:nacional|regional|internacional)\s*[-–:,]?\s*", "", nome)
    while nome.split() and _sem_acento(nome.split()[0]) in _CONECT_FIM:
        nome = nome.split(None, 1)[1] if len(nome.split()) > 1 else ""
    nome = re.sub(r"(?i)\s+(?:e|&)\s+(?:sua\s+)?banda\b.*$", "", nome)  # "GUSTTAVO LIMA E BANDA" → "GUSTTAVO LIMA"
    toks = nome.replace(",", " , ").split()
    out = []
    for t in toks:
        if t == "," or _sem_acento(t) in _PARA:
            break
        out.append(t)
    while out and _sem_acento(out[-1]) in _CONECT_FIM:
        out.pop()
    return " ".join(out).strip(" -–'\"")


def artista(objeto, fornecedor=""):
    """Nome do artista. Ordem: entre aspas logo depois de cantor/banda/artista/show; nomeado após
    "do artista/da banda/do cantor"; nome próprio do fornecedor que aparece inteiro no objeto.
    Vários artistas no mesmo contrato: "" (manchete sem nome)."""
    obj = objeto or ""
    if _VARIOS.search(obj):
        return ""
    m = _ASPAS_ARTISTA.search(obj)
    if m:
        nome = _limpar_nome(m.group(1).strip())
        if len(nome) >= 3:
            return nome
    m = _NOMEADO.search(obj)
    if m:
        nome = _limpar_nome(m.group(1).strip())
        if len(nome) >= 3 and not re.match(r"(?i)(?:para|com|em|no|na|local|regional|nacional)\b", nome):
            return nome
    palavras = _GENERICOS.sub(" ", fornecedor or "").split()
    while palavras and palavras[0].upper() in _CONECTORES:
        palavras.pop(0)
    while palavras and palavras[-1].upper() in _CONECTORES:
        palavras.pop()
    nucleo = " ".join(palavras)
    if len(nucleo) >= 4 and not _FORNECEDOR_COMUM.match(nucleo) and \
            re.search(r"\b" + re.escape(_sem_acento(nucleo)) + r"\b", _sem_acento(obj)):
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
        "compra": c.get("numeroControlePncpCompra") or "",
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
