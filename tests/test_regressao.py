"""Erros que já aconteceram de verdade. Cada um vira teste: se voltar, o robô não publica.

Rodar: python -m pytest -q tests
"""
import re
from datetime import date, timedelta

import pytest

from datetime import datetime

from robo import fila, itens, main, municipio, outros_pncp, publicar, qa, ranking, redacao, shows

HOJE = date.today()


def contrato(objeto, valor=500_000, dias=5, orgao="MUNICIPIO DE CIDADE X", fornecedor="FULANO PRODUCOES LTDA",
             seq=1, compra="11111111000111-1-000001/2026"):
    return {"objetoContrato": objeto, "valorGlobal": valor, "dataAssinatura": (HOJE - timedelta(days=dias)).isoformat(),
            "orgaoEntidade": {"razaoSocial": orgao, "cnpj": "11111111000111"},
            "unidadeOrgao": {"municipioNome": "Cidade X", "ufSigla": "MG", "codigoIbge": "3106200"},
            "nomeRazaoSocialFornecedor": fornecedor, "anoContrato": 2026, "sequencialContrato": seq,
            "numeroControlePNCP": f"11111111000111-2-{seq:06d}/2026", "numeroControlePncpCompra": compra}


def tipos(objeto, **kw):
    c = [contrato(objeto, **kw)]
    return [f["tipo"] for f in shows.selecionar(c)] + [f["tipo"] for f in outros_pncp.selecionar(c)]


# ---------- classificação pelo objeto ----------

def test_ouro_preto_restauracao_de_igreja_nao_e_show():
    assert "show" not in tipos("Restauração dos bens artísticos e integrados da Igreja Matriz de Ouro Preto", valor=900_000)


def test_contrato_antigo_teresopolis_fica_fora():
    assert tipos("Contratação de show artístico da banda Fulano", dias=400) == []


def test_credenciamento_santa_barbara_fica_fora():
    assert "show" not in tipos("Credenciamento de artistas e bandas para shows no carnaval")


def test_patrocinio_boat_show_salvador_nao_e_show():
    assert "show" not in tipos('Concessão de patrocínio para execução do evento "BOAT SHOW 2026"', valor=800_000)


def test_iate_clube_nao_e_compra_inusitada():
    assert "inusitada" not in tipos("Reforma da sede do Iate Clube municipal")


def test_diagramacao_de_diario_oficial_nao_e_publicidade():
    assert "midia" not in tipos("Serviços de diagramação e publicação de atos no Diário Oficial", valor=900_000)


def test_roteiro_do_vinho_itapecerica_nao_e_compra_de_vinho():
    assert "inusitada" not in tipos("Contratação de empresa especializada para Passeio Turístico ao Roteiro do Vinho, "
                                    "no Município de São Roque - SP", valor=117_000)


def test_compressor_odontologico_cruz_nao_e_carro_blindado():
    assert "inusitada" not in tipos("COMPRESSOR ODONTOLÓGICO ISENTO DE ÓLEO; MOTOR BLINDADO; SILENCIOSO", valor=226_000)


def test_natal_cinco_agencias_vira_um_post_so_com_teto():
    c = [contrato("Contratação de serviços de publicidade por intermédio de agência de propaganda", valor=1_500_000,
                  seq=i, fornecedor=f"AGENCIA {i}") for i in range(5)]
    fs = outros_pncp.selecionar(c)
    assert len(fs) == 1 and fs[0]["qtd_contratos"] == 5
    assert "ATÉ" in fs[0]["manchete_padrao"] and "CADA" in fs[0]["manchete_padrao"]


# ---------- artista ----------

def test_angra_artista_e_dj_alok_nao_a_produtora_alive():
    obj = ("Contratação direta, por inexigibilidade de licitação, do artista DJ Alok, representado exclusivamente "
           "pela empresa ALIVE PRODUÇÕES ARTÍSTICAS LTDA, para realização de apresentação musical")
    assert shows.artista(obj, "ALIVE PRODUCOES ARTISTICAS LTDA") == "DJ Alok"


# ---------- itens do contrato ----------

ROTEIRO = [{"descricao": "Roteiro Turístico para Passeio Turístico Roteiro do Vinho no Município de São Roque – Sp.",
            "quantidade": 675, "unidadeMedida": "Pessoa", "valorUnitarioEstimado": 284.33, "valorTotal": 191922.75}]


