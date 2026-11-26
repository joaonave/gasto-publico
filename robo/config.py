"""Parâmetros do robô. Ajuste aqui, sem mexer no resto do código."""

# Gatilho: shows e cachês
PALAVRAS_SHOW = [
    r"\bshows?\b",
    r"apresenta[çc][ãa]o art[ií]stica",
    r"(servi[çc]os?|profissional|profissionais|atra[çc][ãa]o|atra[çc][õo]es) art[ií]stic",
    r"apresenta[çc][ãa]o musical",
    r"cach[êe]",
    r"banda\b",
    r"cantor[a]?\b",
    r"dupla sertaneja",
]
# Objetos que não são cachê de artista (falsos positivos)
PALAVRAS_EXCLUIR = [r"patroc[ií]nio", r"boat show", r"auto show", r"show ?room", r"agro ?show",
                    r"restaura[çc]", r"\bobras?\b", r"reforma", r"constru[çc]", r"pavimenta",
                    r"aquisi[çc][ãa]o de", r"material", r"equipamento", r"instrumentos? musica"]

# Objetos que incluem estrutura (palco, som, etc.) não são cachê puro
PALAVRAS_ESTRUTURA = [r"\bpalco", r"sonoriza", r"ilumina", r"\btenda", r"gerador", r"estrutura"]

VALOR_MINIMO = 200_000  # R$
IDADE_MAX_DIAS = 90     # só posta contratos assinados nos últimos N dias

# Tom: 1 post a cada N leva comentário de "desiludido"
COMENTARIO_A_CADA = 4

# Máximo de posts por execução (o resto fica para o dia seguinte, por ordem de valor)
MAX_POSTS_DIA = 5

# PNCP
PNCP_BASE = "https://pncp.gov.br/api/consulta/v1/contratos"
PNCP_PAUSA_SEG = 3
PNCP_ESPERA_429_SEG = 30
PNCP_TENTATIVAS = 4
PNCP_TAMANHOS_PAGINA = [500, 100, 50]  # tenta o maior; se a API recusar, reduz

# xAI
XAI_URL = "https://api.x.ai/v1/chat/completions"
XAI_MODELO = "grok-4.3"
