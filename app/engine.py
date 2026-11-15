"""Decision engine: hard rules -> GPT structured decision -> confidence guardrail -> audit."""

import json
import logging
import os
import time
import uuid
from typing import Protocol

from .models import DecisionRequest, DecisionResponse, LLMDecision, decision_schema_for
from .use_cases import UseCase

log = logging.getLogger("decision_audit")

CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.75"))


class DecisionProvider(Protocol):
    model: str

    def decide(self, use_case: UseCase, request: DecisionRequest) -> LLMDecision: ...


class OpenAIProvider:
    """Calls GPT with Structured Outputs so the reply always matches the schema."""

    def __init__(self, model: str | None = None):
        from openai import OpenAI

        self.client = OpenAI()
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    def decide(self, use_case: UseCase, request: DecisionRequest) -> LLMDecision:
        schema = decision_schema_for(use_case.name, use_case.decisions)
        instructions = (
            f"{use_case.policy}\n\n"
            "Return exactly one decision from the allowed list, a calibrated confidence "
            "between 0 and 1, short factual reasons that cite the input fields, and any "
            "risk flags. If information is missing, lower your confidence."
        )
        user = json.dumps(request.input, ensure_ascii=False)
        if request.context:
            user += f"\n\nContext: {request.context}"

        response = self.client.responses.parse(
            model=self.model,
            instructions=instructions,
            input=user,
            text_format=schema,
            temperature=0,
        )
        return response.output_parsed


class MockProvider:
    """Offline stand-in so the API, tests and demo run without an API key."""

    model = "mock"

    def decide(self, use_case: UseCase, request: DecisionRequest) -> LLMDecision:
        d = request.input
        if use_case.name == "loan_triage":
            dti = d.get("monthly_debt_eur", 0) / max(d.get("monthly_income_eur", 1), 1)
            if d.get("defaults_last_24m", 0) > 0 or dti > 0.5:
                return LLMDecision(decision="decline", confidence=0.9,
                                   reasons=[f"Debt-to-income {dti:.0%} or recent default"], risk_flags=["high_dti"])
            if dti < 0.35:
                return LLMDecision(decision="approve", confidence=0.88,
                                   reasons=[f"Debt-to-income {dti:.0%} below 35%"], risk_flags=[])
            return LLMDecision(decision="refer_to_underwriter", confidence=0.6,
                               reasons=[f"Debt-to-income {dti:.0%} in grey zone"], risk_flags=["grey_zone_dti"])
        if use_case.name == "fraud_screening":
            ratio = d.get("amount_eur", 0) / max(d.get("customer_avg_payment_eur", 1), 1)
            flags = [k for k in ("beneficiary_new", "device_new") if d.get(k)]
            if ratio > 20 and len(flags) == 2:
                return LLMDecision(decision="block", confidence=0.85,
                                   reasons=[f"Amount is {ratio:.0f}x the usual payment", "New beneficiary and device"],
                                   risk_flags=flags + ["amount_spike"])
            if flags:
                return LLMDecision(decision="step_up_auth", confidence=0.8, reasons=["New device or beneficiary"],
                                   risk_flags=flags)
            return LLMDecision(decision="allow", confidence=0.9, reasons=["Consistent with history"], risk_flags=[])
        text = f"{d.get('subject', '')} {d.get('body', '')}".lower()
        for team, words in {
            "account_security": ("never made", "hack", "phishing", "stolen", "lost card"),
            "billing": ("fee", "charge", "refund", "statement"),
            "technical": ("app", "login", "error", "website"),
            "complaints": ("complain", "lawyer", "unacceptable"),
        }.items():
            if any(w in text for w in words):
                return LLMDecision(decision=team, confidence=0.82, reasons=[f"Keywords match {team}"], risk_flags=[])
        return LLMDecision(decision="human_triage", confidence=0.4, reasons=["No clear topic"], risk_flags=[])


def default_provider() -> DecisionProvider:
    if os.getenv("OPENAI_API_KEY") and os.getenv("DECISION_PROVIDER", "openai") == "openai":
        return OpenAIProvider()
    return MockProvider()


class DecisionEngine:
    def __init__(self, provider: DecisionProvider | None = None):
        self.provider = provider or default_provider()

    def decide(self, use_case: UseCase, request: DecisionRequest) -> DecisionResponse:
        start = time.perf_counter()
        decision_id = str(uuid.uuid4())

        # 1. Hard rules run first and cannot be overridden by the model.
        for rule in use_case.hard_rules:
            reason = rule(request.input)
            if reason:
                result = self._build(decision_id, use_case, use_case.escalation_decision, 1.0,
                                     [reason], ["hard_rule"], "hard_rule", start)
                return self._audit(result, request)

        # 2. GPT makes a structured decision.
        llm = self.provider.decide(use_case, request)

        # 3. Guardrail: low confidence -> escalate to a human.
        if llm.confidence < CONFIDENCE_THRESHOLD and llm.decision != use_case.escalation_decision:
            result = self._build(
                decision_id, use_case, use_case.escalation_decision, llm.confidence,
                llm.reasons + [f"Model suggested '{llm.decision}' below confidence threshold {CONFIDENCE_THRESHOLD}"],
                llm.risk_flags + ["low_confidence"], "guardrail", start,
            )
        else:
            result = self._build(decision_id, use_case, llm.decision, llm.confidence,
                                 llm.reasons, llm.risk_flags, "llm", start)
        return self._audit(result, request)

    def _build(self, decision_id, use_case, decision, confidence, reasons, flags, by, start) -> DecisionResponse:
        return DecisionResponse(
            decision_id=decision_id,
            use_case=use_case.name,
            decision=decision,
            confidence=round(confidence, 3),
            reasons=reasons,
            risk_flags=flags,
            requires_human_review=decision == use_case.escalation_decision,
            decided_by=by,
            model=self.provider.model,
            latency_ms=int((time.perf_counter() - start) * 1000),
        )

    def _audit(self, result: DecisionResponse, request: DecisionRequest) -> DecisionResponse:
        # 4. Every decision is logged with its input for traceability.
        log.info(json.dumps({"audit": result.model_dump(), "input": request.input}, default=str))
        return result
