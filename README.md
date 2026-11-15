# GPT Decision API

A small, production-style example of using **GPT as a decision engine**: send case data, get back a **structured, auditable decision** that your systems can act on.

It covers three banking applications:

| Use case | Endpoint | Possible decisions |
|---|---|---|
| Consumer loan pre-screening | `POST /decide/loan_triage` | `approve` · `decline` · `refer_to_underwriter` |
| Payment fraud screening | `POST /decide/fraud_screening` | `allow` · `block` · `step_up_auth` · `manual_review` |
| Support ticket routing | `POST /decide/ticket_routing` | `billing` · `technical` · `account_security` · `complaints` · `human_triage` |

## Why a "decision API"?

Chat output is free text. Business systems need a **fixed set of outcomes**, a **confidence score**, **reasons**, and a **trail** for auditors. This project shows how to get that safely:

```text
            ┌──────────────┐   forced     ┌────────────────────┐
 request ──▶│  Hard rules  │─────────────▶│                    │
            │ (code, not   │  escalation  │                    │
            │  the model)  │              │                    │
            └──────┬───────┘              │                    │
                   │ pass                 │                    │
            ┌──────▼───────┐              │   DecisionResponse │
            │ GPT with     │              │   + audit log      │
            │ Structured   │─────────────▶│                    │
            │ Outputs      │              │                    │
            └──────┬───────┘              │                    │
                   │ confidence < 0.75    │                    │
            ┌──────▼───────┐              │                    │
            │  Guardrail:  │─────────────▶│                    │
            │  escalate to │              │                    │
            │  a human     │              └────────────────────┘
            └──────────────┘
```

1. **Hard rules first.** Non-negotiable policies (sanctioned countries, loan amount caps) run in code before the model is called. GPT can never override them.
2. **Structured Outputs.** Each use case builds a JSON schema where `decision` is a strict enum. The model *cannot* return an outcome that doesn't exist.
3. **Confidence guardrail.** If the model is unsure, the decision is escalated to a human instead of being acted on automatically.
4. **Audit log.** Every decision is logged with its ID, input, reasons, model and who decided (`llm`, `hard_rule` or `guardrail`).

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # add your OPENAI_API_KEY
```

Run the API:

```bash
export OPENAI_API_KEY=sk-...
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs for the interactive Swagger UI.

No API key? Everything runs offline with a rule-based mock provider:

```bash
DECISION_PROVIDER=mock uvicorn app.main:app --reload
DECISION_PROVIDER=mock python -m examples.demo
```

## Example

```bash
curl -s localhost:8000/decide/fraud_screening -H 'Content-Type: application/json' -d '{
  "input": {
    "amount_eur": 9500, "customer_avg_payment_eur": 120,
    "beneficiary_new": true, "beneficiary_country": "LT",
    "device_new": true, "login_country": "FR",
    "note": "urgent invoice from CEO"
  }
}'
```

```json
{
  "decision_id": "3f0c…",
  "use_case": "fraud_screening",
  "decision": "block",
  "confidence": 0.9,
  "reasons": [
    "Amount is ~79x the customer's average payment",
    "New beneficiary combined with a new device",
    "'Urgent invoice from CEO' matches a known CEO-fraud pattern"
  ],
  "risk_flags": ["amount_spike", "new_beneficiary", "new_device", "ceo_fraud_pattern"],
  "requires_human_review": false,
  "decided_by": "llm",
  "model": "gpt-4.1-mini",
  "latency_ms": 812
}
```

## Project layout

```text
app/
  use_cases.py   # policies, allowed decisions, hard rules, example inputs
  models.py      # request/response models + per-use-case strict schema
  engine.py      # hard rules -> GPT -> guardrail -> audit; OpenAI + mock providers
  main.py        # FastAPI endpoints
examples/demo.py # runs sample cases end to end
tests/           # pytest suite (runs offline)
```

## Adding your own use case

Add a `UseCase` in `app/use_cases.py` with its allowed `decisions`, a `policy` prompt, an `escalation_decision`, and optional `hard_rules`. It is exposed at `POST /decide/<name>` automatically.

Other applications that fit this pattern: insurance claims triage, KYC document checks, trade surveillance alerts, procurement approvals, content moderation, and IT incident prioritisation.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | – | Enables the OpenAI provider |
| `OPENAI_MODEL` | `gpt-4.1-mini` | Any model that supports Structured Outputs |
| `CONFIDENCE_THRESHOLD` | `0.75` | Below this, decisions are escalated to a human |
| `DECISION_PROVIDER` | `openai` | Set to `mock` to run offline |

## Tests

```bash
pytest -q
```

## Disclaimer

This is an educational demo. Automated credit and fraud decisions are regulated (for example GDPR Art. 22 and the EU AI Act). Real deployments need human oversight, bias testing, model risk management and explainability reviews.
