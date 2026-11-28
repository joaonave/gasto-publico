"""Redação do post: manchete padrão em caixa alta + comentário (Pix/esgoto, por morador ou banco) + hashtags.
Sem IA: todo texto sai de modelo fixo preenchido com o dado oficial.
"""
import re

def _manchete_padrao(f):
    if f.get("manchete_padrao"):
        return f["manchete_padrao"]
    orgao = f["orgao"].upper()
    if orgao.startswith("MUNICIPIO DE "):
        orgao = "PREFEITURA DE " + orgao[len("MUNICIPIO DE "):]
    uf = f" ({f['uf']})" if f["uf"] and orgao.startswith("PREFEITURA") else ""
    tipo = "SHOW E ESTRUTURA" if f["inclui_estrutura"] else "SHOW"
    de = f" DE {f['artista'].upper()}" if f.get("artista") else ""
    # contrato assinado não é pagamento: "CONTRATA", nunca "PAGA"
    return f"{orgao}{uf} CONTRATA {tipo}{de} POR {f['valor_manchete']}"


def _linha_fato(f):
    if f.get("linha_fato"):
        return f["linha_fato"]
    forn = f["fornecedor"]
    if f.get("qtd_contratos", 1) > 1:
        forn += f" e mais {f['qtd_contratos'] - 1}"
    partes = [forn, f"{f['valor_exato']}" + (" cada" if f.get("qtd_contratos", 1) > 1 else "")]
    if f["data_assinatura"]:
        partes.append(f"assinado em {f['data_assinatura']}")
    return " | ".join(p for p in partes if p)


LINKS_OK = ("https://pncp.gov.br/", "https://portaldatransparencia.gov.br/")

PROIBIDAS = re.compile(r"corrup|desvi|roub|superfatur|propina|ladr|crime|fraud", re.IGNORECASE)


def _sem_acento(t):
    import unicodedata
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().upper()


def checar(f, manchete, comentario):
    """Retorna lista de problemas. Vazia = pode publicar."""
    erros = []
    if f["valor_manchete"] not in manchete:
        erros.append("valor da manchete diferente do dado")
    valores = re.findall(r"R\$\s?[\d.,]+", manchete)
    if any(v.replace(" ", "") not in f["valor_manchete"].replace(" ", "") for v in valores):
        erros.append("manchete tem valor que não está no dado")
    if manchete != manchete.upper():
        erros.append("manchete não está em caixa alta")
    if comentario and re.search(r"\d", comentario):
        erros.append("comentário com número")
    if f.get("tipo") in ("show", "midia", "inusitada") and re.search(r"\bPAG(A|OU|AR|AM)\b", manchete.upper()):
        erros.append("contrato não é pagamento: manchete com PAGA")
    if f.get("tipo") == "show" and f.get("artista") and _sem_acento(f["artista"]) not in _sem_acento(manchete):
        erros.append("manchete sem o artista do contrato")
    if PROIBIDAS.search(manchete + " " + comentario):
        erros.append("palavra proibida (acusação)")
    if not f["link"].startswith(LINKS_OK):
        erros.append("link inválido")
    return erros


COMENTARIOS = {
    "show": ["Mas a festa vai ser boa.", "Prioridades.", "O povo pede posto de saúde, a prefeitura entrega palco.",
             "Pão e circo. Só que sem o pão.", "Animação garantida. O resto a gente vê depois.",
             "E ainda tem quem reclame do buraco na rua.", "Na hora de pagar professor, falta verba.",
             "Depois do show, a fila do posto continua lá.", "Pelo menos a música é boa. Dizem.",
             "O orçamento aperta. O palco, nunca.", "Cultura é importante. A conta também.",
             "A conta da entrada é sua, mesmo sem ir.", "Na sua cidade também é assim?",
             "Você iria nesse show sabendo que a conta é sua?", "Quanto custou o último show na sua cidade?"],
    "midia": ["Fazer é caro. Contar que fez, mais ainda.", "A propaganda é sempre ótima.",
              "Se não aparecer, não aconteceu.", "A obra pode atrasar. O anúncio, nunca.",
              "Tudo vai muito bem. Pelo menos na propaganda.", "Você já viu essa propaganda por aí?"],
    "inusitada": ["Tudo pelo bem-estar da população.", "Na sua casa tem isso todo dia?", "Prioridades."],
    "inusitada_comida": ["O cardápio do contribuinte é outro.", "Na sua casa tem isso todo dia?",
                         "Alguém aí foi convidado?"],
    "ranking": ["Seu deputado está na lista?", "Seu senador apareceu aí?", "E o seu, onde ficou?"],
}


