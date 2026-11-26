"""Execução diária: coleta → filtro → redação → checagem → arquivo (e, depois, Buffer)."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config, pncp, redacao, shows

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

    SAIDA.mkdir(exist_ok=True)
    arq = SAIDA / f"{data}.md"
    arq.write_text("\n".join(linhas), encoding="utf-8")
    _salvar_estado(estado)
    print(f"Gravado: {arq.relative_to(RAIZ)}")


if __name__ == "__main__":
    executar()
