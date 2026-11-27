"""Erros que já aconteceram de verdade. Cada um vira teste: se voltar, o robô não publica.

Rodar: python -m pytest -q tests
"""
import re
from datetime import date, timedelta

import pytest

import robo.main  # noqa: F401  (import quebrado = rodada quebrada: ex. variável 'ranking' escondendo o módulo)
from robo import (emendas, emendas_portal, fila, itens, municipio, outros_pncp, posts_emendas, publicar, ranking,
                  redacao, shows)

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


# ---------- emendas ----------

def test_banco_do_brasil_nao_e_destino_de_emenda():
    linha = {"codigo": "1", "ano": "2024", "autor": "FULANO", "municipio": "", "localidade": "", "uf": "DF",
             "pago": 1e6, "favorecido": "BANCO DO BRASIL SA", "cod_favorecido": "x", "ano_mes": "202401", "funcao": ""}
    p = emendas_portal.para_planos([linha])[0]
    assert p["uf_destino"] == "" and p["beneficiario"] == ""
    assert posts_emendas.fatos_pagamento(dict(linha, delta=1e6), {"FULANO": {"uf": "RJ"}}) is None


# ---------- texto ----------

def _show():
    return {"tipo": "show", "id": "x", "valor_manchete": "R$ 500 MIL", "link": "https://pncp.gov.br/app/contratos/1/2026/1",
            "orgao": "MUNICIPIO DE CIDADE X", "municipio": "Cidade X", "uf": "MG", "valor": 500000,
            "valor_exato": "R$ 500.000,00", "fornecedor": "F", "data_assinatura": "20/11/2026", "artista": "Fulano",
            "objeto": "show", "inclui_estrutura": False}


def test_contrato_nao_e_pagamento():
    p = redacao.montar(_show(), True)
    assert " PAGA " not in p["corpo_sem_link"] and "CONTRATA" in p["corpo_sem_link"]


def test_link_vai_no_primeiro_comentario():
    p = redacao.montar(_show(), True)
    assert p["variante_link"] == "resposta" and "http" not in p["corpo_sem_link"]


def test_raio_x_longo_cabe_em_280():
    rx = {"nome": "Flávio Bolsonaro", "cargo": "Sen.", "partido": "REPUBLICANOS", "uf": "RJ", "total": 224.98e6,
          "qtd": 50, "destinos": 10, "fora_do_estado": 44,
          "top": [{"destino": "SAO JOAO DE MERITI", "uf": "RJ", "valor": 36.35e6}],
          "por_ano": {"2020": 7.58e6, "2026": 51.67e6}}
    f = posts_emendas.post_raio_x(rx)
    f["nota"] = 99
    p = redacao.montar(f, True)
    assert redacao._tam(p["corpo_sem_link"]) <= 280


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
