"""Liveness and root endpoints."""

from fastapi import APIRouter

from app.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="mgc-backend", version="0.1.0")


@router.get("/")
def root() -> dict:
    return {"message": "MGC PoC API. See /health and /docs."}
