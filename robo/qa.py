"""Conferência dos posts, sem IA. Na dúvida, não publica.

1. revisar(): antes de redigir, regras sobre o contrato (teto, valor, pacote, repetição).
2. conferencia_final(): depois de redigir, o post é reconferido contra o dado de origem — é o último portão.
"""
import re
import unicodedata
from datetime import date, datetime, timedelta

from . import config, publicar
from .shows import _num, valor_manchete

_VALOR_NO_TEXTO = re.compile(r"R\$\s*([\d.]+,\d{2})")
_TETO = re.compile(r"registro de pre[çc]os|estimad|valor m[áa]ximo|at[ée] o limite|teto|credenciamento|"
                   r"eventual|sob demanda|por demanda", re.IGNORECASE)
_PACOTE = re.compile(r"estrutura|palco|som|ilumina[çc]|camarim|seguran[çc]a|banheiros|tendas", re.IGNORECASE)
_EVENTO_SHOW = re.compile(r"show|apresenta[çc]|banda|cantor|dupla|artista|atra[çc]", re.IGNORECASE)
_ACUSACAO = re.compile(r"corrup|desvi|roub|superfatur|propina|ladr|crime|fraud|il[ée]gal|esquema|mamata",
                       re.IGNORECASE)
_LINK_CONTRATO = re.compile(r"^https://pncp\.gov\.br/app/contratos/(\d{14})/(\d{4})/(\d+)$")

LIMITE_SHOW_SEM_ARTISTA = 1_500_000   # cachê muito alto sem artista: provável pacote/evento inteiro
LIMITE_SHOW = 5_000_000
CONTRATOS = ("show", "midia", "inusitada")


def _sa(t):
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().upper()


def revisar(f, manchetes_do_dia):
    """Motivos para segurar o candidato (vazia = segue)."""
    motivos = []
    obj = f.get("objeto", "") or ""
    tipo = f.get("tipo", "")
    v = f.get("valor", 0)
    if tipo in CONTRATOS:
        citados = [_num(x.replace(".", "").replace(",", ".")) for x in _VALOR_NO_TEXTO.findall(obj)]
        if citados and all(abs(c - v) > 1 for c in citados):
            motivos.append(f"objeto cita valor diferente ({', '.join(_VALOR_NO_TEXTO.findall(obj)[:2])})")
        if not f.get("uf"):
            motivos.append("sem UF do órgão")
    if tipo in ("show", "inusitada") and _TETO.search(obj):
        motivos.append("valor parece teto (registro de preço/estimado/credenciamento)")
    if tipo == "show":
        if not _EVENTO_SHOW.search(obj):
            motivos.append("objeto não descreve apresentação artística")
        if v > LIMITE_SHOW or (v > LIMITE_SHOW_SEM_ARTISTA and not f.get("artista")):
            motivos.append("valor fora do padrão para um show (provável evento inteiro)")
        if _PACOTE.search(obj) and not f.get("inclui_estrutura"):
            motivos.append("objeto inclui estrutura e a manchete não diz")
    m = f.get("manchete_padrao") or ""
    if m and m in manchetes_do_dia:
        motivos.append("manchete repetida no dia")
    return motivos


def conferencia_final(f, post):
    """Reconfere o post pronto contra o dado de origem. Qualquer item falho = não publica."""
    erros = []
    corpo = post["corpo_sem_link"]
    manchete = corpo.split("\n")[0]
    tipo = f.get("tipo")

    # forma
    if publicar._tam_x(corpo) > 280:
        erros.append("post passa de 280 caracteres")
    if "http" in corpo:
        erros.append("link no corpo do post")
    fonte = f"Fonte oficial:\n{post['link']}"
    dados = publicar._caber(post.get("dados_municipio") or "", "\n\n" + fonte)
    if publicar._tam_x((dados + "\n\n" if dados else "") + fonte) > 280:
        erros.append("1º comentário passa de 280 caracteres")
    if _ACUSACAO.search(corpo + " " + (post.get("dados_municipio") or "")):
        erros.append("palavra de acusação")

    if tipo in CONTRATOS:
        # o link é o do próprio contrato
        m = _LINK_CONTRATO.match(post["link"])
        if not m or m.group(1) not in (f.get("id") or "") or not (f.get("id") or "").endswith(f"/{m.group(2)}"):
            erros.append("link não corresponde ao contrato")
        # valor da manchete recalculado do valor do contrato
        if valor_manchete(f.get("valor", 0)) not in manchete:
            erros.append("valor da manchete não confere com o contrato")
        # contrato recente (data de assinatura)
        try:
            assinado = datetime.strptime(f.get("data_assinatura", ""), "%d/%m/%Y").date()
            if assinado < date.today() - timedelta(days=config.IDADE_MAX_DIAS) or assinado > date.today() + timedelta(days=1):
                erros.append(f"data de assinatura fora da janela ({f['data_assinatura']})")
        except ValueError:
            erros.append("sem data de assinatura")
        if re.search(r"\bPAG(A|OU|AR|AM)\b", _sa(manchete)):
            erros.append("contrato não é pagamento (PAGA na manchete)")
        # município da manchete é o do órgão
        if f.get("municipio") and redacao_eh_prefeitura(f.get("orgao")) and _sa(f["municipio"]) not in _sa(manchete):
            erros.append("município da manchete diferente do órgão")

    if tipo == "show":
        art = f.get("artista") or ""
        if not art or _sa(art) not in _sa(f.get("objeto", "") + " " + f.get("fornecedor", "")):
            erros.append("artista não aparece no contrato")
        if art and _sa(art) not in _sa(manchete):
            erros.append("artista da manchete diferente do contrato")
    if tipo == "inusitada" and not f.get("item_confirmado"):
        erros.append("item da compra não confirmado no PNCP")

    if f.get("pix") and "emenda Pix" in corpo:
        p = f["pix"]
        if not p.get("total") or p["total"] < 100_000 or not p.get("autor"):
            erros.append("dado do Pix incompleto")
        if valor_manchete(p["total"]).lower().replace("milhões", "milhões") not in corpo.lower():
            erros.append("valor do Pix no texto não confere")
    if tipo == "ranking" and not post["link"].startswith("https://portaldatransparencia.gov.br/"):
        erros.append("ranking sem link do Portal")
    return erros


def redacao_eh_prefeitura(orgao):
    from .redacao import eh_prefeitura
    return eh_prefeitura(orgao)
