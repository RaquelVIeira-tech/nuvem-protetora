"""
Nuvem Protetora - Lambda Handler (Fase 2, AWS)
===============================================

Este é o "Processamento / AWS Lambda (Backend)" do diagrama de arquitetura.

Fluxo:
  API Gateway  ->  este Lambda  ->  Amazon Comprehend (sentimento + PII)
                                ->  risk_engine.analyze()
                                ->  DynamoDB (grava SÓ o indicador)
                                ->  SNS (notifica responsável se risco alto)

Privacy by Design: o texto recebido é usado em memória para a análise e
NUNCA é gravado no DynamoDB nem publicado no SNS. Só sai daqui o score,
a categoria, o hash e os sinais.

ATENÇÃO A CUSTOS:
  - Comprehend free tier: 50K unidades/mês (12 meses). Cada chamada
    abaixo são 2 unidades por mensagem (~até 200 chars).
  - Lambda: 1M req/mês grátis sempre.
  - DynamoDB: 25GB + on-demand dentro do free tier.
  - SNS: 1M publicações/mês grátis.
  Um protótipo de demonstração fica MUITO abaixo desses limites.
  Ainda assim, configure um billing alarm (ver docs/CUSTOS.md).
"""

import json
import os
import sys
import time

# Permite reusar o mesmo motor da Fase 1 (camada Lambda ou pasta empacotada)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "risk_engine"))
sys.path.insert(0, os.path.dirname(__file__))

try:
    import boto3
except ImportError:  # boto3 já existe no runtime do Lambda; local pode faltar
    boto3 = None

from engine import analyze  # noqa: E402  (mesmo arquivo da Fase 1)


# Variáveis de ambiente definidas no template SAM (infra/template.yaml)
TABLE_NAME = os.environ.get("TABLE_NAME", "NuvemProtetoraEventos")
TOPIC_ARN = os.environ.get("TOPIC_ARN", "")
NOTIFY_FROM_CATEGORY = os.environ.get("NOTIFY_FROM", "alerta")

# Categorias ordenadas por gravidade, para decidir quando notificar
_ORDER = {"seguro": 0, "atencao": 1, "alerta": 2, "critico": 3}


def _comprehend_signals(text: str) -> dict:
    """
    Chama o Amazon Comprehend para enriquecer a análise com
    sentimento e detecção de PII em português.
    Retorna o dicionário no formato que risk_engine.analyze espera.
    """
    if boto3 is None:
        return {}

    client = boto3.client("comprehend")
    signals = {}

    try:
        sent = client.detect_sentiment(Text=text, LanguageCode="pt")
        signals["sentiment"] = sent.get("Sentiment")
        scores = sent.get("SentimentScore", {})
        signals["sentiment_score_negative"] = scores.get("Negative", 0.0)
    except Exception as exc:  # nunca derruba o fluxo por causa do Comprehend
        print(f"[warn] detect_sentiment falhou: {exc}")

    try:
        pii = client.detect_pii_entities(Text=text, LanguageCode="pt")
        signals["pii_entities"] = [
            e.get("Type") for e in pii.get("Entities", [])
        ]
    except Exception as exc:
        print(f"[warn] detect_pii_entities falhou: {exc}")

    return signals


def _persist(result_dict: dict) -> None:
    """Grava SOMENTE o indicador no DynamoDB. Nunca o texto."""
    if boto3 is None:
        return
    table = boto3.resource("dynamodb").Table(TABLE_NAME)
    item = {
        "evento_id": result_dict["message_hash"] or str(time.time()),
        "timestamp": int(time.time()),
        "score": result_dict["score"],
        "category": result_dict["category"],
        "signals": result_dict["signals"],
        "char_count": result_dict["char_count"],
        # repare: NÃO existe campo com o conteúdo da mensagem
    }
    table.put_item(Item=item)


def _notify(result_dict: dict) -> None:
    """Publica um alerta no SNS se o risco for relevante."""
    if boto3 is None or not TOPIC_ARN:
        return
    if _ORDER.get(result_dict["category"], 0) < _ORDER.get(NOTIFY_FROM_CATEGORY, 2):
        return
    sns = boto3.client("sns")
    sns.publish(
        TopicArn=TOPIC_ARN,
        Subject="Nuvem Protetora - Alerta de seguranca",
        Message=(
            f"Categoria: {result_dict['category'].upper()}\n"
            f"Score: {result_dict['score']}/100\n"
            f"Sinais: {', '.join(result_dict['signals']) or 'nenhum'}\n"
            f"Evento: {result_dict['message_hash']}\n\n"
            f"{result_dict['explanation']}\n\n"
            "Nenhum conteudo de mensagem foi armazenado."
        ),
    )


def handler(event, context):
    """
    Ponto de entrada do Lambda (configurado pelo API Gateway).
    Espera um corpo JSON: {"message": "texto a analisar"}
    """
    try:
        body = event.get("body")
        if isinstance(body, str):
            body = json.loads(body or "{}")
        elif body is None:
            body = event  # invocação direta (teste)
        text = (body or {}).get("message", "")
    except (ValueError, AttributeError):
        return _response(400, {"error": "JSON invalido"})

    if not text or not text.strip():
        return _response(400, {"error": "campo 'message' obrigatorio"})

    # 1. Enriquecimento via Comprehend (Fase 2)
    external = _comprehend_signals(text)

    # 2. Mesma lógica de risco da Fase 1
    result = analyze(text, external_signals=external)
    result_dict = result.to_dict()

    # 3. Persistir só o indicador + 4. Notificar se necessário
    try:
        _persist(result_dict)
        _notify(result_dict)
    except Exception as exc:
        print(f"[warn] persistencia/notificacao falhou: {exc}")

    # 5. Devolver o indicador para o app (sem eco do texto)
    return _response(200, result_dict)


def _response(status: int, payload: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(payload, ensure_ascii=False),
    }
