/*
 * Nuvem Protetora - Motor de Risco (versão JavaScript)
 * ====================================================
 * Espelho fiel de src/risk_engine/engine.py, para rodar 100% no
 * navegador na Fase 1 (demo, custo zero, sem AWS).
 *
 * A lógica de scoring é idêntica à do Python de propósito: assim a
 * demo prova exatamente o mesmo comportamento que o Lambda terá
 * na Fase 2. Privacy by Design: o texto é analisado em memória e
 * só o RESULTADO é retornado.
 */

const GROOMING_PATTERNS = [
  /\bnao\s+conta\b/, /\bnao\s+conte\b/, /\bsegredo\s+nosso\b/,
  /\bnosso\s+segredo\b/, /\bso\s+entre\s+nos\b/,
  /\bnao\s+fala\s+pros?\s+seus?\s+pais\b/, /\bnao\s+conta\s+pra\s+ninguem\b/,
  /\bvoce\s+e\s+madur[oa]\s+pra\s+sua\s+idade\b/,
  /\bquantos\s+anos\s+voce\s+tem\b/,
  /\bvamos\s+conversar\s+em\s+outro\s+app\b/,
  /\bme\s+manda\s+seu\s+(whats|numero|zap)\b/,
  /\bvoce\s+esta\s+sozinh[oa]\b/, /\bseus\s+pais\s+estao\s+em\s+casa\b/,
  /\bnao\s+precisa\s+contar\b/,
];

const SEXTORTION_PATTERNS = [
  /\bmanda\s+(uma\s+)?foto\s+sua\b/, /\bme\s+manda\s+(uma\s+)?foto\b/,
  /\bfoto\s+sem\s+roupa\b/, /\btira\s+a\s+roupa\b/,
  /\bse\s+voce\s+nao\s+(mandar|fizer)\b/,
  /\bvou\s+(mostrar|espalhar|postar)\b/,
  /\beu\s+tenho\s+suas?\s+fotos?\b/, /\bninguem\s+vai\s+saber\b/,
  /\bisso\s+fica\s+entre\s+a\s+gente\b/,
];

const BULLYING_PATTERNS = [
  /\bninguem\s+gosta\s+de\s+voce\b/,
  /\bvoce\s+e\s+(burr[oa]|idiota|inutil|horrivel)\b/,
  /\bse\s+mata\b/, /\bvai\s+se\s+matar\b/, /\bvoce\s+devia\s+sumir\b/,
  /\btodo\s+mundo\s+te\s+odeia\b/,
  /\bvoce\s+e\s+um[a]?\s+(perdedor|fracass)/,
  /\bvolta\s+pra\s+casa\s+chorando\b/,
];

const PII_REQUEST_PATTERNS = [
  /\bonde\s+voce\s+mora\b/, /\bqual\s+sua\s+escola\b/,
  /\bque\s+horas?\s+voce\s+sai\s+da\s+escola\b/,
  /\bme\s+passa\s+seu\s+endereco\b/, /\bqual\s+seu\s+endereco\b/,
  /\bvoce\s+vai\s+estar\s+sozinh[oa]\s+onde\b/,
];

const PATTERN_GROUPS = {
  grooming: [GROOMING_PATTERNS, 30],
  sextorsao: [SEXTORTION_PATTERNS, 40],
  cyberbullying: [BULLYING_PATTERNS, 25],
  pedido_dados_pessoais: [PII_REQUEST_PATTERNS, 20],
};

const FRIENDLY = {
  seguro: "Nenhum sinal de risco relevante nesta interação.",
  atencao: "Pequenos sinais que valem acompanhamento. Pode ser um bom momento para uma conversa leve sobre segurança online.",
  alerta: "Sinais consistentes de risco. Recomenda-se conversar com a criança ou adolescente e revisar com quem ela tem falado.",
  critico: "Sinais graves identificados. Considere agir imediatamente e, se necessário, acionar canais de denúncia (Disque 100).",
};

function normalize(text) {
  return text
    .toLowerCase()
    .trim()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ");
}

async function hashMessage(text) {
  // SHA-256 nativo do navegador, sem bibliotecas externas
  const data = new TextEncoder().encode(text);
  const buf = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 16);
}

function categoryForScore(score) {
  if (score >= 70) return "critico";
  if (score >= 45) return "alerta";
  if (score >= 20) return "atencao";
  return "seguro";
}

async function analyze(text, externalSignals = null) {
  if (!text || !text.trim()) {
    return {
      score: 0, category: "seguro", signals: [],
      message_hash: "", char_count: 0, explanation: FRIENDLY.seguro,
    };
  }

  const normalized = normalize(text);
  let score = 0;
  const signals = [];

  for (const name in PATTERN_GROUPS) {
    const [patterns, weight] = PATTERN_GROUPS[name];
    const matches = patterns.filter((p) => p.test(normalized)).length;
    if (matches) {
      score += weight + (matches - 1) * Math.floor(weight / 2);
      signals.push(name);
    }
  }

  if (externalSignals) {
    const neg = parseFloat(externalSignals.sentiment_score_negative || 0);
    if (externalSignals.sentiment === "NEGATIVE" && neg >= 0.7) {
      score += 15;
      signals.push("sentimento_muito_negativo");
    }
    const pii = externalSignals.pii_entities || [];
    const sensitive = ["ADDRESS", "PHONE", "AGE", "NAME"];
    if (pii.some((p) => sensitive.includes(p))) {
      score += 10;
      signals.push("dados_pessoais_detectados");
    }
  }

  score = Math.max(0, Math.min(100, score));
  const category = categoryForScore(score);

  return {
    score,
    category,
    signals,
    message_hash: await hashMessage(text),
    char_count: text.length,
    explanation: FRIENDLY[category],
  };
}

window.NuvemProtetora = { analyze };
