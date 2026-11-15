"""Run every use case's example through the engine and print the decisions.

    python -m examples.demo            # uses OpenAI if OPENAI_API_KEY is set, otherwise mock
    DECISION_PROVIDER=mock python -m examples.demo
"""

from app.engine import DecisionEngine
from app.models import DecisionRequest
from app.use_cases import USE_CASES

CASES = [
    ("loan_triage", USE_CASES["loan_triage"].example_input),
    ("loan_triage", {**USE_CASES["loan_triage"].example_input, "monthly_debt_eur": 1_700}),
    ("loan_triage", {**USE_CASES["loan_triage"].example_input, "amount_eur": 400_000}),
    ("fraud_screening", USE_CASES["fraud_screening"].example_input),
    ("fraud_screening", {"amount_eur": 45, "customer_avg_payment_eur": 60, "beneficiary_new": False,
                         "beneficiary_country": "FR", "device_new": False, "login_country": "FR"}),
    ("ticket_routing", USE_CASES["ticket_routing"].example_input),
    ("ticket_routing", {"channel": "chat", "subject": "Why this fee?", "body": "I was charged a 12 EUR fee."}),
]


def main():
    engine = DecisionEngine()
    print(f"Provider: {engine.provider.model}\n")
    for name, data in CASES:
        r = engine.decide(USE_CASES[name], DecisionRequest(input=data))
        review = "  -> HUMAN REVIEW" if r.requires_human_review else ""
        print(f"[{name}] {r.decision} (conf {r.confidence}, by {r.decided_by}){review}")
        for reason in r.reasons:
            print(f"    - {reason}")
        print()


if __name__ == "__main__":
    main()
