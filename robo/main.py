"""Execução diária: coleta → filtro → redação → checagem → arquivo (e, depois, Buffer)."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config, emendas, pncp, posts_emendas, redacao, shows

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


def executar(data=None):
    data = (_normalizar_data(data or os.environ.get("DATA"))
            or (datetime.now(BRT) - timedelta(days=1)).strftime("%Y%m%d"))
    publicar = os.environ.get("PUBLICAR", "false").lower() == "true"
    print(f"Data: {data} | publicar: {publicar}")

    estado = _carregar_estado()
    contratos = pncp.contratos_do_dia(data)
    achados = [f for f in shows.selecionar(contratos) if f["id"] not in estado["vistos"]]
    print(f"Shows acima do corte: {len(achados)}")

    linhas = [f"# Posts – {data[6:]}/{data[4:6]}/{data[:4]}",
              f"Contratos no PNCP: {len(contratos)} | shows acima do corte: {len(achados)}", ""]
    for f in achados[: config.MAX_POSTS_DIA]:
        estado["contador_posts"] += 1
        pedir = estado["contador_posts"] % config.COMENTARIO_A_CADA == 0
        post = redacao.montar(f, pedir)
        status = "OK" if not post["erros"] else "BLOQUEADO: " + "; ".join(post["erros"])
        linhas += [f"## {status} ({post['origem']})", "```", post["texto"], "```",
                   f"Objeto: {f['objeto']}", ""]
        if publicar and not post["erros"]:
            pass  # Buffer entra na próxima etapa
        estado["vistos"].append(f["id"])

    linhas += _bloco_emendas(estado)

    SAIDA.mkdir(exist_ok=True)
    arq = SAIDA / f"{data}.md"
    arq.write_text("\n".join(linhas), encoding="utf-8")
    _salvar_estado(estado)
    print(f"Gravado: {arq.relative_to(RAIZ)}")


def _bloco_emendas(estado):
    linhas = ["", "# Emendas Pix", ""]
    try:
        cadastro = emendas.parlamentares()
        print(f"Parlamentares no cadastro: {len(cadastro)}")
        todos = emendas.carregar_tudo(RAIZ / "dados" / "emendas")
        ano = str(max(emendas.ANOS))
        hoje = [p for p in todos if str(p["ano"]) == ano]
        ids_ant = set(estado.get("pix_ids", []))
        if not ids_ant:
            linhas.append(f"Primeira execução: base criada com {len(hoje)} planos de {ano}. Novidades a partir de amanhã.")
        else:
            novos = [posts_emendas.fatos_emenda(p, cadastro) for p in emendas.novos_planos(hoje, ids_ant)]
            novos.sort(key=lambda f: (f["tipo"] != "emenda_fora", -f["valor"]))
            linhas.append(f"Planos novos hoje: {len(novos)}")
            for f in novos[: config.MAX_POSTS_DIA]:
                estado["contador_posts"] += 1
                post = redacao.montar(f, estado["contador_posts"] % config.COMENTARIO_A_CADA == 0)
                status = "OK" if not post["erros"] else "BLOQUEADO: " + "; ".join(post["erros"])
                linhas += [f"## {status} ({f['tipo']})", "```", post["texto"], "```", ""]
        estado["pix_ids"] = [p["id"] for p in hoje]

        # Raio-X do dia (rodízio)
        for _ in range(20):
            nome = emendas.proximo_raio_x(estado, cadastro)
            rx = emendas.raio_x(nome, todos, cadastro)
            if rx:
                th = posts_emendas.thread_raio_x(rx)
                status = "OK" if not th["erros"] else "BLOQUEADO: " + "; ".join(th["erros"])
                linhas += [f"## Raio-X do dia — {status}"]
                for t in th["posts"]:
                    linhas += ["```", t, "```"]
                break
    except Exception as e:  # noqa: BLE001
        linhas.append(f"Erro no bloco de emendas: {e}")
        print(f"Erro emendas: {e}")
    return linhas


if __name__ == "__main__":
    executar()
