from functools import lru_cache
from typing import Any, Literal

from pydantic import BaseModel, Field, create_model


class DecisionRequest(BaseModel):
    input: dict[str, Any] = Field(..., description="Case data to decide on")
    context: str | None = Field(None, description="Optional extra context for the model")


class LLMDecision(BaseModel):
    """Shape the LLM must return (enforced through structured outputs)."""

    decision: str
    confidence: float = Field(..., ge=0, le=1)
    reasons: list[str]
    risk_flags: list[str]


@lru_cache
def decision_schema_for(use_case: str, decisions: tuple[str, ...]) -> type[LLMDecision]:
    """Build a per-use-case schema so `decision` is a strict enum the model cannot escape."""
    return create_model(
        f"{use_case.title().replace('_', '')}Decision",
        __base__=LLMDecision,
        decision=(Literal[decisions], ...),  # type: ignore[valid-type]
    )


class DecisionResponse(BaseModel):
    decision_id: str
    use_case: str
    decision: str
    confidence: float
    reasons: list[str]
    risk_flags: list[str]
    requires_human_review: bool
    decided_by: Literal["llm", "hard_rule", "guardrail"]
    model: str
    latency_ms: int
