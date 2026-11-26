"""Fila do X no Buffer: lista os posts agendados e remove os que não seguem o formato atual.

Formato atual = texto com as hashtags fixas (#GastoPublico). Post agendado sem elas veio de versão antiga do robô.
"""
import json
import sys

from . import publicar

MARCA = "#GastoPublico"


def listar():
    canal = publicar.canal_x()
    orgs = publicar._gql("query { account { organizations { id } } }")["account"]["organizations"]
    posts = []
    for org in orgs:
        q = ('query { posts(first: 100, input: { organizationId: %s, filter: { channelIds: [%s] } }) '
             '{ edges { node { id status dueAt createdAt text } } } }'
             % (json.dumps(org["id"]), json.dumps(canal["id"])))
        try:
            d = publicar._gql(q)
        except RuntimeError as e:
            print(f"  fila: {str(e)[:300]}")
            continue
        posts += [e["node"] for e in d["posts"]["edges"]]
    return posts


def metricas():
    """Posts enviados com as métricas que o Buffer coleta do X."""
    canal = publicar.canal_x()
    orgs = publicar._gql("query { account { organizations { id } } }")["account"]["organizations"]
    out = []
    for org in orgs:
        q = ('query { posts(first: 100, input: { organizationId: %s, filter: { channelIds: [%s] } }) '
             '{ edges { node { id status sentAt text externalLink metricsUpdatedAt metrics { name value unit } } } } }'
             % (json.dumps(org["id"]), json.dumps(canal["id"])))
        out += [e["node"] for e in publicar._gql(q)["posts"]["edges"] if e["node"]["status"] == "sent"]
    return out


def pendente(p):
    return str(p.get("status", "")).lower() in ("scheduled", "draft", "needs_approval", "queued", "pending")


def antigo(p):
    return pendente(p) and MARCA not in (p.get("text") or "")


def limpar(apagar=True):
    removidos = []
    for p in listar():
        if antigo(p):
            if apagar:
                r = publicar._gql('mutation { deletePost(input: { id: %s }) { __typename } }' % json.dumps(p["id"]))
                print(f"  removido da fila (formato antigo): {p['dueAt']} | {(p['text'] or '')[:70]!r} | {r}")
            removidos.append(p)
    return removidos


def apagar_com(trecho):
    if len(trecho.strip()) < 10:  # trecho curto apagaria a fila inteira
        print("  trecho curto demais; nada removido")
        return
    for p in listar():
        if pendente(p) and trecho.lower() in (p.get("text") or "").lower():
            r = publicar._gql('mutation { deletePost(input: { id: %s }) { __typename } }' % json.dumps(p["id"]))
            print(f"  removido: {p['dueAt']} | {(p['text'] or '')[:80]!r} | {r}")


if __name__ == "__main__":
    if "--apagar" in sys.argv:
        apagar_com(sys.argv[sys.argv.index("--apagar") + 1])
    elif "--metricas" in sys.argv:
        print(json.dumps(metricas(), ensure_ascii=False))
    elif "--listar" in sys.argv:
        for p in listar():
            print(p["status"], p["dueAt"], p["createdAt"], "ANTIGO" if antigo(p) else "", repr((p["text"] or "")[:90]))
    else:
        print(f"  fila: {len(limpar())} posts antigos removidos")
