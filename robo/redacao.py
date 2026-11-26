"""Redação do post (API do Grok) e checagem automática antes de publicar."""
import json
import os
import re

import requests

from . import config

ESTILO = """Você escreve posts para o perfil @GastoPublicoBR no X.
Voz: um brasileiro comum, desiludido com o uso do dinheiro público. Cansado, irônico, nunca histérico.

Formato obrigatório (responda só com JSON):
{"manchete": "...", "comentario": "..."}

Regras da manchete:
- TODA EM CAIXA ALTA, uma frase, sem emoji, até 140 caracteres.
- Diz o fato: quem pagou, quanto, por quê. Ex.: PREFEITURA DE X (UF) PAGA R$ 680 MIL EM SHOW DE FULANO
- Use o valor EXATAMENTE como vem em "valor_manchete". Não escreva nenhum outro valor em R$.
- Se o órgão for "MUNICIPIO DE X", chame de "PREFEITURA DE X".
- Nome de artista só se estiver escrito no objeto do contrato. Se não estiver, diga "SHOW".
- Se "inclui_estrutura" for true, diga "SHOW E ESTRUTURA", não "CACHÊ".

Regras do comentário (só quando "pedir_comentario" for true; senão devolva ""):
- Uma ou duas frases curtas, minúsculas normais, tom de quem já viu isso mil vezes.
- Ironia ou contraste. Ex.: "Mas a festa vai ser boa." / "Prioridades."
- PROIBIDO: acusar crime, falar em corrupção, desvio, roubo, superfaturamento; inventar fato ou número;
  palavrões; mencionar partido. Não use nenhum número no comentário.
"""


def _grok(fatos, pedir_comentario):
    chave = os.environ.get("XAI_KEY")
    if not chave:
        return None
    if fatos.get("manchete_padrao"):
        if not pedir_comentario:
            return None
        entrada = {"manchete": fatos["manchete_padrao"], "contexto": fatos.get("contexto", ""),
                   "pedir_comentario": True,
                   "instrucao": "Devolva a manchete exatamente igual e escreva só o comentário."}
    else:
        entrada = {k: fatos[k] for k in ("orgao", "municipio", "uf", "fornecedor", "objeto",
                                          "valor_manchete", "inclui_estrutura")}
        entrada["pedir_comentario"] = pedir_comentario
    r = requests.post(
        config.XAI_URL,
        headers={"Authorization": f"Bearer {chave}"},
        json={
            "model": os.environ.get("XAI_MODELO", config.XAI_MODELO),
            "messages": [
                {"role": "system", "content": ESTILO},
                {"role": "user", "content": json.dumps(entrada, ensure_ascii=False)},
            ],
            "temperature": 0.7,
            "response_format": {"type": "json_object"},
        },
        timeout=90,
    )
    r.raise_for_status()
    texto = r.json()["choices"][0]["message"]["content"]
    return json.loads(texto)


def _manchete_padrao(f):
    if f.get("manchete_padrao"):
        return f["manchete_padrao"]
    orgao = f["orgao"].upper()
    if orgao.startswith("MUNICIPIO DE "):
        orgao = "PREFEITURA DE " + orgao[len("MUNICIPIO DE "):]
    uf = f" ({f['uf']})" if f["uf"] and orgao.startswith("PREFEITURA") else ""
    tipo = "SHOW E ESTRUTURA" if f["inclui_estrutura"] else "SHOW"
    return f"{orgao}{uf} PAGA {f['valor_manchete']} EM {tipo}"


def _linha_fato(f):
    if f.get("linha_fato"):
        return f["linha_fato"]
    partes = [f"{f['fornecedor']}", f"{f['valor_exato']}"]
    if f["data_assinatura"]:
        partes.append(f"assinado em {f['data_assinatura']}")
    return " | ".join(p for p in partes if p)


LINKS_OK = ("https://pncp.gov.br/", "https://api.transferegov.gestao.gov.br/",
            "https://portaldatransparencia.gov.br/", "https://www.camara.leg.br/",
            "https://camara.leg.br/", "https://www.senado.leg.br/")

PROIBIDAS = re.compile(r"corrup|desvi|roub|superfatur|propina|ladr|crime|fraud", re.IGNORECASE)


def checar(f, manchete, comentario):
    """Retorna lista de problemas. Vazia = pode publicar."""
    erros = []
    if f["valor_manchete"] not in manchete:
        erros.append("valor da manchete diferente do dado")
    valores = re.findall(r"R\$\s?[\d.,]+", manchete)
    if any(v.replace(" ", "") not in f["valor_manchete"].replace(" ", "") for v in valores):
        erros.append("manchete tem valor que não está no dado")
    if manchete != manchete.upper():
        erros.append("manchete não está em caixa alta")
    if comentario and re.search(r"\d", comentario):
        erros.append("comentário com número")
    if PROIBIDAS.search(manchete + " " + comentario):
        erros.append("palavra proibida (acusação)")
    if not f["link"].startswith(LINKS_OK):
        erros.append("link inválido")
    return erros


def montar(f, pedir_comentario):
    """Monta o post. Se o Grok falhar ou a checagem reprovar, usa a manchete padrão sem comentário."""
    manchete, comentario, origem = _manchete_padrao(f), "", "padrão"
    try:
        g = _grok(f, pedir_comentario)
        if g:
            m = f.get("manchete_padrao") or (g.get("manchete") or "").strip()
            c = (g.get("comentario") or "").strip() if pedir_comentario else ""
            if m and not checar(f, m, c):
                manchete, comentario, origem = m, c, "grok"
            else:
                print(f"  checagem reprovou texto do Grok: {checar(f, m, c)}")
    except Exception as e:  # noqa: BLE001
        print(f"  Grok indisponível ({e}); usando manchete padrão")

    erros = checar(f, manchete, comentario)
    embaixo = comentario if comentario else _linha_fato(f)
    post = f"{manchete}\n\n{embaixo}\n\n🔗 {f['link']}"
    # X conta link como 23 caracteres
    tamanho = len(post) - len(f["link"]) + 23
    if tamanho > 280:
        erros.append(f"post com {tamanho} caracteres")
    return {"texto": post, "erros": erros, "origem": origem, "comentario": bool(comentario)}