COMIDA = {"LAGOSTA", "CAMARÃO", "VINHO", "ESPUMANTE", "UÍSQUE", "CAVIAR", "PICANHA", "FILÉ MIGNON", "BACALHAU"}


def eh_municipal(orgao):
    """Órgão municipal (prefeitura, câmara, fundo, autarquia): o post é sobre a cidade."""
    return bool(re.search(r"munic|prefeit", orgao or "", re.IGNORECASE))


def eh_prefeitura(orgao):
    """Só a prefeitura (não câmara, consórcio, fundo ou instituto municipal)."""
    return bool(re.match(r"^(MUNIC[IÍ]PIO|PREFEITURA)( MUNICIPAL)? D[EOA]S? ", (orgao or "").upper()))


def _comentario_banco(f):
    tipo = f.get("tipo", "show")
    chave = next((k for k in COMENTARIOS if tipo == k), None) or next((k for k in COMENTARIOS if tipo.startswith(k)), "show")
    if chave == "inusitada" and f.get("item") in COMIDA:
        chave = "inusitada_comida"
    lista = COMENTARIOS[chave]
    if not eh_prefeitura(f.get("orgao")):  # frase que fala da prefeitura só quando é a prefeitura
        lista = [x for x in lista if "prefeitura" not in x.lower()] or lista
    return lista[sum(map(ord, str(f.get("id", "")))) % len(lista)]


TAG_TIPO = {"ranking": "#EmendasParlamentares"}  # só temas que as pessoas buscam

ESTADOS = {"AC": "Acre", "AL": "Alagoas", "AP": "Amapa", "AM": "Amazonas", "BA": "Bahia", "CE": "Ceara",
           "DF": "DistritoFederal", "ES": "EspiritoSanto", "GO": "Goias", "MA": "Maranhao", "MT": "MatoGrosso",
           "MS": "MatoGrossoDoSul", "MG": "MinasGerais", "PA": "Para", "PB": "Paraiba", "PR": "Parana",
           "PE": "Pernambuco", "PI": "Piaui", "RJ": "RioDeJaneiro", "RN": "RioGrandeDoNorte",
           "RS": "RioGrandeDoSul", "RO": "Rondonia", "RR": "Roraima", "SC": "SantaCatarina", "SP": "SaoPaulo",
           "SE": "Sergipe", "TO": "Tocantins"}


TAGS_FIXAS = "#GastoPublico #emendas #congresso #imposto"


def _hashtags(f):
    """Fixas do canal + locais (cidade, estado, artista). Nunca hashtag de trending."""
    return (TAGS_FIXAS + " " + _hashtags_locais(f)).strip()


def _hashtags_locais(f):
    import unicodedata
    def limpa(t):
        t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
        return "".join(p.capitalize() for p in re.split(r"[^A-Za-z0-9]+", t) if p)
    tags = []
    if f.get("municipio"):
        tags.append("#" + limpa(f["municipio"]))
    if f.get("uf") in ESTADOS:
        tags.append("#" + ESTADOS[f["uf"]])
    if f.get("artista"):
        tags.append("#" + limpa(f["artista"]))
    tipo = f.get("tipo", "show")
    tag = next((v for k, v in TAG_TIPO.items() if tipo.startswith(k)), None)
    if tag and tag.lower() not in TAGS_FIXAS.lower():
        tags.append(tag)
    return " ".join(dict.fromkeys(t for t in tags if len(t) > 1))


