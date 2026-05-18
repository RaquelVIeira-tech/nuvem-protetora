"""
Testes do motor de análise de risco.

Rode com:  pytest -v
(estes testes não tocam em nenhum serviço de nuvem — custo zero)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from risk_engine import analyze, RiskCategory


def test_mensagem_vazia_e_segura():
    r = analyze("")
    assert r.score == 0
    assert r.category == RiskCategory.SEGURO


def test_mensagem_inofensiva_e_segura():
    r = analyze("Oi, vamos jogar bola depois da escola?")
    assert r.category == RiskCategory.SEGURO
    assert r.signals == []


def test_grooming_dispara_sinal():
    r = analyze("Isso fica como nosso segredo, não conta pra ninguém ok?")
    assert "grooming" in r.signals
    assert r.score >= 30


def test_sextorsao_e_critico():
    r = analyze(
        "Me manda uma foto sua sem roupa, se você não fizer vou espalhar"
    )
    assert "sextorsao" in r.signals
    assert r.category in (RiskCategory.ALERTA, RiskCategory.CRITICO)


def test_cyberbullying_detectado():
    r = analyze("ninguem gosta de voce, todo mundo te odeia")
    assert "cyberbullying" in r.signals
    assert r.score >= 25


def test_pedido_de_dados_pessoais():
    r = analyze("onde voce mora? qual sua escola?")
    assert "pedido_dados_pessoais" in r.signals


def test_resultado_nao_contem_texto_original():
    """Privacy by Design: o texto bruto nunca pode estar no resultado."""
    texto = "Me manda seu zap, isso fica entre a gente"
    r = analyze(texto)
    serializado = str(r.to_dict())
    assert texto not in serializado
    assert "zap" not in serializado.lower()
    # mas o hash deve estar presente, para rastreabilidade sem conteúdo
    assert len(r.message_hash) == 16


def test_sinais_externos_do_comprehend_aumentam_score():
    base = analyze("voce esta sozinho em casa?")
    com_comprehend = analyze(
        "voce esta sozinho em casa?",
        external_signals={
            "sentiment": "NEGATIVE",
            "sentiment_score_negative": 0.9,
            "pii_entities": ["ADDRESS"],
        },
    )
    assert com_comprehend.score > base.score


def test_acentuacao_nao_quebra_deteccao():
    """A normalização deve casar mesmo com acentos e maiúsculas."""
    r = analyze("NÃO CONTA pra ninguém, é segredo NOSSO")
    assert "grooming" in r.signals
