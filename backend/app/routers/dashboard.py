from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import AuthContext, require_doctor_for_documents
from app.schemas.admin import DashboardResponse
from app.services.analytics import get_doctor_dashboard

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
def doctor_dashboard(
    auth: AuthContext = Depends(require_doctor_for_documents),
    db: Session = Depends(get_db),
) -> DashboardResponse:
    return get_doctor_dashboard(db, auth.user.id)
