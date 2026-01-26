"""
Health check endpoints for Kubernetes probes.
"""

import logging

from fastapi import APIRouter, HTTPException, status

from echomind_lib.helpers.readiness_probe import get_readiness_probe

logger = logging.getLogger(__name__)
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

    Returns:
        Health report with status of each dependency.

    Raises:
        HTTPException: 500 if probe fails unexpectedly.
    """
    try:
        probe = get_readiness_probe()
        report = await probe.check_health()
        return report.to_dict()
    except Exception as e:
        logger.exception("❌ Readiness probe failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Health check failed: {str(e)}",
        )
