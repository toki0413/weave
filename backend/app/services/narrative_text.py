# ============ 叙事明文读取 ============
"""把「可能已加密的 narrative」取成明文，供服务层使用。

为什么要有这个模块：
routers/session.py 里已有 _decrypt_with_fallback / _decrypt_session，但服务层
不能复用 —— 它解密失败会抛 HTTPException(401)，那是路由层的语义，服务层抛出
HTTP 异常既不该也不好用。

这里刻意区分三种返回值，而不是"取不到就退回原文"：
base64 密文能切句、能被 jieba 分词，静默退回原文等于交出一些近乎恒定的
无意义数字，而且不报错。这正是 decline.py 原先那个缺陷能长期存活的原因。
"""
from dataclasses import dataclass
from typing import Optional

from app.services import key_manager
from app.services.crypto import decrypt

# 三种状态
OK = "ok"                     # 明文或解密成功
DECRYPT_FAILED = "decrypt_failed"   # 该解密但解不出来（未登录 / 密钥丢失）
NO_CONTENT = "no_content"           # 空或 None


@dataclass(frozen=True)
class NarrativeText:
    text: str
    state: str
    reason: str = ""

    @property
    def usable(self) -> bool:
        return self.state == OK


def decrypt_narrative(raw: Optional[str], user_id: str, is_encrypted: bool) -> NarrativeText:
    if not raw or not raw.strip():
        return NarrativeText("", NO_CONTENT, "empty")
    if not is_encrypted:
        # 旧的未加密数据：放过，与 session.py:59 的判断保持一致
        return NarrativeText(raw, OK, "plaintext")
    try:
        return NarrativeText(decrypt(raw, key_manager.get_user_key(user_id)), OK, "master_key")
    except Exception:
        pass
    try:
        # 兼容早期用 KEK 直接加密的数据
        return NarrativeText(decrypt(raw, key_manager.get_user_kek(user_id)), OK, "kek_fallback")
    except Exception as e:
        return NarrativeText("", DECRYPT_FAILED, type(e).__name__)
