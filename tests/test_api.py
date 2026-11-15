import os

os.environ["DECISION_PROVIDER"] = "mock"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.engine import DecisionEngine  # noqa: E402
from app.models import DecisionRequest, LLMDecision, decision_schema_for  # noqa: E402
from app.use_cases import USE_CASES  # noqa: E402

client = TestClient(app)


def post(use_case, data):
    r = client.post(f"/decide/{use_case}", json={"input": data})
    assert r.status_code == 200, r.text
    return r.json()


def test_lists_use_cases():
    names = {uc["name"] for uc in client.get("/use-cases").json()}
    assert names == {"loan_triage", "fraud_screening", "ticket_routing"}


def test_loan_approved_by_llm():
    body = post("loan_triage", USE_CASES["loan_triage"].example_input)
    assert body["decision"] == "approve"
    assert body["decided_by"] == "llm"
    assert body["requires_human_review"] is False


def test_hard_rule_overrides_model():
    data = {**USE_CASES["loan_triage"].example_input, "amount_eur": 400_000}
    body = post("loan_triage", data)
    assert body["decision"] == "refer_to_underwriter"
    assert body["decided_by"] == "hard_rule"


def test_grey_zone_referred():
    data = {**USE_CASES["loan_triage"].example_input, "monthly_debt_eur": 1_700}  # ~40% DTI
    body = post("loan_triage", data)
    assert body["decision"] == "refer_to_underwriter"
    assert body["requires_human_review"] is True


def test_low_confidence_guardrail_escalates():
    class UnsureProvider:
        model = "stub"

        def decide(self, use_case, request):
            return LLMDecision(decision="approve", confidence=0.5, reasons=["looks fine"], risk_flags=[])

    result = DecisionEngine(UnsureProvider()).decide(
        USE_CASES["loan_triage"], DecisionRequest(input=USE_CASES["loan_triage"].example_input)
    )
    assert result.decision == "refer_to_underwriter"
    assert result.decided_by == "guardrail"
    assert "low_confidence" in result.risk_flags


def test_fraud_blocked():
    body = post("fraud_screening", USE_CASES["fraud_screening"].example_input)
    assert body["decision"] == "block"


def test_sanctions_rule():
    data = {**USE_CASES["fraud_screening"].example_input, "beneficiary_country": "kp"}
    assert post("fraud_screening", data)["decided_by"] == "hard_rule"


def test_ticket_routing():
    assert post("ticket_routing", USE_CASES["ticket_routing"].example_input)["decision"] == "account_security"


def test_unknown_use_case():
    assert client.post("/decide/nope", json={"input": {}}).status_code == 404


def test_schema_restricts_decision_to_enum():
    uc = USE_CASES["fraud_screening"]
    schema = decision_schema_for(uc.name, uc.decisions).model_json_schema()
    assert schema["properties"]["decision"]["enum"] == list(uc.decisions)
