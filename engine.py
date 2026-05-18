"""
Nuvem Protetora - Motor de Análise de Risco
=============================================

Núcleo da solução. Recebe uma mensagem de texto e devolve um indicador
de risco (score 0-100 + categoria), SEM armazenar o conteúdo bruto.

Este módulo é deliberadamente independente de qualquer serviço de nuvem.
- Na Fase 1 (demo, custo zero) ele roda sozinho, com heurísticas locais.
- Na Fase 2 (AWS) o Lambda chama o Amazon Comprehend para obter
  sentimento e entidades, e injeta esses sinais aqui via `external_signals`.

Princípio de projeto (Privacy by Design):
o texto entra, é analisado em memória, e só o RESULTADO sai.
Nenhuma função aqui escreve o conteúdo original em log ou disco.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class RiskCategory(str, Enum):
    """Categoria de risco identificada na mensagem."""

    SEGURO = "seguro"
    ATENCAO = "atencao"
    ALERTA = "alerta"
    CRITICO = "critico"


# ---------------------------------------------------------------------------
# Léxicos de risco
# ---------------------------------------------------------------------------
# IMPORTANTE: estas listas são propositalmente conservadoras e ilustrativas.
# Num produto real, esta camada evoluiria para um modelo treinado
# (o "SageMaker como fase futura" do diagrama de arquitetura). O objetivo
# aqui é demonstrar a MECÂNICA de scoring, não esgotar o vocabulário.

# Sinais associados a aliciamento (grooming): tentativa de isolar a
# criança, criar segredo, ou mover a conversa para canal privado.
GROOMING_PATTERNS = [
    r"\bnao\s+conta\b",
    r"\bnao\s+conte\b",
    r"\bsegredo\s+nosso\b",
    r"\bnosso\s+segredo\b",
    r"\bso\s+entre\s+nos\b",
    r"\bnao\s+fala\s+pros?\s+seus?\s+pais\b",
    r"\bnao\s+conta\s+pra\s+ninguem\b",
    r"\bvoce\s+e\s+madur[oa]\s+pra\s+sua\s+idade\b",
    r"\bquantos\s+anos\s+voce\s+tem\b",
    r"\bvamos\s+conversar\s+em\s+outro\s+app\b",
    r"\bme\s+manda\s+seu\s+(whats|numero|zap)\b",
    r"\bvoce\s+esta\s+sozinh[oa]\b",
    r"\bseus\s+pais\s+estao\s+em\s+casa\b",
    r"\bnao\s+precisa\s+contar\b",
]

# Sinais associados a sextorsão / pedido de conteúdo íntimo.
SEXTORTION_PATTERNS = [
    r"\bmanda\s+(uma\s+)?foto\s+sua\b",
    r"\bme\s+manda\s+(uma\s+)?foto\b",
    r"\bfoto\s+sem\s+roupa\b",
    r"\btira\s+a\s+roupa\b",
    r"\bse\s+voce\s+nao\s+(mandar|fizer)\b",
    r"\bvou\s+(mostrar|espalhar|postar)\b",
    r"\beu\s+tenho\s+suas?\s+fotos?\b",
    r"\bninguem\s+vai\s+saber\b",
    r"\bisso\s+fica\s+entre\s+a\s+gente\b",
]

# Sinais associados a cyberbullying / agressão direcionada.
BULLYING_PATTERNS = [
    r"\bninguem\s+gosta\s+de\s+voce\b",
    r"\bvoce\s+e\s+(burr[oa]|idiota|inutil|horrivel)\b",
    r"\bse\s+mata\b",
    r"\bvai\s+se\s+matar\b",
    r"\bvoce\s+devia\s+sumir\b",
    r"\btodo\s+mundo\s+te\s+odeia\b",
    r"\bvoce\s+e\s+um[a]?\s+(perdedor|fracass)",
    r"\bvolta\s+pra\s+casa\s+chorando\b",
]

# Pedidos de dados pessoais sensíveis (endereço, escola, rotina).
PII_REQUEST_PATTERNS = [
    r"\bonde\s+voce\s+mora\b",
    r"\bqual\s+sua\s+escola\b",
    r"\bque\s+horas?\s+voce\s+sai\s+da\s+escola\b",
    r"\bme\s+passa\s+seu\s+endereco\b",
    r"\bqual\s+seu\s+endereco\b",
    r"\bvoce\s+vai\s+estar\s+sozinh[oa]\s+onde\b",
]

# Cada grupo tem um peso. Sextorsão e grooming são os mais graves.
PATTERN_GROUPS = {
    "grooming": (GROOMING_PATTERNS, 30),
    "sextorsao": (SEXTORTION_PATTERNS, 40),
    "cyberbullying": (BULLYING_PATTERNS, 25),
    "pedido_dados_pessoais": (PII_REQUEST_PATTERNS, 20),
}


# ---------------------------------------------------------------------------
# Estrutura do resultado
# ---------------------------------------------------------------------------
@dataclass
class RiskResult:
    """
    Resultado da análise. É exatamente isto que pode ser armazenado
    ou trafegado — nunca o texto original.
    """

    score: int  # 0 a 100
    category: RiskCategory
    signals: list[str] = field(default_factory=list)  # tipos de risco achados
    message_hash: str = ""  # hash do texto, p/ deduplicação sem guardar conteúdo
    char_count: int = 0  # tamanho, útil p/ métricas, não revela conteúdo
    explanation: str = ""  # texto curto, amigável, p/ o app do responsável

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category"] = self.category.value
        return d


# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------
def _normalize(text: str) -> str:
    """
    Normaliza o texto para casar padrões de forma robusta:
    minúsculas, sem acento, espaços colapsados.
    Isto NÃO é armazenado — é uma cópia temporária em memória.
    """
    text = text.lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"\s+", " ", text)
    return text


def _hash_message(text: str) -> str:
    """
    Gera um hash SHA-256 do texto. Permite deduplicar/rastrear
    eventos sem nunca guardar o conteúdo. Privacy by Design na prática.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _category_for_score(score: int) -> RiskCategory:
    if score >= 70:
        return RiskCategory.CRITICO
    if score >= 45:
        return RiskCategory.ALERTA
    if score >= 20:
        return RiskCategory.ATENCAO
    return RiskCategory.SEGURO


