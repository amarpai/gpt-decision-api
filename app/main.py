import logging

from fastapi import FastAPI, HTTPException

from .engine import DecisionEngine
from .models import DecisionRequest, DecisionResponse
from .use_cases import USE_CASES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

app = FastAPI(
    title="GPT Decision API",
    description="Structured, auditable business decisions powered by GPT with code-enforced guardrails.",
    version="0.1.0",
)
engine = DecisionEngine()


@app.get("/health")
def health():
    return {"status": "ok", "model": engine.provider.model}


@app.get("/use-cases")
def list_use_cases():
    return [
        {"name": uc.name, "title": uc.title, "decisions": uc.decisions, "example_input": uc.example_input}
        for uc in USE_CASES.values()
    ]


@app.post("/decide/{use_case}", response_model=DecisionResponse)
def decide(use_case: str, request: DecisionRequest):
    uc = USE_CASES.get(use_case)
    if not uc:
        raise HTTPException(404, f"Unknown use case '{use_case}'. See GET /use-cases.")
    return engine.decide(uc, request)
