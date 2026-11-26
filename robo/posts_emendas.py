"""Monta fatos e posts de emendas Pix."""
from .emendas import TRANSFEREGOV
from .shows import valor_exato, valor_manchete


def _quem(cad):
    if not cad:
        return None
    sigla = f"{cad['partido']}-{cad['uf']}".strip("-")
    return f"{cad['cargo']} {cad['nome']} ({sigla})".upper().replace("DEP. ", "DEP. ").strip()


def fatos_emenda(plano, cadastro):
    cad = cadastro.get(plano["parlamentar"])
    quem = _quem(cad) or plano["parlamentar"]
    destino = plano["beneficiario"].upper().replace("MUNICIPIO DE ", "")
    uf = plano["uf_destino"]
    fora = bool(cad and cad["uf"] and uf and uf != cad["uf"])
    vm = valor_manchete(plano["valor"])
    manchete = f"{quem} MANDA {vm} EM EMENDA PIX PARA {destino} ({uf})"
    if fora:
        manchete += f". ELE É DE {cad['uf']}"
    return {
        "id": "pix-" + plano["id"],
        "tipo": "emenda_fora" if fora else "emenda",
        "valor": plano["valor"],
        "valor_manchete": vm,
        "manchete_padrao": manchete,
        "linha_fato": f"Emenda {plano['emenda']} | {valor_exato(plano['valor'])} | situação: {plano['situacao']}",
        "contexto": "Emenda Pix: dinheiro cai direto na conta do município ou estado." +
                    (" O parlamentar foi eleito por outro estado." if fora else ""),
        "link": f"{TRANSFEREGOV}?id_plano_acao=eq.{plano['id']}",
    }


def thread_raio_x(rx):
    sigla = f"{rx['partido']}-{rx['uf']}".strip("-")
    cab = f"RAIO-X: {rx['cargo']} {rx['nome']} ({sigla})".upper()
    p1 = (f"{cab}\n\nDesde 2020 mandou {valor_manchete(rx['total']).lower().replace('r$', 'R$')} "
          f"em emendas Pix: {rx['qtd']} repasse{'s' if rx['qtd'] > 1 else ''} para "
          f"{rx['destinos']} destino{'s' if rx['destinos'] > 1 else ''}.\n\n🧵")
    linhas = [f"{i}. {t['destino'].title().replace('Municipio De ', '')} ({t['uf']}) — {valor_manchete(t['valor'])}"
              for i, t in enumerate(rx["top"], 1)]
    p2 = "PARA ONDE MAIS FOI\n\n" + "\n".join(linhas)
    p3 = "POR ANO\n\n" + "\n".join(f"{a}: {valor_manchete(v)}" for a, v in rx["por_ano"].items())
    pct = 100 * rx["fora_do_estado"] / rx["total"] if rx["total"] else 0
    p4 = (f"FORA DE {rx['uf'] or 'SEU ESTADO'}: {valor_manchete(rx['fora_do_estado'])} ({pct:.0f}%)\n\n"
          f"Fonte: Transferegov (emendas Pix)\n🔗 {TRANSFEREGOV}")
    posts = [p1, p2, p3, p4]
    def tam(t):
        return len(t) - len(TRANSFEREGOV) + 23 if TRANSFEREGOV in t else len(t)
    erros = [f"post {i+1} com {tam(t)} caracteres" for i, t in enumerate(posts) if tam(t) > 280]
    return {"posts": posts, "erros": erros}