# ironia com a conta por morador (valor do contrato ÷ população IBGE)
INGRESSO = {
    "show": ["Custa {v} por morador. Até quem fica em casa entra na conta.",
             "Sai {v} o \"ingresso\" de cada morador. Criança e idoso inclusos.",
             "{v} por habitante. Ingresso caro pra quem nem vai.",
             "O show custa {v} por morador. Você foi convidado?"],
    "midia": ["Até {v} por morador em propaganda. Você foi bem informado?",
              "Até {v} de cada morador pra prefeitura falar bem dela mesma."],
    "inusitada": ["{v} de cada morador. Você foi convidado?"],
}
MIN_POR_HAB = {"show": 5, "midia": 10, "inusitada": 1}


def _ingresso(f):
    tipo, ph = f.get("tipo"), f.get("por_habitante")
    if tipo not in INGRESSO or not ph or ph < MIN_POR_HAB[tipo]:
        return ""
    if not eh_prefeitura(f.get("orgao")):
        return ""  # câmara, consórcio, órgão estadual/federal: dividir pela população da cidade não faz sentido
    v = f"R$ {ph:,.0f}".replace(",", ".") if ph >= 10 else f"R$ {ph:.2f}".replace(".", ",")
    banco = INGRESSO[tipo]
    return banco[sum(map(ord, f.get("id", ""))) % len(banco)].format(v=v)


def _tam(t):
    """Tamanho no X (emoji conta 2)."""
    return len(t) + sum(1 for c in t if ord(c) > 0xFFFF)


def _linha_pix(f):
    """Pix de emenda + esgoto: dois fatos oficiais lado a lado (sem afirmar que o mesmo dinheiro pagou o gasto)."""
    p = f.get("pix")
    if not p:
        return ""
    from .shows import valor_manchete
    v = valor_manchete(p["total"]).replace("MILHÕES", "milhões").replace("MILHÃO", "milhão").replace("MIL", "mil")
    # total de 12 meses (não "em junho"): é a soma da janela
    t = (f"Nos últimos 12 meses, a prefeitura recebeu {v} em \"emenda Pix\" enviada por {p['autor']}, "
         f"direto no caixa.")
    if f.get("sem_esgoto", 0) >= 50:
        t += f"\n\nE {f['sem_esgoto']:.0f}% dos moradores seguem sem rede de esgoto."
    return t


def montar(f, pedir_comentario=True):
    """Monta o post. Corpo (vai ao X) sem link; o link vai no 1º comentário."""
    manchete = _manchete_padrao(f)
    ingresso = _linha_pix(f) or _ingresso(f)
    comentario = f.get("comentario_fixo") or ingresso or _comentario_banco(f)
    # números da linha do Pix/esgoto/por morador vêm de fontes oficiais próprias: fora da checagem da manchete
    erros = checar(f, manchete, re.sub(r"\d", "", comentario) if comentario == ingresso else comentario)
    embaixo = f"{f['linha_fato']}\n\n{comentario}" if f.get("tipo") == "ranking" and f.get("linha_fato") else comentario
    # hashtags: completas → fixas → só #GastoPublico (marca do formato atual; nunca some)
    corpo_sem_link = ""
    for tags in (_hashtags(f), TAGS_FIXAS, "#GastoPublico"):
        corpo_sem_link = f"{manchete}\n\n{embaixo}\n\n{tags}"
        if _tam(corpo_sem_link) <= 280:
            break
    else:
        erros.append(f"post com {_tam(corpo_sem_link)} caracteres")
    # reserva (só se o Buffer recusar a resposta): link no próprio post
    texto = f"{manchete}\n\n{embaixo}\n\n🔗 {f['link']}\n#GastoPublico"
    return {"texto": texto, "corpo_sem_link": corpo_sem_link, "link": f["link"], "variante_link": "resposta",
            "erros": erros}
