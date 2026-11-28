"""Rodada do robô: coleta → candidatos → pontos → conferência (QA + itens do contrato) → redação → Buffer.

Dia de publicação: rodada a partir das 21h agenda o dia seguinte (a fila de amanhã fica pronta na véspera);
antes disso, agenda o próprio dia. Várias tentativas de agendamento por dia; só a primeira de cada dia publica.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import (card, emendas, emendas_portal, homicidios, itens, municipio, outros_pncp, pix, pncp, pontos,
               publicar, qa, ranking, redacao, shows)

RAIZ = Path(__file__).resolve().parent.parent
ESTADO = RAIZ / "dados" / "estado.json"
SAIDA = RAIZ / "saida"
BRT = timezone(timedelta(hours=-3))
VIRADA_H = 21  # a partir desta hora a rodada prepara o dia seguinte
DIAS_ATRAS = 7  # poucos candidatos: busca contratos de até N dias antes


def _carregar_estado():
    if ESTADO.exists():
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    return {"vistos": []}


def _salvar_estado(e):
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    e["vistos"] = e["vistos"][-20000:]
    e["shows_vistos"] = e.get("shows_vistos", [])[-5000:]
    ESTADO.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")


def _normalizar_data(txt):
    """Aceita 20261102, 2026-11-02, 2026/11/02 ou 02/11/2026."""
    d = "".join(ch for ch in (txt or "") if ch.isdigit())
    if len(d) != 8:
        return None
    return d if int(d[:4]) > 1900 else d[4:] + d[2:4] + d[:2]


def dia_de_publicacao(agora=None):
    agora = agora or datetime.now(BRT)
    return (agora + timedelta(days=1) if agora.hour >= VIRADA_H else agora).strftime("%Y-%m-%d")


def _chave_show(f):
    return f"{f.get('orgao', '')}|{(f.get('artista') or '').upper()}|{round(f.get('valor') or 0, -3):.0f}"


# ---------- candidatos ----------

def _candidatos_pncp(data, estado, log):
    contratos = pncp.contratos_do_dia(data)
    todos_shows = shows.selecionar(contratos)
    com_artista = [f for f in todos_shows if f.get("artista")]  # show sem nome não engaja: fica fora
    c = [f for f in com_artista + outros_pncp.selecionar(contratos) if f["id"] not in estado["vistos"]]
    log.append(f"PNCP {data}: {len(contratos)} contratos | shows {len(todos_shows)} "
               f"({len(todos_shows) - len(com_artista)} sem artista, descartados) | candidatos: {len(c)}")
    return c


def _emendas(estado, dia, log):
    """Baixa emendas e cadastro (usados no ranking e no cruzamento Pix). Devolve (linhas, cadastro, ranking)."""
    cadastro = emendas.parlamentares()
    linhas = emendas_portal.baixar()
    f = ranking.do_dia(estado, linhas, cadastro) if estado.get("ranking_dia") != dia else None
    log.append(f"Emendas: {len(linhas)} linhas | ranking do dia: {f['variante'] if f else 'não'}")
    return linhas, cadastro, ([f] if f else [])


# ---------- rodada ----------

def executar(data=None):
    data = (_normalizar_data(data or os.environ.get("DATA"))
            or (datetime.now(BRT) - timedelta(days=1)).strftime("%Y%m%d"))
    ligar = os.environ.get("PUBLICAR", "false").lower() == "true"
    simular = os.environ.get("SIMULAR") == "1"
    estado = _carregar_estado()
    dia = dia_de_publicacao()
    if simular:  # teste integrado: dia "novo", nada é gravado nem publicado
        estado.update(pub_dia=None, pub_qtd=0, pub_cat={}, ranking_dia=None, manchetes_dia={})
        ligar = False
    automatico = os.environ.get("GITHUB_EVENT_NAME") in ("schedule", "workflow_dispatch") and not os.environ.get("DATA")
    if automatico and not simular and estado.get("ultima_rodada") == dia:
        print(f"Fila de {dia} já preparada; tentativa extra ignorada.")
        return
    print(f"Dados: {data} | dia de publicação: {dia} | publicar: {ligar}")
    log = [f"# Robô – dados de {data[6:]}/{data[4:6]}/{data[:4]} – publicação em {dia} – "
           f"execução {datetime.now(BRT):%d/%m %H:%M}", ""]

    candidatos, linhas, cadastro = [], [], {}
    try:
        candidatos += _candidatos_pncp(data, estado, log)
    except Exception as e:  # noqa: BLE001
        log.append(f"Erro no PNCP: {e}")
    try:
        linhas, cadastro, rk = _emendas(estado, dia, log)
        candidatos += rk
    except Exception as e:  # noqa: BLE001
        log.append(f"Erro nas emendas (sem ranking e sem Pix hoje): {e}")

    # poucos candidatos: contratos dos dias anteriores ainda não publicados
    vagas = pontos.TETO_DIA - (estado.get("pub_qtd", 0) if estado.get("pub_dia") == dia else 0)
    alvo = 3 * vagas if vagas >= 3 else 0
    base = datetime.strptime(data, "%Y%m%d")
    for k in range(1, DIAS_ATRAS + 1):
        if len(candidatos) >= alvo:
            break
        d = (base - timedelta(days=k)).strftime("%Y%m%d")
        ids = {f["id"] for f in candidatos}
        try:
            candidatos += [f for f in _candidatos_pncp(d, estado, log) if f["id"] not in ids]
        except Exception as e:  # noqa: BLE001
            log.append(f"Erro no PNCP {d}: {e}")

    pop = pontos.Populacao(RAIZ / "dados" / "populacao.json")
    muni = municipio.Municipios(RAIZ / "dados" / "municipios.json")
    hom = homicidios.Homicidios(pop.por_cod)

    # emenda Pix recebida pela prefeitura que contratou o gasto (+ esgoto da cidade)
    if linhas:
        idx = pix.indice(linhas)
        com_pix = 0
        for f in candidatos:
            if pontos.categoria(f) in ("show", "midia", "inusitada"):
                pix.anexar(f, idx, cadastro)
                if f.get("pix"):
                    com_pix += 1
                    d = muni.dados(pop.cod(f))
                    if "esgoto" in d:
                        f["sem_esgoto"] = round(100 - d["esgoto"], 1)
        log.append(f"Emenda Pix: {len(idx)} cidades com Pix em 12 meses | {com_pix} contratos de prefeitura que recebeu Pix")

    escolhidos, segurados = _escolher_e_conferir(candidatos, estado, dia, pop)
    log += ["", f"Candidatos: {len(candidatos)} | escolhidos e conferidos: {len(escolhidos)} | "
                f"segurados: {len(segurados)} (já agendados para {dia}: {estado.get('pub_qtd', 0)})", ""]
    if segurados:
        log += ["## Segurados (não publicados)"] + [
            f"- {f.get('manchete_padrao') or f.get('orgao')} → {'; '.join(m)}" for f, m in segurados] + [""]

    aprovados = []
    for f in escolhidos:
        post = redacao.montar(f, True)
        # dados da cidade só quando o órgão é municipal; o item confirmado do contrato vem primeiro
        cod = pop.cod(f) if redacao.eh_municipal(f.get("orgao")) else ""
        cidade = municipio.comentario(f, muni.dados(cod), pop.por_cod.get(cod), hom.de(cod),
                                      getattr(hom, "anos", "")) if cod else ""
        post["dados_municipio"] = "\n".join(x for x in (itens.linha(f.get("item_confirmado")), cidade) if x)
        post["erros"] += qa.conferencia_final(f, post)  # último portão antes do Buffer
        status = "OK" if not post["erros"] else "BLOQUEADO: " + "; ".join(post["erros"])
        hab = f" | R$/hab {f['por_habitante']:.2f}" if f.get("por_habitante") else ""
        log += [f"## {status} | {f.get('tipo')} | nota {f['nota']}{hab}",
                "```", post["corpo_sem_link"] + (f"\n--- 1º comentário ---\n{post['dados_municipio']}"
                                                  if post["dados_municipio"] else ""),
                "```", f"Link: {post['link']}", f"Objeto: {f.get('objeto', '')[:300]}", ""]
        if post["erros"]:
            segurados.append((f, post["erros"]))
            continue
        nome_card = f"cards/{dia}/{abs(hash(f['id'])) % 10**10}.png"
        try:
            card.gerar(f, RAIZ / nome_card)
        except Exception as e:  # noqa: BLE001
            print(f"  card falhou: {e}")
            nome_card = ""
        post.update(card=nome_card, id=f["id"], ids_extras=f.get("ids_extras", []), categoria=pontos.categoria(f),
                    chave_show=_chave_show(f) if f.get("tipo") == "show" else "")
        aprovados.append((f, post))
    muni.salvar()

    resto = [f for f in candidatos if f not in escolhidos]
    if resto:
        log += ["", "### Não escolhidos (continuam valendo nos próximos dias)"] + [
            f"- {f.get('nota', '?')} | {f.get('tipo')} | {f.get('manchete_padrao') or f.get('orgao', '')}"[:160]
            for f in sorted(resto, key=lambda f: -f.get("nota", 0))[:30]]

    if simular:
        _relatorio_simulacao(data, dia, aprovados, segurados, log)
        return

    if ligar and aprovados:
        (RAIZ / "dados" / "pendentes.json").write_text(json.dumps(
            {"saida": f"saida/{data}.md", "dia": dia, "posts": [p for _, p in aprovados]},
            ensure_ascii=False), encoding="utf-8")
        pontos.registrar(estado, [f for f, _ in aprovados])
        log += ["", f"{len(aprovados)} posts prontos para o Buffer (resultado abaixo)."]
        for f, _ in aprovados:
            estado["vistos"] += [f["id"]] + f.get("ids_extras", [])
            if f.get("tipo") == "show":
                estado.setdefault("shows_vistos", []).append(_chave_show(f))
            if f.get("tipo") == "ranking":
                estado["ranking_dia"], estado["ranking_pos"] = dia, f["ranking_pos_prox"]
    # segurados não voltam; não escolhidos continuam valendo (até 90 dias da assinatura)
    for f, _ in segurados:
        estado["vistos"] += [f["id"]] + f.get("ids_extras", [])

    estado["ultima_rodada"] = dia
    SAIDA.mkdir(exist_ok=True)
    arq = SAIDA / f"{data}.md"
    arq.write_text("\n".join(log), encoding="utf-8")
    _salvar_estado(estado)
    print(f"Gravado: {arq.relative_to(RAIZ)}")


def _escolher_e_conferir(candidatos, estado, dia, pop):
    """Escolhe pela nota; confere cada escolhido (QA + itens do contrato no PNCP); se algum cair,
    escolhe de novo para não perder a vaga."""
    segurados, escolhidos = [], []
    manchetes = set(estado.get("manchetes_dia", {}).get(dia, []))
    shows_vistos = set(estado.get("shows_vistos", []))
    restantes = list(candidatos)
    for _ in range(6):
        novos = [f for f in pontos.escolher(restantes, estado, dia, pop) if f not in escolhidos]
        if not novos:
            break
        caiu = False
        for f in novos:
            if f.get("tipo") == "show" and not f.get("manchete_padrao"):
                f["manchete_padrao"] = redacao._manchete_padrao(f)  # deduplicação e card usam a manchete
            motivos = qa.revisar(f, manchetes)
            if f.get("tipo") == "show" and _chave_show(f) in shows_vistos:
                motivos.append("mesmo show (órgão, artista, valor) já publicado")
            if not motivos:
                ok, motivo, item = itens.verificar(f)
                if ok:
                    f["item_confirmado"] = item
                else:
                    motivos = [motivo]
            if motivos:
                segurados.append((f, motivos))
                restantes.remove(f)
                caiu = True
                continue
            manchetes.add(f.get("manchete_padrao") or "")
            escolhidos.append(f)
        if not caiu:
            break
    estado["manchetes_dia"] = {dia: sorted(manchetes)}
    return escolhidos, segurados


def _relatorio_simulacao(data, dia, aprovados, segurados, log):
    """Teste integrado: mostra exatamente o que iria ao X (post + 1º comentário) e confere cada um."""
    out = [f"# Teste integrado – dados de {data} – publicação em {dia} – {datetime.now(BRT):%d/%m %H:%M}", ""]
    try:
        canal = publicar.canal_x()
        out.append(f"Buffer: conectado, canal X = {canal.get('name') or canal.get('id')}")
    except Exception as e:  # noqa: BLE001
        out.append(f"Buffer: FALHA na conexão ({e})")
    problemas = 0
    for f, post in aprovados:
        fonte = f"Fonte oficial:\n{post['link']}"
        dados = publicar._caber(post.get("dados_municipio") or "", "\n\n" + fonte)
        resposta = (dados + "\n\n" if dados else "") + fonte
        checks = {"1º comentário ≤ 280": publicar._tam_x(resposta) <= 280,
                  "card gerado": bool(post.get("card")) and (RAIZ / post["card"]).exists()}
        falhou = [k for k, v in checks.items() if not v]
        problemas += bool(falhou)
        out += [f"## {'OK' if not falhou else 'PROBLEMA: ' + ', '.join(falhou)} | {f.get('tipo')} | nota {f.get('nota')}",
                "POST:", "```", post["corpo_sem_link"], "```", "1º COMENTÁRIO:", "```", resposta, "```",
                f"Objeto: {(f.get('objeto') or '')[:250]}", ""]
    out.insert(2, f"**{len(aprovados)} posts prontos | {problemas} com problema | {len(segurados)} segurados**")
    out += ["", "## Log da rodada", ""] + log
    arq = RAIZ / "dados" / "diag" / "teste_integrado.md"
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text("\n".join(out), encoding="utf-8")
    print(f"Teste integrado: {len(aprovados)} posts, {problemas} com problema -> {arq.relative_to(RAIZ)}")


if __name__ == "__main__":
    executar()
