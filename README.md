# gasto-publico

Robô do @GastoPublicoBR. Uma vez por dia, puxa do PNCP os contratos de show/cachê acima de R$ 200 mil,
escreve o post (API do Grok), checa os números e grava em `saida/AAAAMMDD.md`.

- Publicação no X: desligada (`PUBLICAR: "false"`) até aprovar o formato.
- Parâmetros: `robo/config.py` (valor mínimo, posts por dia, comentário a cada N posts).
- Rodar na hora: aba **Actions** → "Robô diário – shows" → **Run workflow**.
- Segredo necessário: `XAI_KEY` (Settings → Secrets and variables → Actions). Sem ele, o robô usa a manchete padrão.

## Blocos do robô
1. **Shows** (PNCP): contratos de show/cachê acima de R$ 200 mil.
2. **Emendas Pix** (Transferegov): emenda nova, fora do estado, raio-X diário do parlamentar. *Bloqueado a partir do GitHub (403); migrar para a API do Portal da Transparência com `PORTAL_KEY`.*
3. **Cota parlamentar** (Câmara, arquivo anual oficial): maior gasto do dia, refeição acima de R$ 300, uso em fim de semana, fornecedor que atende 30+ gabinetes.
