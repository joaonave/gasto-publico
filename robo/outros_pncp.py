"""Outros gatilhos do PNCP (mesma coleta dos shows): publicidade/mídia e compras inusitadas."""
import re

from .shows import _num, _recente, fatos as fatos_base, valor_manchete

MIDIA = re.compile(r"publicidade|propaganda|veicula[çc][ãa]o|divulga[çc][ãa]o institucional|"
                   r"ag[êe]ncia de (publicidade|propaganda|comunica)|m[íi]dia (digital|impressa|televisiva)|"
                   r"impulsionamento|inser[çc][õo]es (em|na|no) (r[áa]dio|tv|televis)", re.IGNORECASE)
MIDIA_EXCLUIR = re.compile(r"publica[çc][ãa]o (de|em) (atos|editais|extratos)|di[áa]rio oficial|"
                           r"imprensa oficial|publica[çc][õo]es legais", re.IGNORECASE)
MIDIA_MIN = 300_000

INUSITADAS = {
    "LAGOSTA": r"lagosta", "CAMARÃO": r"camar[ãa]o", "VINHO": r"\bvinhos?\b", "ESPUMANTE": r"espumante|champanhe",
    "UÍSQUE": r"whisk(e)?y|u[íi]sque", "CAVIAR": r"caviar", "PICANHA": r"picanha", "FILÉ MIGNON": r"fil[ée] mignon",
    "BACALHAU": r"bacalhau", "JOIAS": r"\bjoias?\b", "CARRO BLINDADO": r"blindad", "HELICÓPTERO": r"helic[óo]ptero",
    "IATE": r"\biate\b", "JATINHO": r"jatinho|aeronave executiva",
}
INUSITADA_MIN = 20_000
INUSITADA_EXCLUIR = re.compile(r"seguran[çc]a p[úu]blica|pol[íi]cia|resgate|samu|bombeiro|"
                               r"merenda|alimenta[çc][ãa]o escolar|PNAE|hospital", re.IGNORECASE)


def _orgao(f):
    o = f["orgao"].upper()
    if o.startswith("MUNICIPIO DE "):
        return f"PREFEITURA DE {o[len('MUNICIPIO DE '):]} ({f['uf']})"
    return o


def selecionar(contratos):
    saida = []
    for c in contratos:
        if not _recente(c):
            continue
        obj = c.get("objetoContrato") or ""
        v = _num(c.get("valorGlobal") or c.get("valorInicial"))
        if v >= MIDIA_MIN and MIDIA.search(obj) and not MIDIA_EXCLUIR.search(obj):
            f = fatos_base(c)
            f.update(tipo="midia", manchete_padrao=f"{_orgao(f)} PAGA {valor_manchete(v)} EM PUBLICIDADE",
                     contexto="Contrato de publicidade/propaganda do poder público.")
            saida.append(f)
            continue
        if v >= INUSITADA_MIN and not INUSITADA_EXCLUIR.search(obj):
            for item, rx in INUSITADAS.items():
                if re.search(rx, obj, re.IGNORECASE):
                    f = fatos_base(c)
                    f.update(tipo="inusitada",
                             manchete_padrao=f"CONTRATO DE {valor_manchete(v)} DA {_orgao(f)} INCLUI {item}",
                             contexto=f"Contrato cujo objeto inclui {item.lower()}.")
                    saida.append(f)
                    break
    saida.sort(key=lambda f: f["valor"], reverse=True)
    return saida
