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
    resultados = publicar.agendar(d["posts"], dia=d.get("dia"))
    _devolver_falhas(d["posts"], resultados)
    arq = RAIZ / d["saida"]
    linhas = ["", "# Publicação (Buffer)", ""] + [f"- {r}: {t.splitlines()[0][:90]}" for t, r in resultados]
    with arq.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(linhas) + "\n")
    PEND.unlink()
    _avisar(d, resultados)


def _devolver_falhas(posts, resultados):
    """Post que o Buffer recusou volta a concorrer: sai dos 'vistos' e do teto do dia."""
    falhas = [p for p, (_, r) in zip(posts, resultados) if not r.startswith("agendado")]
    if not falhas:
        return
    arq = RAIZ / "dados" / "estado.json"
    e = json.loads(arq.read_text(encoding="utf-8"))
    for p in falhas:
        ids = {p.get("id")} | set(p.get("ids_extras") or [])
        e["vistos"] = [v for v in e.get("vistos", []) if v not in ids]
        if p.get("chave_show") in e.get("shows_vistos", []):
            e["shows_vistos"].remove(p["chave_show"])
        e["pub_qtd"] = max(0, e.get("pub_qtd", 0) - 1)
        cat = p.get("categoria")
        if cat and e.get("pub_cat", {}).get(cat):
            e["pub_cat"][cat] -= 1
        if p.get("categoria") == "ranking":
            e["ranking_dia"] = None
        for dia, lst in e.get("manchetes_dia", {}).items():  # a manchete não pode barrar a nova tentativa
            if p.get("manchete") in lst:
                lst.remove(p["manchete"])
    arq.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  {len(falhas)} post(s) recusado(s) pelo Buffer voltam a concorrer")


def _avisar(d, resultados):
    """Abre um aviso (issue) no GitHub com a fila do dia: janela para apagar no Buffer antes de sair."""
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        return
    linhas = [f"- **{r}**\n  > {t.splitlines()[0]}" for t, r in resultados]
    segurados = [ln for ln in (RAIZ / d["saida"]).read_text(encoding="utf-8").splitlines()
                 if ln.startswith("- ") and "→" in ln]
    corpo = (f"@joaonave fila de {d.get('dia', 'hoje')} no Buffer. Se algo estiver errado, apague no Buffer antes do horário.\n\n"
             + "\n".join(linhas)
             + ("\n\n**Segurados pelo QA (não publicados):**\n" + "\n".join(segurados) if segurados else "")
             + f"\n\nRelatório completo: `{d['saida']}`")
    r = requests.post(f"https://api.github.com/repos/{repo}/issues", timeout=30,
                      headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                      json={"title": f"Fila de {d.get('dia', 'hoje')} – {len(resultados)} posts", "body": corpo})
    print(f"  aviso no GitHub: {r.status_code}")


if __name__ == "__main__":
    executar()
