from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Baseline
from app.schemas import BaselineCreate, BaselineOut
from app.routers.auth import get_current_user

router = APIRouter(prefix="/baseline", tags=["baseline"])

@router.post("/", response_model=BaselineOut)
def create_baseline(
    data: BaselineCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models import Session as DBSession
    session = db.query(DBSession).filter(
        DBSession.id == data.session_id,
        DBSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Delete existing baseline
    db.query(Baseline).filter(Baseline.user_id == current_user.id).delete()
    
    baseline = Baseline(
        user_id=current_user.id,
        session_id=data.session_id,
        metrics=session.metrics,
    )
    db.add(baseline)
    db.commit()
    db.refresh(baseline)
    return baseline

@router.get("/", response_model=BaselineOut)
def get_baseline(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    baseline = db.query(Baseline).filter(Baseline.user_id == current_user.id).first()
    if not baseline:
        raise HTTPException(status_code=404, detail="No baseline set")
    return baseline
