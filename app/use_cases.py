"""Decision use cases: each one defines the allowed outcomes, the policy the
model must follow, and hard rules that are enforced in code (never by the LLM).
"""

from dataclasses import dataclass, field
from typing import Callable

HardRule = Callable[[dict], str | None]  # returns a forced decision reason, or None


@dataclass(frozen=True)
class UseCase:
    name: str
    title: str
    decisions: tuple[str, ...]
    escalation_decision: str  # what to return when a human must review
    policy: str
    example_input: dict
    hard_rules: list[HardRule] = field(default_factory=list)


# ---------------------------------------------------------------- loan triage
def _loan_amount_cap(data: dict) -> str | None:
    if float(data.get("amount_eur", 0)) > 250_000:
        return "Amount above EUR 250k always requires a credit officer."
    return None


LOAN_TRIAGE = UseCase(
    name="loan_triage",
    title="Consumer loan pre-screening",
    decisions=("approve", "decline", "refer_to_underwriter"),
    escalation_decision="refer_to_underwriter",
    policy=(
        "You pre-screen consumer loan applications for a retail bank.\n"
        "- approve: debt-to-income below 35%, stable income, no recent defaults.\n"
        "- decline: debt-to-income above 50% or a default in the last 24 months.\n"
        "- refer_to_underwriter: anything in between, missing data, or unusual cases.\n"
        "Never use age, gender, nationality, religion or other protected attributes."
    ),
    example_input={
        "amount_eur": 18_000,
        "monthly_income_eur": 4_200,
        "monthly_debt_eur": 900,
        "employment": "permanent, 6 years",
        "defaults_last_24m": 0,
        "purpose": "car purchase",
    },
    hard_rules=[_loan_amount_cap],
)


# ------------------------------------------------------------ fraud screening
def _sanctioned_country(data: dict) -> str | None:
    if str(data.get("beneficiary_country", "")).upper() in {"KP", "IR", "SY"}:
        return "Beneficiary country is on the sanctions list."
    return None


FRAUD_SCREENING = UseCase(
    name="fraud_screening",
    title="Payment fraud screening",
    decisions=("allow", "block", "step_up_auth", "manual_review"),
    escalation_decision="manual_review",
    policy=(
        "You screen outgoing card and wire payments for fraud.\n"
        "- allow: consistent with the customer's usual behaviour.\n"
        "- step_up_auth: mildly unusual (new device, new merchant) -> ask for 2FA.\n"
        "- block: strong fraud signals (new beneficiary + large amount + new device,\n"
        "  impossible travel, known scam patterns).\n"
        "- manual_review: ambiguous, high value, or insufficient data."
    ),
    example_input={
        "amount_eur": 9_500,
        "customer_avg_payment_eur": 120,
        "beneficiary_new": True,
        "beneficiary_country": "LT",
        "device_new": True,
        "login_country": "FR",
        "note": "urgent invoice from CEO",
    },
    hard_rules=[_sanctioned_country],
)


# ------------------------------------------------------------- ticket routing
TICKET_ROUTING = UseCase(
    name="ticket_routing",
    title="Customer support ticket routing",
    decisions=("billing", "technical", "account_security", "complaints", "human_triage"),
    escalation_decision="human_triage",
    policy=(
        "You route customer support tickets to the right team.\n"
        "- account_security: lost card, suspected hacking, phishing, unknown transactions.\n"
        "- billing: fees, charges, refunds, statements.\n"
        "- technical: app, login errors, website issues.\n"
        "- complaints: dissatisfaction with service or staff, legal threats.\n"
        "- human_triage: unclear or multiple equally strong topics."
    ),
    example_input={
        "channel": "email",
        "subject": "Money gone??",
        "body": "I see 3 payments I never made last night and I can't log into the app.",
    },
)


USE_CASES: dict[str, UseCase] = {
    uc.name: uc for uc in (LOAN_TRIAGE, FRAUD_SCREENING, TICKET_ROUTING)
}
