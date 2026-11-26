"""Publicação no X via API do Buffer (GraphQL). Distribui os posts ao longo do dia."""
import json
import os
from datetime import datetime, timedelta, timezone

import requests

API = "https://api.buffer.com"
BRT = timezone(timedelta(hours=-3))

MAX_POR_DIA = 10       # teto de posts agendados por execução (plano grátis do Buffer)
INICIO_H, FIM_H = 8, 21
INTERVALO_MIN = 75


def _gql(query, variables=None):
    r = requests.post(API, timeout=60, json={"query": query, "variables": variables or {}},
                      headers={"Authorization": f"Bearer {os.environ['BUFFER_KEY']}",
                               "Content-Type": "application/json"})
    r.raise_for_status()
    corpo = r.json()
    if corpo.get("errors"):
        raise RuntimeError(f"Buffer: {corpo['errors']}")
    return corpo["data"]


def canal_x():
    orgs = _gql("query { account { organizations { id name } } }")["account"]["organizations"]
    for org in orgs:
        canais = _gql('query { channels(input: { organizationId: %s }) { id name service } }'
                      % json.dumps(org["id"]))["channels"]
        for c in canais:
            if c["service"].lower() in ("twitter", "x"):
                return c
    raise RuntimeError("Nenhum canal do X conectado no Buffer")


def horarios(qtd, agora=None):
    agora = agora or datetime.now(BRT)
    t = max(agora + timedelta(minutes=10), agora.replace(hour=INICIO_H, minute=0, second=0, microsecond=0))
    fim = agora.replace(hour=FIM_H, minute=0, second=0, microsecond=0)
    slots = []
    while len(slots) < qtd:
        if t > fim:  # passou das 21h: começa no dia seguinte
            t = (t + timedelta(days=1)).replace(hour=INICIO_H, minute=0)
            fim = fim + timedelta(days=1)
        slots.append(t)
        t += timedelta(minutes=INTERVALO_MIN)
    return slots


REPO_RAW = "https://raw.githubusercontent.com/joaonave/gasto-publico/main/"


def _mutacao(post, canal_id, due, com_imagem=True, com_thread=True):
    partes = [f"text: {json.dumps(post["texto_final"], ensure_ascii=False)}", f"channelId: {json.dumps(canal_id)}",
              "schedulingType: automatic", "mode: customScheduled", f"dueAt: {json.dumps(due)}"]
    if com_imagem and post.get("card"):
        partes.append("assets: [{ image: { url: %s } }]" % json.dumps(REPO_RAW + post["card"]))
    if com_thread and post.get("resposta"):
        itens = ", ".join("{ text: %s }" % json.dumps(t, ensure_ascii=False) for t in (post["texto_final"], post["resposta"]))
        partes.append("metadata: { twitter: { thread: [%s] } }" % itens)
    return ("mutation { createPost(input: { %s }) { ... on PostActionSuccess { post { id dueAt } } "
            "... on MutationError { message } } }" % ", ".join(partes))


def agendar(posts):
    """posts: lista de dicts com texto, corpo_sem_link, link, variante_link e card (caminho no repositório).
    Tenta com imagem e com link na resposta; se o Buffer recusar, simplifica até publicar."""
    if not os.environ.get("BUFFER_KEY"):
        return [(p["texto"], "sem BUFFER_KEY: não publicado") for p in posts]
    posts = posts[:MAX_POR_DIA]
    canal = canal_x()
    print(f"  Buffer: canal {canal['name']} ({canal['service']})")
    saida = []
    for post, quando in zip(posts, horarios(len(posts))):
        due = quando.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        tentativas = []
        if post.get("variante_link") == "resposta":
            p2 = dict(post, texto_final=post["corpo_sem_link"], resposta=f"Fonte oficial:\n{post['link']}")
            tentativas += [(p2, True, True), (p2, False, True)]
        p1 = dict(post, texto_final=post["texto"], resposta=None)
        tentativas += [(p1, True, False), (p1, False, False)]
        res = "erro"
        for p, img, th in tentativas:
            try:
                r = _gql(_mutacao(p, canal["id"], due, img, th))["createPost"]
            except Exception as e:  # noqa: BLE001
                r = {"message": str(e)[:200]}
            if "post" in r:
                res = (f"agendado {quando:%d/%m %H:%M} | imagem: {'sim' if img and p.get('card') else 'não'}"
                       f" | link: {'resposta' if th else 'post'}")
                break
            res = f"erro: {r.get('message')}"
            if "limit" in res.lower():
                break
        print(f"  {res}")
        saida.append((post["texto"], res))
    return saida
