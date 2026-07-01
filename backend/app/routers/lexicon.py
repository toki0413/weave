"""自定义词典路由：管理每个家庭专属的实体词条"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime

from app.database import get_db
from app.models import CustomLexicon, User
from app.routers.auth import get_current_user

router = APIRouter(prefix="/lexicon", tags=["lexicon"])


# ========== 请求/响应模型 ==========
class LexiconItemCreate(BaseModel):
    word: str = Field(..., min_length=1, max_length=100)
    word_type: str = Field(..., pattern="^(person|place|event|item)$")


class LexiconImportItem(BaseModel):
    word: str = Field(..., min_length=1, max_length=100)
    word_type: str = Field(..., pattern="^(person|place|event|item)$")


class LexiconImport(BaseModel):
    items: List[LexiconImportItem]


class LexiconOut(BaseModel):
    id: str
    user_id: str
    word: str
    word_type: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ========== 路由 ==========
@router.get("/", response_model=List[LexiconOut])
def list_lexicon(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    word_type: Optional[str] = None,
):
    """获取当前用户的全部自定义词条，可选按类型过滤"""
    q = db.query(CustomLexicon).filter(CustomLexicon.user_id == current_user.id)
    if word_type:
        q = q.filter(CustomLexicon.word_type == word_type)
    return q.order_by(CustomLexicon.created_at.desc()).all()


@router.post("/", response_model=LexiconOut)
def add_lexicon_word(
    item: LexiconItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """添加单个词条；同一用户下重复词+类型会被忽略"""
    existing = db.query(CustomLexicon).filter(
        CustomLexicon.user_id == current_user.id,
        CustomLexicon.word == item.word,
        CustomLexicon.word_type == item.word_type,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="该词条已存在")

    entry = CustomLexicon(
        user_id=current_user.id,
        word=item.word,
        word_type=item.word_type,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{word_id}")
def delete_lexicon_word(
    word_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除指定词条，仅能删自己的"""
    entry = db.query(CustomLexicon).filter(
        CustomLexicon.id == word_id,
        CustomLexicon.user_id == current_user.id,
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="词条不存在")
    db.delete(entry)
    db.commit()
    return {"detail": "已删除", "id": word_id}


@router.post("/import", response_model=List[LexiconOut])
def import_lexicon(
    payload: LexiconImport,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量导入词条，自动跳过重复项"""
    # 先把已有的词+类型查出来，避免逐条查库
    existing_rows = db.query(CustomLexicon).filter(
        CustomLexicon.user_id == current_user.id,
    ).all()
    existing_keys = {(r.word, r.word_type) for r in existing_rows}

    created = []
    for it in payload.items:
        key = (it.word, it.word_type)
        if key in existing_keys:
            continue
        entry = CustomLexicon(
            user_id=current_user.id,
            word=it.word,
            word_type=it.word_type,
        )
        db.add(entry)
        existing_keys.add(key)
        created.append(entry)

    if created:
        db.commit()
        for e in created:
            db.refresh(e)
    return created