def test_item_roteiro_do_vinho_nao_confirma_vinho():
    f = {"tipo": "inusitada", "item": "VINHO", "item_rx": outros_pncp.INUSITADAS["VINHO"]}
    assert itens.verificar(f, ROTEIRO)[0] is False


def test_inusitada_sem_itens_nao_sai():
    f = {"tipo": "inusitada", "item": "VINHO", "item_rx": outros_pncp.INUSITADAS["VINHO"], "compra": ""}
    assert itens.verificar(f)[0] is False


def test_item_garrafa_de_vinho_confirma_e_vai_pro_comentario():
    vinho = [{"descricao": "Vinho tinto seco 750ml", "quantidade": 120, "unidadeMedida": "Garrafa",
              "valorUnitarioEstimado": 180, "valorTotal": 21600}]
    ok, _, item = itens.verificar({"tipo": "inusitada", "item_rx": outros_pncp.INUSITADAS["VINHO"]}, vinho)
    assert ok and "120 garrafas a R$ 180,00" in itens.linha(item)


def test_show_cujo_item_e_so_palco_nao_sai():
    palco = [{"descricao": "Locação de palco, som e iluminação", "quantidade": 1, "unidadeMedida": "Serviço",
              "valorUnitarioEstimado": 400000, "valorTotal": 400000}]
    assert itens.verificar({"tipo": "show", "artista": "Fulano"}, palco)[0] is False


# ---------- texto ----------

def _show():
    return {"tipo": "show", "id": "x", "valor_manchete": "R$ 500 MIL", "link": "https://pncp.gov.br/app/contratos/1/2026/1",
            "orgao": "MUNICIPIO DE CIDADE X", "municipio": "Cidade X", "uf": "MG", "valor": 500000,
            "valor_exato": "R$ 500.000,00", "fornecedor": "F", "data_assinatura": "20/11/2026", "artista": "Fulano",
            "objeto": "show", "inclui_estrutura": False}


def test_contrato_nao_e_pagamento():
    p = redacao.montar(_show(), True)
    assert " PAGA " not in p["corpo_sem_link"] and "CONTRATA" in p["corpo_sem_link"]


def test_link_vai_no_primeiro_comentario_e_marca_nunca_some():
    p = redacao.montar(_show(), True)
    assert p["variante_link"] == "resposta" and "http" not in p["corpo_sem_link"]
    longo = dict(_show(), sem_esgoto=97, orgao="MUNICIPIO DE SAO JOAO DAS DUAS PONTES", municipio="São João das Duas Pontes",
                 pix={"autor": "Dep. Fulano de Tal Sobrenome (REPUBLICANOS-SP)", "total": 1_398_000, "mes": "202606"})
    assert "#GastoPublico" in redacao.montar(longo, True)["corpo_sem_link"]


def test_rankings_cabem_em_280_e_nao_quebram():
    cad, linhas = {}, []
    for i in range(80):
        k = f"P{i}"
        cad[k] = {"nome": "Fulano de Tal Sobrenome", "cargo": "Dep." if i < 60 else "Sen.",
                  "partido": ["REPUBLICANOS", "SOLIDARIEDADE", "UNIÃO", "PL", "PT"][i % 5], "uf": ["MG", "SP", "BA", "RJ"][i % 4]}
        linhas.append({"autor": k, "ano_mes": f"{HOJE.year}06", "pago": 1e6 * (i + 1), "tipo": ranking.PIX})
    linhas.append({"autor": "BANCADA DE MINAS", "ano_mes": f"{HOJE.year}06", "pago": 1.8e10, "tipo": "Bancada"})
    for v in ranking.VARIANTES:
        f = ranking.fato(v, linhas, cad)
        assert f, v
        f["nota"] = 99
        p = redacao.montar(f, True)
        assert not p["erros"], (v, p["erros"])
        assert redacao._tam(p["corpo_sem_link"]) <= 280, v


def test_ironia_dinamarca_nunca_em_emenda_recebida():
    d = {"idhm": 0.76, "agua": 99, "esgoto": 94.7}
    txt = municipio.comentario({"municipio": "Sete Lagoas", "uf": "MG", "tipo": "emenda_pagamento", "id": "x"}, d, 239833)
    assert "Dinamarca" not in txt and "gastar" not in txt


