"""
Health check endpoints for Kubernetes probes.
"""

from fastapi import APIRouter

from echomind_lib.helpers.readiness_probe import get_readiness_probe

router = APIRouter()


@router.get("/health")
async def health_check():
    """
    Liveness probe endpoint.
    
    Returns 200 if the service is running.
    """
    return {"status": "ok"}


@router.get("/ready")
async def readiness_check():
    """
    Readiness probe endpoint.
    
    Checks all dependencies (DB, Redis, Qdrant, etc.).
    """
    probe = get_readiness_probe()
    report = await probe.check_health()
    return report.to_dict()
