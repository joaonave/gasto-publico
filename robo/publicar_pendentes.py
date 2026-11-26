"""Passo 2 do workflow: agenda no Buffer os posts preparados (cards já estão no GitHub)."""
import json
import os
from pathlib import Path

import requests

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
    _avisar(d, resultados)


def _avisar(d, resultados):
    """Abre um aviso (issue) no GitHub com a fila do dia: janela para apagar no Buffer antes de sair."""
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        return
    linhas = [f"- **{r}**\n  > {t.splitlines()[0]}" for t, r in resultados]
    segurados = [ln for ln in (RAIZ / d["saida"]).read_text(encoding="utf-8").splitlines()
                 if ln.startswith("- ") and "→" in ln]
    corpo = ("@joaonave fila de hoje no Buffer. Se algo estiver errado, apague no Buffer antes do horário.\n\n"
             + "\n".join(linhas)
             + ("\n\n**Segurados pelo QA (não publicados):**\n" + "\n".join(segurados) if segurados else "")
             + f"\n\nRelatório completo: `{d['saida']}`")
    r = requests.post(f"https://api.github.com/repos/{repo}/issues", timeout=30,
                      headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                      json={"title": f"Fila do dia – {len(resultados)} posts", "body": corpo})
    print(f"  aviso no GitHub: {r.status_code}")


if __name__ == "__main__":
    executar()