def test_bancos_de_comentario_sem_acusacao_nem_numero_nem_servidor():
    proibidas = re.compile(r"corrup|desvi|roub|superfatur|propina|ladr|crime|fraud|servidor", re.IGNORECASE)
    for tipo, frases in redacao.COMENTARIOS.items():
        for fr in frases:
            assert not proibidas.search(fr), (tipo, fr)
            assert not re.search(r"\d", fr), (tipo, fr)


def test_primeiro_comentario_cabe_e_mantem_fonte():
    t = municipio.comentario({"municipio": "Santo Antônio dos Lopes", "uf": "MA", "tipo": "show", "id": "a"},
                             {"idhm": 0.566, "agua": 78.38, "esgoto": 12.66, "precario": 66.33}, 14632, (58.2, 2.6, 57), "2022–2024")
    item = "🧾 Item: Contratação de show do artista Fulano. 1 unidade a R$ 500.000,00 cada (estimado)"
    sufixo = "\n\nFonte oficial:\nhttps://pncp.gov.br/app/contratos/12356879000198/2026/111"
    r = publicar._caber(item + "\n" + t, sufixo)
    assert publicar._tam_x(r + sufixo) <= 280
    assert r.startswith("🧾") and ("(IBGE, Censo 2022)" in r) == any(s in r for s in ("🚽", "💩", "🚱"))


# ---------- fila do Buffer ----------

def test_post_de_formato_antigo_na_fila_e_removido():
    assert fila.antigo({"status": "scheduled", "text": "PREFEITURA X PAGA R$ 1 MI EM SHOW\n#política"})
    assert not fila.antigo({"status": "scheduled", "text": "X CONTRATA SHOW\n#GastoPublico"})
    assert not fila.antigo({"status": "sent", "text": "antigo sem marca"})


# ---------- revisão independente (27/11) ----------

@pytest.mark.parametrize("obj,forn,esperado", [
    ("show do cantor Wesley Safadão para o evento “Carnaval 2027”", "", "Wesley Safadão"),
    ("internet banda larga para o programa “Conecta Escola”", "", ""),
    ("festejos de São João com atrações", "SAO JOAO EVENTOS LTDA", ""),
    ("Festa da Cidade com show", "CIDADE EVENTOS LTDA", ""),
    ("show do cantor TIERRY NO EVENTO DO ANIVERSÁRIO DE 50 ANOS DO MUNICÍPIO", "", "TIERRY"),
    ("APRESENTAÇÃO MUSICAL DO ARTISTA GUSTTAVO LIMA E BANDA, PARA O ANIVERSÁRIO", "", "GUSTTAVO LIMA"),
    ("show da banda Roupa Nova e do cantor Zé Neto", "", ""),
    ("Show do cantor Xand Avião. Valor: R$ 500 mil", "", "Xand Avião"),
    ("shows das bandas Calcinha Preta, Mastruz com Leite e Limão com Mel", "", ""),
    ("SHOW ARTÍSTICO COM A DUPLA “DIEGO E ARNALDO”, ARTISTAS DE RENOME NACIONAL", "", "DIEGO E ARNALDO"),
])
def test_artista(obj, forn, esperado):
    assert shows.artista(obj, forn) == esperado


@pytest.mark.parametrize("obj", ["Contratação de internet banda larga", "Show pirotécnico de fogos no réveillon",
                                 "Uniformes para banda marcial", "Cachê para palestrantes do seminário"])
def test_falsos_shows(obj):
    assert "show" not in tipos(obj)


def test_aviso_de_licitacao_nao_e_publicidade():
    assert "midia" not in tipos("Veiculação de avisos de licitação em jornais de grande circulação", valor=400_000)


@pytest.mark.parametrize("obj", ["Gêneros alimentícios: vinagre de vinho, camarão seco", "Detergente neutro espumante",
                                 "Locação de helicóptero para transporte aeromédico", "Cadeiras cor vinho para o auditório"])
def test_falsas_inusitadas(obj):
    assert "inusitada" not in tipos(obj, valor=300_000)


def test_pix_fala_dos_12_meses_nao_de_um_mes():
    f = dict(_show(), pix={"autor": "Dep. Fulano (PX-BA)", "total": 500_000, "mes": "202605"}, sem_esgoto=71)
    t = redacao._linha_pix(f)
    assert "últimos 12 meses" in t and "maio" not in t and "sem finalidade" not in t


