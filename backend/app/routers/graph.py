from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Session as DBSession
from app.routers.auth import get_current_user
from typing import List, Dict, Any

router = APIRouter(prefix="/graph", tags=["graph"])

@router.get("/latest")
def get_latest_graph(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = db.query(DBSession).filter(
        DBSession.user_id == current_user.id
    ).order_by(DBSession.created_at.desc()).first()
    
    if not session:
        return {"graph": {"nodes": [], "edges": []}, "metrics": {}, "health": 0}
    
    return {
        "graph": session.graph,
        "metrics": session.metrics,
        "health": session.health_score,
        "anomalies": session.anomalies,
        "day": session.day_number,
    }

@router.get("/export/json")
def export_json(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sessions = db.query(DBSession).filter(
        DBSession.user_id == current_user.id
    ).order_by(DBSession.created_at.desc()).all()
    
    return {
        "user_id": current_user.id,
        "export_time": datetime.now(timezone.utc).isoformat(),
        "sessions": [
            {
                "id": s.id,
                "day": s.day_number,
                "health": s.health_score,
                "graph": s.graph,
                "metrics": s.metrics,
                "anomalies": s.anomalies,
            }
            for s in sessions
        ],
    }

from datetime import datetime, timezone
