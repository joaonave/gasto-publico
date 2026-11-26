"""QA automático sem IA: regras que seguram o post quando há dúvida. Na dúvida, não publica."""
import json
import os
import re

import requests

from .shows import _num

# Modo autônomo (ninguém revisando): só publica o que tem evidência forte.
MODO_ESTRITO = False  # volume: só os erros grosseiros seguram o post

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

    # modo estrito: precisão acima de volume
    if MODO_ESTRITO:
        if tipo == "show" and not f.get("artista"):
            motivos.append("estrito: show sem artista identificado no contrato")
        if tipo == "inusitada":
            motivos.append("estrito: compras inusitadas desligadas até termos histórico de acerto")
        if tipo == "midia" and not re.search(r"publicidade|propaganda", obj, re.IGNORECASE):
            motivos.append("estrito: objeto não diz publicidade/propaganda")

    # 4. manchete repetida no mesmo dia
    m = f.get("manchete_padrao") or ""
    if m and m in manchetes_do_dia:
        motivos.append("manchete repetida hoje")

    # 5. sem link oficial ou sem município/estado quando é contrato
    if tipo.startswith(("show", "midia", "inusitada")) and not f.get("uf"):
        motivos.append("sem UF do órgão")
    return motivos


PERGUNTA = """Você confere um post antes de publicar. Responda só JSON: {"ok": true/false, "motivo": "..."}.
ok=false se QUALQUER item falhar ou houver dúvida:
1. O objeto do contrato confirma o tipo de gasto da manchete (show, publicidade, emenda, cota)?
2. O valor da manchete é o valor do contrato/pagamento (não um teto apresentado como pago, nem soma de vários itens)?
3. A manchete não afirma nada que os dados não dizem (nome, local, tipo de gasto)?
4. O comentário não acusa ninguém de crime?"""


def revisar_ia(f, texto):
    """Segunda leitura por IA. Só roda se houver XAI_KEY; sem chave, não bloqueia."""
    chave = os.environ.get("XAI_KEY")
    if not chave:
        return []
    dados = {k: f.get(k) for k in ("tipo", "orgao", "fornecedor", "objeto", "valor", "data_assinatura", "artista")}
    try:
        r = requests.post("https://api.x.ai/v1/chat/completions", timeout=60,
                          headers={"Authorization": f"Bearer {chave}"},
                          json={"model": os.environ.get("XAI_MODELO", "grok-4.3"), "temperature": 0,
                                "response_format": {"type": "json_object"},
                                "messages": [{"role": "system", "content": PERGUNTA},
                                             {"role": "user", "content": json.dumps(
                                                 {"post": texto, "dados": dados}, ensure_ascii=False, default=str)}]})
        r.raise_for_status()
        res = json.loads(r.json()["choices"][0]["message"]["content"])
        return [] if res.get("ok") is True else [f"IA: {res.get('motivo', 'dúvida')}"]
    except Exception as e:  # noqa: BLE001
        return [f"IA indisponível ({e}); segurado por segurança"]
