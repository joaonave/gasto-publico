"""Ranking diário de emendas pagas no ano (Portal da Transparência), em rodízio:
deputados, senadores, partido, UF, emenda Pix e emendas "sem dono" (bancada/comissão/relator).
"""
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from .emendas import norm

PIX = "Emenda Individual - Transferências Especiais"
VARIANTES = ["deputados", "senadores", "partido", "pix", "uf", "sem_dono"]
LINK = "https://portaldatransparencia.gov.br/emendas"


def _v(x):
    """Valor curto para as linhas do ranking."""
    if x >= 1e9:
        return f"{x / 1e9:.1f} bi".replace(".", ",")
    return f"{x / 1e6:.1f} mi".replace(".", ",")


def _vm(x):
    """Valor da manchete: mil, milhão/milhões, bilhão/bilhões."""
    if x >= 1e9:
        return f"R$ {x / 1e9:.1f} {'BILHÃO' if x < 2e9 else 'BILHÕES'}".replace(".", ",")
    if x >= 1e6:
        return f"R$ {x / 1e6:.1f} {'MILHÃO' if x < 2e6 else 'MILHÕES'}".replace(".", ",")
    return f"R$ {x / 1e3:.0f} MIL"


_COLETIVA = re.compile(r"bancada|comiss|relator", re.IGNORECASE)


def _somas(linhas, cadastro, ano):
    """pago/pix por parlamentar do cadastro; 'sem dono' = emendas coletivas (bancada, comissão, relator) pelo tipo
    ou autor. Emenda individual de ex-parlamentar/licenciado fica fora das duas contas."""
    pago, pix, sem_dono, total = defaultdict(float), defaultdict(float), 0.0, 0.0
    for r in linhas:
        if not str(r.get("ano_mes") or "").startswith(ano):
            continue
        v = r.get("pago") or 0
        total += v
        k = norm(r["autor"])
        if _COLETIVA.search(r.get("tipo") or "") or _COLETIVA.search(r.get("autor") or ""):
            sem_dono += v
        elif k in cadastro:
            pago[k] += v
            if r.get("tipo") == PIX:
                pix[k] += v
    return pago, pix, sem_dono, total


def _quem(c):
    return f"{c['nome']} ({c['partido']}-{c['uf']})"


def fato(variante, linhas, cadastro, ano=None):
    agora = datetime.now(timezone(timedelta(hours=-3)))  # Brasília
    ano = ano or str(agora.year)
    if ano == str(agora.year) and agora.month < 2:
        return None  # janeiro: quase nenhum pagamento no ano ainda
    pago, pix, sem_dono, total = _somas(linhas, cadastro, ano)
    if not pago:
        return None
    base = {"id": f"ranking-{variante}-{datetime.now():%Y%m%d}", "tipo": "ranking", "variante": variante,
            "link": LINK, "uf": "", "municipio": "",
            "contexto": f"Ranking de emendas pagas em {ano}, Portal da Transparência."}

    def lista(itens, fmt):
        return "\n".join(f"{i}. {fmt(k, v)}" for i, (k, v) in enumerate(itens, 1))

    if variante in ("deputados", "senadores"):
        cargo = "Dep." if variante == "deputados" else "Sen."
        top = sorted(((k, v) for k, v in pago.items() if cadastro[k].get("cargo") == cargo), key=lambda kv: -kv[1])[:4]
        if not top:
            return None
        lider = cadastro[top[0][0]]
        manchete = f"{cargo.upper()} {lider['nome'].upper()} LIDERA O RANKING DE EMENDAS PAGAS EM {ano}: {_vm(top[0][1])}"
        corpo = lista(top, lambda k, v: f"{_quem(cadastro[k])} {_v(v)}")
        valor = top[0][1]
    elif variante == "pix":
        top = sorted(pix.items(), key=lambda kv: -kv[1])[:3]
        if not top:
            return None
        manchete = f"RANKING DA \"EMENDA PIX\" EM {ano}: {cadastro[top[0][0]]['nome'].upper()} LIDERA COM {_vm(top[0][1])}"
        corpo = lista(top, lambda k, v: f"{_quem(cadastro[k])} {_v(v)}")
        valor = top[0][1]
    elif variante in ("partido", "uf"):
        g, n = defaultdict(float), defaultdict(int)
        for k, v in pago.items():
            g[cadastro[k][variante]] += v
            n[cadastro[k][variante]] += 1
        media = sorted(((x, g[x] / n[x]) for x in g if n[x] >= 3), key=lambda kv: -kv[1])
        if len(media) < 4:
            return None
        nome = "PARTIDO" if variante == "partido" else "ESTADO"
        manchete = f"EMENDAS PAGAS EM {ano} POR {nome}: {media[0][0]} LIDERA COM {_vm(media[0][1])} POR PARLAMENTAR"
        corpo = (lista(media[:4], lambda x, v: f"{x} {_v(v)}") +
                 f"\n…\nÚltimo: {media[-1][0]}, {_v(media[-1][1])}\n(média por parlamentar; com 3+ parlamentares)")
        valor = media[0][1]
    else:  # sem_dono
        if not sem_dono:
            return None
        manchete = f"{_vm(sem_dono)} EM EMENDAS DE BANCADA, COMISSÃO E RELATOR PAGAS EM {ano}: SEM NOME DE PARLAMENTAR NO PORTAL"
        corpo = (f"São {round(100 * sem_dono / total)}% de todas as emendas pagas no ano.\n"
                 f"Emendas individuais, com nome e sobrenome: R$ {_v(sum(pago.values()))}.")
        valor = sem_dono
    # lista encurta (4 → 3 → 2 nomes) até o post caber em 280 com folga
    def cabe(t):
        return len(manchete) + len(t) + 75 <= 280  # comentário + #GastoPublico
    if variante in ("deputados", "senadores", "pix"):
        linhas_ = corpo.split("\n")
        while len(linhas_) > 2 and not cabe("\n".join(linhas_)):
            linhas_.pop()
        corpo = "\n".join(linhas_)
    comentario = {"deputados": "Seu deputado está na lista?", "senadores": "Seu senador está na lista?",
                  "pix": "Transferência especial: direto no caixa da prefeitura.",
                  "partido": "E o partido que você vota?", "uf": "E o seu estado, onde ficou?",
                  "sem_dono": "Quem indicou? Boa pergunta."}[variante]
    return dict(base, comentario_fixo=comentario, valor=valor, valor_manchete=_vm(valor), manchete_padrao=manchete, linha_fato=corpo)


def do_dia(estado, linhas, cadastro):
    """Próxima variante do rodízio que tenha dado."""
    pos = estado.get("ranking_pos", 0)
    for i in range(len(VARIANTES)):
        v = VARIANTES[(pos + i) % len(VARIANTES)]
        f = fato(v, linhas, cadastro)
        if f:
            f["ranking_pos_prox"] = (pos + i + 1) % len(VARIANTES)
            return f
    return None
