"""Outros gatilhos do PNCP (mesma coleta dos shows): publicidade/mídia e compras inusitadas."""
import re

from .shows import _num, _recente, agrupar, fatos as fatos_base, valor_manchete

MIDIA = re.compile(r"publicidade|propaganda|veicula[çc][ãa]o|divulga[çc][ãa]o institucional|"
                   r"ag[êe]ncia de (publicidade|propaganda|comunica)|m[íi]dia (digital|impressa|televisiva)|"
                   r"impulsionamento|inser[çc][õo]es (em|na|no) (r[áa]dio|tv|televis)", re.IGNORECASE)
MIDIA_EXCLUIR = re.compile(r"publica[çc][ãa]o (de|em) (atos|editais|extratos)|di[áa]rio oficial|"
                           r"imprensa oficial|publica[çc][õo]es legais|diagrama[çc]|publica[çc][ãa]o de textos", re.IGNORECASE)
MIDIA_MIN = 300_000

INUSITADAS = {
    "LAGOSTA": r"lagosta", "CAMARÃO": r"camar[ãa]o", "VINHO": r"\bvinhos?\b", "ESPUMANTE": r"espumante|champanhe",
    "UÍSQUE": r"whisk(e)?y|u[íi]sque", "CAVIAR": r"caviar", "PICANHA": r"picanha", "FILÉ MIGNON": r"fil[ée] mignon",
    "BACALHAU": r"bacalhau", "JOIAS": r"\bjoias?\b", "CARRO BLINDADO": r"(ve[íi]culo|carro|autom[óo]vel|caminhonete|suv)s? blindad", "HELICÓPTERO": r"helic[óo]ptero",
    "IATE": r"\biate\b", "JATINHO": r"jatinho|aeronave executiva",
}
INUSITADA_MIN = 20_000
INUSITADA_EXCLUIR = re.compile(r"seguran[çc]a p[úu]blica|pol[íi]cia|resgate|samu|bombeiro|"
                               r"merenda|alimenta[çc][ãa]o escolar|PNAE|hospital|\bobras?\b|reforma|engenharia|clube|constru[çc]|"
                               r"passeio|roteiro|tur[íi]stic|excurs|viagem", re.IGNORECASE)  # "Roteiro do Vinho" é passeio, não compra de vinho


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
            f.update(tipo="midia", contexto="Contrato de publicidade/propaganda do poder público (valor é o teto).")
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
    saida = agrupar(saida)
    for f in saida:
        if f["tipo"] == "midia":
            n = f["qtd_contratos"]
            vm = valor_manchete(f["valor"])
            f["manchete_padrao"] = (f"{_orgao(f)} FECHA {n} CONTRATOS DE PUBLICIDADE DE ATÉ {vm} CADA" if n > 1
                                    else f"{_orgao(f)} FECHA CONTRATO DE PUBLICIDADE DE ATÉ {vm}")
    return saida