def test_camara_municipal_nao_e_prefeitura():
    assert not redacao.eh_prefeitura("CAMARA MUNICIPAL DE PARANAIBA")
    assert not redacao.eh_prefeitura("CONSORCIO INTERMUNICIPAL DE SAUDE")
    assert redacao.eh_prefeitura("MUNICIPIO DE SERTAOZINHO") and redacao.eh_prefeitura("PREFEITURA MUNICIPAL DE X")
    f = dict(_show(), tipo="midia", orgao="CAMARA MUNICIPAL DE X", por_habitante=50)
    assert redacao._ingresso(f) == ""


def test_comentario_de_show_nao_fala_de_prefeitura_quando_nao_e():
    for i in range(40):
        f = dict(_show(), orgao="GOVERNO DO ESTADO DE X", id=f"id{i}")
        assert "prefeitura" not in redacao._comentario_banco(f).lower()


def test_manchete_com_paga_e_bloqueada():
    f = _show()
    assert redacao.checar(f, "PREFEITURA DE X (MG) PAGA R$ 500 MIL EM SHOW DE FULANO", "")


def test_bancos_sem_pagou():
    for frases in list(redacao.COMENTARIOS.values()) + list(redacao.INGRESSO.values()):
        for fr in frases:
            assert not re.search(r"\bpagou\b|paga a entrada|j[áa] pag", fr, re.IGNORECASE), fr


def test_sem_dono_e_so_bancada_comissao_relator():
    cad = {f"P{i}": {"nome": "X", "cargo": "Dep.", "partido": "PL", "uf": "MG"} for i in range(5)}
    linhas = [{"autor": "P1", "ano_mes": "202606", "pago": 1e6, "tipo": "Emenda Individual"},
              {"autor": "EX DEPUTADO FORA DO CADASTRO", "ano_mes": "202606", "pago": 5e9, "tipo": "Emenda Individual"},
              {"autor": "BANCADA DE MG", "ano_mes": "202606", "pago": 2e9, "tipo": "Emenda de Bancada"}]
    _, _, sem_dono, _ = ranking._somas(linhas, cad, "2026")
    assert sem_dono == 2e9


def test_homicidio_cidade_pequena_nao_aparece():
    t = municipio.comentario({"municipio": "Vilarejo", "uf": "MG", "tipo": "show", "id": "a"}, {}, 2000,
                             (83.0, 4.0, 5), "2022–2024")
    assert "🔪" not in t


def test_ironia_sem_causalidade():
    for frases in municipio.IRONIA.values():
        for fr in frases:
            assert not re.search(r"sobr|resolvid|prioridade", fr, re.IGNORECASE), fr


def test_post_novo_sem_hashtag_nao_e_apagado_da_fila():
    assert not fila.antigo({"status": "scheduled", "text": "X CONTRATA SHOW", "createdAt": "2026-12-01T10:00:00Z"})


def test_valor_da_manchete_do_ranking():
    assert ranking._vm(300_000) == "R$ 300 MIL" and ranking._vm(1.5e6) == "R$ 1,5 MILHÃO"


# ---------- teste integrado (27/11): casos reais ----------

def test_post_com_pix_nao_e_bloqueado_pelo_numero_12():
    f = dict(_show(), artista="Encantus", orgao="MUNICIPIO DE CORONEL JOAO PESSOA", sem_esgoto=96.6,
             pix={"autor": "Dep. Robinson Faria (PP-RN)", "total": 398_000, "mes": "202606"})
    p = redacao.montar(f, True)
    assert not p["erros"], p["erros"]
    assert "emenda Pix" in p["corpo_sem_link"] and redacao._tam(p["corpo_sem_link"]) <= 280


def test_floreal_dupla_de_renome_nacional():
    obj = ("Contratação de Empresa especializada na realização de SHOW MUSICAL - ARTÍSTICO – COM A DUPLA DE RENOME "
           "NACIONAL - DIEGO & ARNALDO, que acontecerá no dia 28 de Novembro de 2026")
    assert shows.artista(obj, "") == "DIEGO & ARNALDO"


def test_linha_do_item_sem_palavra_cortada_nem_unidade_abreviada():
    it = itens._resumo({"descricao": "Serviços artísticos, de Atração Musical para apresentação durante os festejos da "
                                     "Emancipação Política", "quantidade": 1, "unidadeMedida": "ser",
                        "valorUnitarioEstimado": 750000, "valorTotal": 750000})
    t = itens.linha(it)
    assert "1 ser " not in t and t.endswith("(estimado: R$ 750.000,00)") and " os f." not in t


