# Docker Setup

## Build da imagem

```bash
docker build -t aracruz-bot .
```

## Executar

### Modo Webhook (Recomendado)

O container inicia um servidor HTTP que fica aguardando requisições:

```bash
docker run -d \
  -p 8080:8080 \
  -v $(pwd)/downloads:/app/downloads \
  -v $(pwd)/bot_profile:/app/bot_profile \
  --shm-size=2gb \
  --name aracruz-bot \
  aracruz-bot
```

**Endpoints disponíveis:**

- `POST /webhook` ou `GET /webhook` - Dispara a execução do bot
- `GET /health` - Verifica se o serviço está rodando

**Exemplo de uso:**

```bash
# Disparar execução via curl
curl http://localhost:8080/webhook

# Verificar saúde do serviço
curl http://localhost:8080/health
```

### Execução direta (sem webhook)

Se quiser executar diretamente sem servidor HTTP:

```bash
docker run --rm \
  -v $(pwd)/downloads:/app/downloads \
  -v $(pwd)/bot_profile:/app/bot_profile \
  --shm-size=2gb \
  aracruz-bot python acessar_pagina.py
```

### Integração com n8n

Configure um workflow no n8n com:
1. **Schedule Trigger** - a cada 12 horas
2. **HTTP Request** node - `POST http://seu-servidor:8080/webhook`
3. O bot executa e depois envia os dados para o webhook do n8n (já configurado)

## Volumes

- `./downloads` → `/app/downloads` - Planilhas baixadas e processadas
- `./bot_profile` → `/app/bot_profile` - Perfil do Chrome (cookies/sessão)

Os dados persistem no host mesmo após o container ser removido.