_FRIENDLY = {
    RiskCategory.SEGURO: "Nenhum sinal de risco relevante nesta interação.",
    RiskCategory.ATENCAO: (
        "Pequenos sinais que valem acompanhamento. Pode ser um bom momento "
        "para uma conversa leve sobre segurança online."
    ),
    RiskCategory.ALERTA: (
        "Sinais consistentes de risco. Recomenda-se conversar com a "
        "criança ou adolescente e revisar com quem ela tem falado."
    ),
    RiskCategory.CRITICO: (
        "Sinais graves identificados. Considere agir imediatamente e, se "
        "necessário, acionar canais de denúncia (Disque 100)."
    ),
}


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------
def analyze(
    text: str,
    external_signals: Optional[dict] = None,
) -> RiskResult:
    """
    Analisa uma mensagem e devolve o indicador de risco.

    Parâmetros
    ----------
    text:
        A mensagem a analisar. Processada em memória; nunca persistida.
    external_signals:
        Opcional. Sinais vindos do Amazon Comprehend na Fase 2 AWS.
        Formato esperado (todos os campos opcionais):
            {
                "sentiment": "NEGATIVE" | "POSITIVE" | "NEUTRAL" | "MIXED",
                "sentiment_score_negative": float 0..1,
                "pii_entities": ["NAME", "ADDRESS", ...],
            }
        Quando ausente (Fase 1, demo local), a análise usa só heurísticas.

    Retorno
    -------
    RiskResult — apenas indicadores derivados, seguro para armazenar.
    """
    if not text or not text.strip():
        return RiskResult(
            score=0,
            category=RiskCategory.SEGURO,
            explanation=_FRIENDLY[RiskCategory.SEGURO],
        )

    normalized = _normalize(text)
    score = 0
    signals: list[str] = []

    # 1. Heurística por léxicos (sempre roda, Fase 1 e Fase 2)
    # Conta quantos padrões distintos casaram em cada grupo: vários
    # sinais do mesmo tipo (ex.: pedir foto + ameaçar espalhar) indicam
    # risco maior do que um único sinal isolado.
    for name, (patterns, weight) in PATTERN_GROUPS.items():
        matches = sum(1 for p in patterns if re.search(p, normalized))
        if matches:
            # primeiro match vale o peso cheio; cada match extra agrava
            score += weight + (matches - 1) * (weight // 2)
            signals.append(name)

    # 2. Sinais externos do Amazon Comprehend (só na Fase 2)
    if external_signals:
        sentiment = external_signals.get("sentiment")
        neg = float(external_signals.get("sentiment_score_negative", 0) or 0)
        if sentiment == "NEGATIVE" and neg >= 0.7:
            score += 15
            if "sentimento_muito_negativo" not in signals:
                signals.append("sentimento_muito_negativo")

        pii = external_signals.get("pii_entities") or []
        sensitive_pii = {"ADDRESS", "PHONE", "AGE", "NAME"}
        if any(p in sensitive_pii for p in pii):
            score += 10
            if "dados_pessoais_detectados" not in signals:
                signals.append("dados_pessoais_detectados")

    score = max(0, min(100, score))
    category = _category_for_score(score)

    return RiskResult(
        score=score,
        category=category,
        signals=signals,
        message_hash=_hash_message(text),
        char_count=len(text),
        explanation=_FRIENDLY[category],
    )
