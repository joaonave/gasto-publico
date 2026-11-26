"""QA automático sem IA: regras que seguram o post quando há dúvida. Na dúvida, não publica."""
import re

from .shows import _num

_VALOR_NO_TEXTO = re.compile(r"R\$\s*([\d.]+,\d{2})")
_TETO = re.compile(r"registro de pre[çc]os|estimad|valor m[áa]ximo|at[ée] o limite|teto|credenciamento|"
                   r"eventual|sob demanda|por demanda", re.IGNORECASE)
_PACOTE = re.compile(r"estrutura|palco|som|ilumina[çc]|camarim|seguran[çc]a|banheiros|tendas", re.IGNORECASE)
_EVENTO_SHOW = re.compile(r"show|apresenta[çc]|banda|cantor|dupla|artista|atra[çc]", re.IGNORECASE)

LIMITE_SHOW_SEM_ARTISTA = 1_500_000   # cachê muito alto sem artista identificado: provável pacote/evento inteiro
LIMITE_SHOW = 5_000_000


def revisar(f, manchetes_do_dia):
    """Retorna lista de motivos para segurar o post (vazia = liberado)."""
    motivos = []
    obj = f.get("objeto", "") or ""
    tipo = f.get("tipo", "")
    v = f.get("valor", 0)

    # 1. valor escrito no próprio objeto diferente do valor do contrato
    citados = [_num(x.replace(".", "").replace(",", ".")) for x in _VALOR_NO_TEXTO.findall(obj)]
    if citados and all(abs(c - v) > 1 for c in citados) and tipo.startswith(("show", "midia", "inusitada")):
        motivos.append(f"objeto cita valor diferente ({', '.join(_VALOR_NO_TEXTO.findall(obj)[:2])})")

    # 2. teto / registro de preço / credenciamento tratado como pagamento
    if tipo.startswith(("show", "inusitada")) and _TETO.search(obj):
        motivos.append("valor parece teto (registro de preço/estimado/credenciamento)")

    # 3. show: precisa ter cara de show; valores fora do padrão vão para revisão
    if tipo == "show":
        if not _EVENTO_SHOW.search(obj):
            motivos.append("objeto não descreve apresentação artística")
        if v > LIMITE_SHOW or (v > LIMITE_SHOW_SEM_ARTISTA and not f.get("artista")):
            motivos.append("valor fora do padrão para um show (provável evento inteiro)")
        if _PACOTE.search(obj) and not f.get("inclui_estrutura"):
            motivos.append("objeto inclui estrutura e a manchete não diz")

    # 4. manchete repetida no mesmo dia
    m = f.get("manchete_padrao") or ""
    if m and m in manchetes_do_dia:
        motivos.append("manchete repetida hoje")

    # 5. sem link oficial ou sem município/estado quando é contrato
    if tipo.startswith(("show", "midia", "inusitada")) and not f.get("uf"):
        motivos.append("sem UF do órgão")
    return motivos