def test_esgoto_nao_repete_no_comentario_quando_esta_no_post():
    f = {"municipio": "Coronel João Pessoa", "uf": "RN", "tipo": "show", "id": "a", "orgao": "MUNICIPIO DE X",
         "pix": {"total": 1}, "sem_esgoto": 96.6}
    t = municipio.comentario(f, {"idhm": 0.578, "agua": 32.6, "esgoto": 3.4, "precario": 82.9}, 4279)
    assert "🚽" not in t and "💩" in t


# ---------- portão final e agendamento da véspera ----------

def _show_real():
    f = shows.fatos(contrato("Contratação da Banda Barões da Pisadinha, para apresentação musical", valor=400_000,
                             fornecedor="BAROES DA PISADINHA PRODUCAO MUSICAL LTDA"))
    f["orgao"] = "MUNICIPIO DE CIDADE X"
    return f


def test_portao_final_aprova_post_correto():
    f = _show_real()
    assert f["artista"] and qa.conferencia_final(f, redacao.montar(f)) == []


def test_portao_final_barra_valor_link_artista_e_data_errados():
    f = _show_real()
    post = redacao.montar(f)
    assert "link não corresponde ao contrato" in qa.conferencia_final(f, dict(post, link="https://pncp.gov.br/app/contratos/99999999000199/2026/7"))
    assert "valor da manchete não confere com o contrato" in qa.conferencia_final(dict(f, valor=900_000), post)
    assert "artista não aparece no contrato" in qa.conferencia_final(dict(f, artista="Wesley Safadão"), post)
    assert any("data" in e for e in qa.conferencia_final(dict(f, data_assinatura="01/01/2024"), post))
    assert "item da compra não confirmado no PNCP" in qa.conferencia_final(dict(f, tipo="inusitada"), post)


def test_rodada_da_noite_prepara_o_dia_seguinte():
    brt = main.BRT
    assert main.dia_de_publicacao(datetime(2026, 11, 27, 21, 30, tzinfo=brt)) == "2026-11-28"
    assert main.dia_de_publicacao(datetime(2026, 11, 28, 7, 7, tzinfo=brt)) == "2026-11-28"
    slots = publicar.horarios(10, agora=datetime(2026, 11, 27, 21, 40, tzinfo=brt), dia="2026-11-28")
    assert slots[0].strftime("%d %H:%M") == "28 08:00" and all(s.day == 28 and s.hour <= 21 for s in slots)


def test_buffer_recusou_post_volta_a_concorrer(tmp_path, monkeypatch):
    import json
    from robo import publicar_pendentes as pp
    est = tmp_path / "dados" / "estado.json"
    est.parent.mkdir()
    est.write_text(json.dumps({"vistos": ["a", "b"], "pub_qtd": 2, "pub_cat": {"show": 2}, "shows_vistos": ["k"]}))
    monkeypatch.setattr(pp, "RAIZ", tmp_path)
    pp._devolver_falhas([{"id": "a", "categoria": "show", "chave_show": "k"}, {"id": "b", "categoria": "show"}],
                        [("t", "erro: limit"), ("t", "agendado 28/11 08:00")])
    e = json.loads(est.read_text())
    assert e["vistos"] == ["b"] and e["pub_qtd"] == 1 and e["pub_cat"]["show"] == 1 and e["shows_vistos"] == []


def test_oeiras_primeiro_comentario_cabe_contando_o_link_inteiro():
    # Buffer recusou: "Thread item 2 exceeds the 280 character limit" (link contado pelo tamanho real)
    dados = ("🧾 Item: CONTRATAÇÃO DA APRESENTAÇÃO ARTÍSTICA DA CANTORA MARA PAVANELLY, PARA… (estimado: R$ 200.000,00)\n"
             "📊 OEIRAS (PI)\n💩 51,6% despejam em fossa rudimentar, vala, rio ou não têm banheiro\n"
             "🚱 11,2% sem água da rede geral\n(IBGE, Censo 2022)\nIDHM 0,634, médio (PNUD, 2010)\nPopulação: 39.275 (IBGE)")
    fonte = "\n\nFonte oficial:\nhttps://pncp.gov.br/app/contratos/06553937000170/2026/96"
    r = publicar._caber(dados, fonte)
    assert len(r + fonte) + sum(1 for c in r if ord(c) > 0xFFFF) <= 280
