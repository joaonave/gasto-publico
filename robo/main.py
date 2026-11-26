"""Execução diária: coleta → candidatos → sistema de pontos → redação → checagem → Buffer."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import card, cota, qa, emendas, emendas_portal, outros_pncp, pncp, pontos, posts_emendas, publicar, redacao, shows

RAIZ = Path(__file__).resolve().parent.parent
ESTADO = RAIZ / "dados" / "estado.json"
SAIDA = RAIZ / "saida"
BRT = timezone(timedelta(hours=-3))


def _carregar_estado():
    if ESTADO.exists():
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    return {"vistos": [], "contador_posts": 0}


def _salvar_estado(e):
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    e["vistos"] = e["vistos"][-20000:]
    ESTADO.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")


def _normalizar_data(txt):
    """Aceita 20261102, 2026-11-02, 2026/11/02 ou 02/11/2026."""
    d = "".join(ch for ch in (txt or "") if ch.isdigit())
    if len(d) != 8:
        return None
    return d if int(d[:4]) > 1900 else d[4:] + d[2:4] + d[:2]


def _candidatos_pncp(data, estado, log):
    contratos = pncp.contratos_do_dia(data)
    c = [f for f in shows.selecionar(contratos) + outros_pncp.selecionar(contratos) if f["id"] not in estado["vistos"]]
    log.append(f"PNCP {data}: {len(contratos)} contratos | candidatos (shows, publicidade, inusitadas): {len(c)}")
    return c


def _candidatos_emendas(estado, log):
    cadastro = emendas.parlamentares()
    todas = emendas_portal.baixar()
    ano = datetime.now(BRT).year
    pagos, primeira = emendas_portal.pagamentos_do_dia(todas, RAIZ / "dados" / "emendas_recebido.json", ano)
    c = []
    if primeira:
        log.append("Emendas: primeira execução, base criada. Pagamentos do dia a partir da próxima.")
    else:
        c = [f for f in (posts_emendas.fatos_pagamento(r, cadastro) for r in pagos) if f]
        log.append(f"Emendas: {len(pagos)} pagamentos acima do corte | {len(c)} com deputado/senador identificado")
    # Raio-X do dia (rodízio sorteado entre deputados e senadores)
    if estado.get("raiox_dia") != datetime.now(BRT).strftime("%Y-%m-%d"):
        planos = emendas_portal.para_planos(todas)
        for _ in range(50):
            rx = emendas.raio_x(emendas.proximo_raio_x(estado, cadastro), planos, cadastro)
            if rx:
                c.append(posts_emendas.post_raio_x(rx))
                break
    return c


def _candidatos_cota(estado, log):
    ano = datetime.now(BRT).year
    notas = cota.baixar(ano)
    vistos = set(estado.get("cota_ids", []))
    c = []
    if not vistos:
        log.append("Cota: primeira execução, base criada.")
    else:
        c, _ = cota.gatilhos(notas, vistos)
        log.append(f"Cota parlamentar: {len(c)} gatilhos")
    estado["cota_ids"] = ["cota-" + str(n["id"]) for n in cota.recentes(notas)]
    return c


def executar(data=None):
    data = (_normalizar_data(data or os.environ.get("DATA"))
            or (datetime.now(BRT) - timedelta(days=1)).strftime("%Y%m%d"))
    ligar = os.environ.get("PUBLICAR", "false").lower() == "true"
    hoje = datetime.now(BRT).strftime("%Y-%m-%d")
    print(f"Data: {data} | publicar: {ligar}")
    estado = _carregar_estado()
    log = [f"# Robô – dados de {data[6:]}/{data[4:6]}/{data[:4]} – execução {datetime.now(BRT):%d/%m %H:%M}", ""]

    candidatos = []
    for nome, fn in [("PNCP", lambda: _candidatos_pncp(data, estado, log)),
                     ("Emendas", lambda: _candidatos_emendas(estado, log)),
                     ("Cota", lambda: _candidatos_cota(estado, log))]:
        try:
            candidatos += fn()
        except Exception as e:  # noqa: BLE001
            log.append(f"Erro em {nome}: {e}")
            print(f"Erro {nome}: {e}")

    pop = pontos.Populacao(RAIZ / "dados" / "populacao.json")
    escolhidos = pontos.escolher(candidatos, estado, hoje, pop)
    log += ["", f"Candidatos: {len(candidatos)} | escolhidos pelo sistema de pontos: {len(escolhidos)} "
                f"(já publicados hoje: {estado.get('pub_qtd', 0)})", ""]

    aprovados, segurados, manchetes = [], [], set(estado.get("manchetes_dia", {}).get(hoje, []))
    for f in list(escolhidos):
        motivos = qa.revisar(f, manchetes)
        if motivos:
            segurados.append((f, motivos))
            escolhidos.remove(f)
            continue
        manchetes.add(f.get("manchete_padrao") or "")
    estado["manchetes_dia"] = {hoje: sorted(manchetes)}
    if segurados:
        log += ["## Segurados pelo QA (não publicados)"] + [
            f"- {f.get('manchete_padrao') or f.get('orgao')} → {'; '.join(m)}" for f, m in segurados] + [""]
    for f in escolhidos:
        post = redacao.montar(f, True)
        status = "OK" if not post["erros"] else "BLOQUEADO: " + "; ".join(post["erros"])
        hab = f" | R$/hab {f['por_habitante']:.2f}" if f.get("por_habitante") else ""
        log += [f"## {status} | {f.get('tipo')} | nota {f['nota']}{hab} | tags {post['variante_tag']}",
                "```", post["texto"], "```", f"Objeto: {f.get('objeto', '')[:300]}", ""]
        if not post["erros"]:
            nome_card = f"cards/{hoje}/{abs(hash(f['id'])) % 10**10}.png"
            try:
                card.gerar(f, RAIZ / nome_card)
            except Exception as e:  # noqa: BLE001
                print(f"  card falhou: {e}")
                nome_card = ""
            aprovados.append((f, dict(post, card=nome_card)))

    # o que não foi escolhido fica registrado, com a nota
    resto = [f for f in candidatos if f not in escolhidos]
    if resto:
        log += ["", "### Não escolhidos (nota)"] + [
            f"- {f.get('nota', '?')} | {f.get('tipo')} | {f.get('manchete_padrao') or f.get('orgao', '')}"[:160]
            for f in sorted(resto, key=lambda f: -f.get("nota", 0))[:30]]

    if ligar and aprovados:
        # publicação acontece no passo seguinte do workflow, depois que os cards estiverem no GitHub
        (RAIZ / "dados").mkdir(exist_ok=True)
        (RAIZ / "dados" / "pendentes.json").write_text(json.dumps(
            {"saida": f"saida/{data}.md", "posts": [p for _, p in aprovados]}, ensure_ascii=False), encoding="utf-8")
        publicados = [f for f, _ in aprovados]
        pontos.registrar(estado, publicados)
        log += ["", f"{len(aprovados)} posts prontos para o Buffer (resultado abaixo)."]
        for f in publicados:
            estado["vistos"].append(f["id"])
            estado["vistos"].extend(f.get("ids_extras", []))
            if f.get("tipo") == "raiox":
                estado["raiox_dia"] = hoje

    # tudo que foi avaliado hoje não volta amanhã
    for f in candidatos:
        if f.get("tipo") != "raiox":
            estado["vistos"].append(f["id"])
            estado["vistos"].extend(f.get("ids_extras", []))

    SAIDA.mkdir(exist_ok=True)
    arq = SAIDA / f"{data}.md"
    arq.write_text("\n".join(log), encoding="utf-8")
    _salvar_estado(estado)
    print(f"Gravado: {arq.relative_to(RAIZ)}")


if __name__ == "__main__":
    executar()
