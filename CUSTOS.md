# Guia de Custos — como manter o projeto em custo zero

Este projeto foi desenhado para **não gerar gastos** num cenário de
protótipo. Esta página explica por quê e o que fazer para garantir isso.

## Fase 1 (demo web) — custo SEMPRE zero

A demo em `web/` roda inteiramente no navegador. Não há servidor, não
há AWS, não há nada para pagar. Você pode publicar de graça no
**GitHub Pages** (ver `README.md`).

## Fase 2 (AWS) — projetada para caber no Free Tier

Você só tem custo na Fase 2 se fizer o deploy na AWS. Mesmo assim, o
template foi escrito para ficar dentro dos limites gratuitos:

| Serviço | Free Tier | Uso de um protótipo |
|---|---|---|
| AWS Lambda | 1 milhão de requisições/mês (sempre grátis) | dezenas/centenas |
| Amazon Comprehend | 50.000 unidades/mês (12 meses) | muito abaixo |
| Amazon DynamoDB | 25 GB + on-demand no free tier | alguns KB |
| Amazon SNS | 1 milhão de publicações/mês (sempre grátis) | pouquíssimas |
| API Gateway | 1 milhão de chamadas/mês (12 meses) | dezenas |

> Cada análise faz ~2 chamadas ao Comprehend. Mesmo testando
> milhares de mensagens, você fica longe do limite de 50.000.

As escolhas do `template.yaml` que ajudam a manter custo zero:
- DynamoDB em `PAY_PER_REQUEST` (sem cobrança por capacidade ociosa).
- Lambda com `MemorySize: 256` (menor custo por execução).
- Nenhum recurso "always-on" (sem EC2, sem NAT Gateway, sem RDS).

## Passo obrigatório antes de qualquer deploy: Billing Alarm

Configure um alarme de cobrança de **US$ 0,01** para ser avisado ao
primeiro centavo. Pelo console:

1. Acesse **Billing → Billing preferences** e ative
   *Receive Billing Alerts*.
2. Vá em **CloudWatch → Alarms → Create alarm**.
3. Métrica: **Billing → Total Estimated Charge → USD**.
4. Condição: *Greater than* `0.01`.
5. Crie um tópico SNS com seu e-mail e confirme a inscrição.

Assim, se qualquer coisa fugir do free tier, você recebe um e-mail
antes de a conta crescer.

## Como NÃO ter custo enquanto desenvolve a Fase 2

Você pode testar o Lambda **localmente**, sem subir nada:

```bash
# instala o motor para teste local
pip install -r requirements-dev.txt

# testa o handler sem AWS (Comprehend é ignorado se boto3 não achar credenciais)
python -c "from src.lambda.app import handler; \
import json; print(handler({'message':'nao conta pra ninguem, e segredo nosso'}, None))"
```

O `app.py` foi escrito para **degradar com segurança**: se o boto3 não
estiver configurado, ele pula Comprehend/DynamoDB/SNS e ainda assim
roda o motor de risco. Ou seja, dá para validar quase tudo sem AWS.

## Como remover tudo (e zerar qualquer custo futuro)

Quando terminar de demonstrar:

```bash
sam delete --stack-name nuvem-protetora
```

Isso apaga Lambda, DynamoDB, SNS e API Gateway. Nada continua rodando.
