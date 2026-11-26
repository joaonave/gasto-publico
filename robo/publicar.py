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


MUT = """mutation {
  createPost(input: { text: %s, channelId: %s, schedulingType: automatic, mode: customScheduled, dueAt: %s }) {
    ... on PostActionSuccess { post { id dueAt } }
    ... on MutationError { message }
  }
}"""


def agendar(textos):
    """Agenda os textos no X. Retorna lista de (texto, resultado)."""
    if not os.environ.get("BUFFER_KEY"):
        return [(t, "sem BUFFER_KEY: não publicado") for t in textos]
    textos = textos[:MAX_POR_DIA]
    canal = canal_x()
    print(f"  Buffer: canal {canal['name']} ({canal['service']})")
    saida = []
    for texto, quando in zip(textos, horarios(len(textos))):
        due = quando.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        try:
            r = _gql(MUT % (json.dumps(texto), json.dumps(canal["id"]), json.dumps(due)))["createPost"]
            res = f"agendado {quando:%d/%m %H:%M}" if "post" in r else f"erro: {r.get('message')}"
        except Exception as e:  # noqa: BLE001
            res = f"erro: {e}"
        print(f"  {res}")
        saida.append((texto, res))
    return saida
