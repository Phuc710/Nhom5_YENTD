"""
Configuration routes: read and update runtime config.
"""
from fastapi import APIRouter, Depends

from api.models import ConfigResponse, ConfigUpdateRequest, MessageResponse
from api.services.alpr_service import ALPRService
from api.dependencies import get_alpr_service

router = APIRouter(tags=["Configuration"])


@router.get(
    "/config",
    response_model=ConfigResponse,
    summary="Get current configuration",
)
async def get_config(service: ALPRService = Depends(get_alpr_service)):
    config = service.get_config()
    return ConfigResponse(**config)


@router.put(
    "/config",
    response_model=MessageResponse,
    summary="Update runtime configuration",
    description=(
        "Update detection thresholds and flags at runtime without restarting.\n\n"
        "Only the fields you include will be changed; omitted fields stay the same."
    ),
)
async def update_config(
    request: ConfigUpdateRequest,
    service: ALPRService = Depends(get_alpr_service),
):
    updates = request.model_dump(exclude_none=True)
    if not updates:
        return MessageResponse(message="No changes provided.")
    service.update_config(**updates)
    return MessageResponse(message=f"Configuration updated: {', '.join(updates.keys())}")
