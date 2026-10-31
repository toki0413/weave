"""自定义词典路由：管理每个家庭专属的实体词条"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Optional
from datetime import datetime

from app.database import get_db
from app.models import CustomLexicon, User
from app.routers.auth import get_current_user
from app.middleware.permission import resolve_target_user

router = APIRouter(prefix="/lexicon", tags=["lexicon"])

# 中文类型别名：家属（尤其是不写代码的家属）只会说"人名/地点"，
# 此前批量导入要求 person/place/event/item，等于把家属挡在门外。
# 归一发生在 schema 校验之前，所以字段本身放宽为字符串。
LEXICON_TYPE_ALIASES = {
    "person": "person", "人物": "person", "人名": "person", "人": "person",
    "place": "place", "地点": "place", "地方": "place", "场所": "place",
    "event": "event", "事件": "event", "事情": "event", "活动": "event",
    "item": "item", "物品": "item", "东西": "item", "物件": "item",
}


def _norm_type(raw: str) -> str:
    # 单层查表：中文键不受 lower() 影响，英文键本就是小写（与前端
    # ui/lexicon-import.js 同一套映射与同一理由）
    key = (raw or "").strip().lower()
    mapped = LEXICON_TYPE_ALIASES.get(key)
    if not mapped:
        raise ValueError("word_type 需为 person/place/event/item，或中文：人名/地点/事件/物品")
    return mapped


# ========== 请求/响应模型 ==========
class LexiconItemCreate(BaseModel):
    word: str = Field(..., min_length=1, max_length=100)
    word_type: str = Field(..., min_length=1, max_length=20)

    @field_validator("word_type")
    @classmethod
    def _t(cls, v):
        return _norm_type(v)


class LexiconImportItem(BaseModel):
    word: str = Field(..., min_length=1, max_length=100)
    word_type: str = Field(..., min_length=1, max_length=20)

    @field_validator("word_type")
    @classmethod
    def _t(cls, v):
        return _norm_type(v)


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
# elderly_id：家属/医生代维护"老人的"词典。转写发生在老人上传时，
# 只有落在老人 user_id 下的词条才会被 stt.py 取到并进百炼 system
# context —— 家属写进自己名下对老人的转写零作用，所以这里是代理写入
# 而不是各存一份。权限与默认对象规则见 resolve_target_user。
@router.get("/", response_model=List[LexiconOut])
def list_lexicon(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    word_type: Optional[str] = None,
    elderly_id: Optional[str] = Query(None, description="代维护的目标老人"),
):
    """获取目标用户的全部自定义词条，可选按类型过滤"""
    target = resolve_target_user(db, current_user, elderly_id)
    q = db.query(CustomLexicon).filter(CustomLexicon.user_id == target)
    if word_type:
        q = q.filter(CustomLexicon.word_type == _norm_type(word_type))
    return q.order_by(CustomLexicon.created_at.desc()).all()


@router.post("/", response_model=LexiconOut)
def add_lexicon_word(
    item: LexiconItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    elderly_id: Optional[str] = Query(None, description="代维护的目标老人"),
):
    """添加单个词条；同一用户下重复词+类型会被拒绝"""
    target = resolve_target_user(db, current_user, elderly_id)
    existing = db.query(CustomLexicon).filter(
        CustomLexicon.user_id == target,
        CustomLexicon.word == item.word,
        CustomLexicon.word_type == item.word_type,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="该词条已存在")

    entry = CustomLexicon(
        user_id=target,
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
    elderly_id: Optional[str] = Query(None, description="代维护的目标老人"),
):
    """删除词条：目标由 elderly_id 决定，且只能删目标用户名下的词条"""
    target = resolve_target_user(db, current_user, elderly_id)
    entry = db.query(CustomLexicon).filter(
        CustomLexicon.id == word_id,
        CustomLexicon.user_id == target,
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
    elderly_id: Optional[str] = Query(None, description="代维护的目标老人"),
):
    """批量导入词条，自动跳过重复项（去重仍在本路由内，表上没有唯一约束）"""
    target = resolve_target_user(db, current_user, elderly_id)
    existing_rows = db.query(CustomLexicon).filter(
        CustomLexicon.user_id == target,
    ).all()
    existing_keys = {(r.word, r.word_type) for r in existing_rows}

    created = []
    for it in payload.items:
        key = (it.word, it.word_type)
        if key in existing_keys:
            continue
        entry = CustomLexicon(
            user_id=target,
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
