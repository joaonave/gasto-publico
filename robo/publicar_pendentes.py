"""Passo 2 do workflow: agenda no Buffer os posts preparados (cards já estão no GitHub)."""
import json
from pathlib import Path

from . import publicar

RAIZ = Path(__file__).resolve().parent.parent
PEND = RAIZ / "dados" / "pendentes.json"


def executar():
    if not PEND.exists():
        print("Nada pendente.")
        return
    d = json.loads(PEND.read_text(encoding="utf-8"))
    resultados = publicar.agendar(d["posts"])
    arq = RAIZ / d["saida"]
    linhas = ["", "# Publicação (Buffer)", ""] + [f"- {r}: {t.splitlines()[0][:90]}" for t, r in resultados]
    with arq.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(linhas) + "\n")
    PEND.unlink()


if __name__ == "__main__":
    executar()
