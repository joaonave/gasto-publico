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
    p1 = (f"{cab}\n\nDesde 2014 teve {valor_manchete(rx['total']).lower().replace('r$', 'R$')} "
          f"pagos em emendas: {rx['qtd']} repasse{'s' if rx['qtd'] > 1 else ''} para "
          f"{rx['destinos']} destino{'s' if rx['destinos'] > 1 else ''}.\n\n🧵")
    linhas = [f"{i}. {t['destino'].title().replace('Municipio De ', '')} ({t['uf']}) — {valor_manchete(t['valor'])}"
              for i, t in enumerate(rx["top"], 1)]
    p2 = "PARA ONDE MAIS FOI\n\n" + "\n".join(linhas)
    p3 = "POR ANO\n\n" + "\n".join(f"{a}: {valor_manchete(v)}" for a, v in rx["por_ano"].items())
    pct = 100 * rx["fora_do_estado"] / rx["total"] if rx["total"] else 0
    p4 = (f"FORA DE {rx['uf'] or 'SEU ESTADO'}: {valor_manchete(rx['fora_do_estado'])} ({pct:.0f}%)\n\n"
          "Fonte: Portal da Transparência (CGU)\n🔗 https://portaldatransparencia.gov.br/emendas")
    posts = [p1, p2, p3, p4]
    def tam(t):
        return len(t) - len(TRANSFEREGOV) + 23 if TRANSFEREGOV in t else len(t)
    erros = [f"post {i+1} com {tam(t)} caracteres" for i, t in enumerate(posts) if tam(t) > 280]
    return {"posts": posts, "erros": erros}


def fatos_pagamento(r, cadastro):
    """Post de emenda paga no dia (fonte: download do Portal da Transparência)."""
    from .emendas import norm
    cad = cadastro.get(norm(r["autor"]))
    if not cad:  # bancada, comissão ou relator: sem um parlamentar identificável
        return None
    quem = _quem(cad)
    destino = (r["municipio"] or r.get("favorecido") or r["localidade"] or "").upper()
    uf = r["uf"]
    fora = bool(cad["uf"] and uf and uf != cad["uf"])
    vm = valor_manchete(r["pago_dia"])
    if destino and uf:
        manchete = f"{quem} TEM {vm} PAGOS EM EMENDA PARA {destino} ({uf})"
    else:
        manchete = f"{quem} TEM {vm} PAGOS EM EMENDA"
    if fora:
        manchete += f". ELE É DE {cad['uf']}"
    return {
        "id": "pago-" + r["codigo"] + "-" + str(round(r["pago"])),
        "tipo": "emenda_fora" if fora else "emenda",
        "valor": r["pago_dia"], "valor_manchete": vm, "manchete_padrao": manchete,
        "municipio": r["municipio"], "uf": uf,
        "linha_fato": " | ".join(x for x in [f"Emenda {r['codigo']}", r.get("favorecido", ""),
                                            f"recebido em {r.get('ano_mes', '')}: {valor_exato(r['pago'])}"] if x),
        "contexto": "Pagamento de emenda parlamentar." + (" O parlamentar foi eleito por outro estado." if fora else ""),
        "link": f"https://portaldatransparencia.gov.br/emendas/detalhe?codigoEmenda={r['codigo']}",
    }
