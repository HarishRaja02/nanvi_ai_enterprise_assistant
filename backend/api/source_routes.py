from fastapi import APIRouter, Depends, HTTPException, status

from backend.security.dependencies import get_current_user
from backend.security.models import UserIdentity
from backend.security.authorization import UserAttributes
from backend.sources.service import SourceReferenceNotFound, SourceReferenceService
from backend.sources.dependencies import get_source_reference_service

router = APIRouter()


def _attributes(identity: UserIdentity) -> UserAttributes:
    if not identity.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Authorization context unavailable")
    return UserAttributes(
        user_id=identity.subject,
        tenant_id=identity.tenant_id,
        department=identity.department,
        roles=identity.roles,
    )


@router.get("/sources/{reference_id}")
async def get_source_reference(
    reference_id: str,
    identity: UserIdentity = Depends(get_current_user),
    service: SourceReferenceService = Depends(get_source_reference_service),
):
    """Return safe citation metadata only; never source content or infrastructure paths."""
    try:
        reference = service.resolve_for_user(_attributes(identity), reference_id, reference_id)
    except SourceReferenceNotFound:
        # Deliberately identical for missing and unauthorized references so the endpoint
        # does not become an existence oracle for restricted company information.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source reference not found")
    return reference.to_frontend_dict()
