# 🛡️ Nuvem Protetora

> IA pela segurança online de crianças e adolescentes.
> Projeto final do curso de Extensão em Inteligência Artificial — Escola da Nuvem.

O **Nuvem Protetora** é uma solução *serverless* e orientada a eventos que
analisa interações digitais em busca de sinais de **grooming**,
**sextorsão** e **cyberbullying**, alertando responsáveis de forma
**ética, preventiva e não invasiva** — sem armazenar o conteúdo das
mensagens, em conformidade com a **LGPD** e o **ECA**.

![Arquitetura](docs/arquitetura.png)

---

## ✨ Em duas fases

Este repositório está organizado para você evoluir sem ter gastos:

| | Fase 1 — Demo | Fase 2 — AWS |
|---|---|---|
| **Onde roda** | Navegador (`web/`) | AWS (Lambda + Comprehend) |
| **Custo** | Sempre zero | Projetada p/ Free Tier |
| **Prova** | O conceito e a UX | A arquitetura técnica |
| **O motor de risco** | `assets/engine.js` | `src/risk_engine/` (Python) |

A **lógica de detecção de risco é a mesma** nas duas fases — só muda
onde ela roda. Isso é proposital: a demo prova exatamente o
comportamento que o backend AWS terá.

---

## 🚀 Como rodar a Fase 1 (demo, custo zero)

Não precisa de AWS nem de instalar nada.

```bash
# clone o repositório
git clone https://github.com/SEU_USUARIO/nuvem-protetora.git
cd nuvem-protetora/web

# sirva localmente (qualquer servidor estático serve)
python3 -m http.server 8000
# abra http://localhost:8000
```

Ou publique grátis no **GitHub Pages**: em *Settings → Pages*, aponte
para a pasta `/web` na branch `main`. Em minutos você tem um link vivo
para colocar no portfólio.

### O que a demo mostra
- **App do Filho**: simula mensagens recebidas pela criança.
- **App do Responsável**: recebe apenas o *indicador de risco*
  (score, categoria, hash) — **nunca o texto**.
- Botões de exemplo para você testar cada tipo de risco.

---

## ☁️ Como rodar a Fase 2 (AWS) — opcional

⚠️ **Antes de qualquer coisa, leia [`docs/CUSTOS.md`](docs/CUSTOS.md)**
e configure o *billing alarm*. O template foi feito para caber no
Free Tier, mas o alarme é a sua rede de segurança.

```bash
# pré-requisitos: AWS CLI configurado + AWS SAM CLI
cd infra
sam build
sam deploy --guided \
  --parameter-overrides EmailResponsavel=seu-email@exemplo.com
```

O `sam deploy` mostra o endpoint da API ao final. Aponte a demo para
ele e a análise passa a usar o **Amazon Comprehend** de verdade.

### Testar o Lambda localmente (sem subir nada / sem custo)

```bash
python3 -c "from src.lambda.app import handler; \
print(handler({'message':'nao conta pra ninguem, e segredo nosso'}, None))"
```

O código *degrada com segurança*: sem credenciais AWS, ele pula
Comprehend/DynamoDB/SNS e ainda roda o motor de risco.

---

## 🧠 O motor de risco

O coração do projeto é [`src/risk_engine/engine.py`](src/risk_engine/engine.py).
Ele recebe um texto e devolve:

```python
{
  "score": 60,                    # 0 a 100
  "category": "alerta",           # seguro | atencao | alerta | critico
  "signals": ["grooming"],        # tipos de risco encontrados
  "message_hash": "5a0259d63c63", # rastreabilidade SEM guardar conteúdo
  "char_count": 52,
  "explanation": "Sinais consistentes de risco..."
}
```

**Privacy by Design na prática:** o texto é analisado em memória e o
resultado *nunca* contém o conteúdo original — só indicadores
derivados. Há um teste que garante exatamente isso.

> Nota de honestidade técnica: o Amazon Comprehend faz sentimento e
> detecção de PII em português, mas **não tem um modelo pronto para
> "grooming" ou "sextorsão"**. Essa detecção é uma camada de regras e
> *scoring* construída neste projeto. Evoluí-la para um modelo treinado
> é o *"SageMaker como fase futura"* do diagrama de arquitetura.

---

## ✅ Testes

```bash
pip install -r requirements-dev.txt
pytest -v
```

Os testes não tocam em nenhum serviço de nuvem — custo zero.

---

## 📁 Estrutura

```
nuvem-protetora/
├── web/                  Fase 1 — demo (custo zero)
│   ├── index.html
│   └── assets/engine.js  motor de risco em JS
├── src/
│   ├── risk_engine/      motor de risco em Python (compartilhado)
│   └── lambda/app.py     Fase 2 — handler AWS
├── infra/template.yaml   infraestrutura como código (AWS SAM)
├── tests/                testes do motor
└── docs/
    ├── CUSTOS.md          como manter custo zero
    ├── arquitetura.png    diagrama da solução
    └── Projeto_Nuvem_Protetora_Final.docx
```

---

## 🗺️ Próximos passos (do documento original)

- Evolução do modelo de IA (camada de regras → modelo treinado / SageMaker).
- Integração com APIs oficiais de plataformas digitais.
- Ampliação do módulo educativo gamificado.

---

## ⚖️ Aviso

Este é um **protótipo acadêmico**. Os léxicos de detecção são
ilustrativos e propositalmente conservadores — não substituem
ferramentas profissionais de proteção infantil. Em situação real de
risco, procure o **Disque 100**.
