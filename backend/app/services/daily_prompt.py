# ============ 60 秒日课服务（CogniTalk 模式 + 适老化多模态契约）============
"""低门槛每日语音引导话题：降低记录阻力，提高纵向数据密度。

设计原则（极简适老化 + 多感官协同）：
- 60 秒上限：一次只回答一个问题，不追求长叙事
- 语音优先：tts_text 面向 TTS 朗读（短句、口语、无书面符号）
- 大字显示：question 是适合 22pt+ 大字渲染的短句
- 多模态反馈：modality 字段声明推荐呈现通道（voice/text/haptic），
  前端按通道组合渲染，不重复堆叠信息
- 题库围绕老人常用场景（人物/地点/事件/物品四类实体）设计，
  保证回答天然富含可抽取实体
- 可选 LLM 个性化：配置豆包（火山方舟）/deepseek/openai 后，
  在题库话题上生成个性化追问；失败或未配置时静默回退题库原题
"""

import hashlib
import logging
from datetime import date
from typing import Dict, Any, List, Optional

logger = logging.getLogger("cognitive_garden")

# 题库：按实体类型组织，每题都是"60 秒能说完"的具体问题
TOPIC_POOL: List[Dict[str, str]] = [
    # 人物（persons）
    {"category": "person", "topic": "家人", "question": "今天最想聊一位家人，TA 今天做了什么？", "tts": "说说今天家里人的事，随便聊一位"},
    {"category": "person", "topic": "老朋友", "question": "今天有没有想起哪位老朋友或老邻居？", "tts": "有没有想起哪位老朋友"},
    {"category": "person", "topic": "帮助", "question": "今天谁帮了您，或者您帮了谁一个小忙？", "tts": "今天谁帮了您，或者您帮了谁"},
    # 地点（places）
    {"category": "place", "topic": "出门", "question": "今天出过门吗？去了哪儿？", "tts": "今天出门了吗，去了哪里"},
    {"category": "place", "topic": "最常去的地方", "question": "说说您最常去的一个地方，今天去没去？", "tts": "您最常去的地方，今天去了吗"},
    {"category": "place", "topic": "窗外", "question": "今天窗外或楼下有什么新鲜事？", "tts": "今天窗外有什么新鲜事"},
    # 事件（events）
    {"category": "event", "topic": "早饭", "question": "今天早饭吃了什么？在哪里吃的？", "tts": "早饭吃了什么呀"},
    {"category": "event", "topic": "锻炼", "question": "今天活动筋骨了吗？做了什么？", "tts": "今天锻炼了吗，做了什么"},
    {"category": "event", "topic": "小确幸", "question": "今天有一件让您开心的小事吗？", "tts": "今天有什么开心的小事"},
    {"category": "event", "topic": "天气", "question": "今天天气怎么样？您出门感受如何？", "tts": "今天天气怎么样"},
    {"category": "event", "topic": "电视", "question": "今天看了什么电视或听了什么广播？", "tts": "今天看了什么电视节目"},
    # 物品（items）
    {"category": "item", "topic": "买菜", "question": "今天买了什么菜或东西？在哪儿买的？", "tts": "今天买了什么菜"},
    {"category": "item", "topic": "老物件", "question": "家里有件老物件，讲讲它和您的故事？", "tts": "说说家里一件老物件的故事"},
    {"category": "item", "topic": "药和身体", "question": "今天按时吃药、量血压了吗？", "tts": "今天吃药和量血压了吗"},
]

# 副话题池：主话题之外给一个轻量备选，保持极简（最多两个选择，避免决策负担）
_FALLBACK_MODTALITY = {"voice": "primary", "text": "large_print", "haptic": "start_end"}

# 冷启动种子序列（U1）：注册后前 7 天的日课按"家族人物 + 老物件"主题定类别。
# 依据：NLP 实体抽取依赖前几条叙事积累，冷启动期图谱接近空白；家人的名字、
# 老物件的名字是老人最不费力的实体来源，先喂这两类让图谱尽快"长出第一朵花"。
# 序列固定为"每天一个类别"而不是每天一道题——同类别内仍按 hash 轮转，
# 避免同一天注册的所有老人拿到完全相同的题目。
SEED_SEQUENCE: List[str] = [
    "person",  # 第 1 天：家人（最亲的人开场）
    "item",    # 第 2 天：老物件（家里现成的记忆锚点）
    "person",  # 第 3 天：老朋友
    "event",   # 第 4 天：早饭（低门槛破冰）
    "person",  # 第 5 天：谁帮了谁
    "item",    # 第 6 天：买菜（生活琐事实体丰富）
    "place",   # 第 7 天：最常去的地方
]
SEED_WINDOW_DAYS = len(SEED_SEQUENCE)


def _seed_day_index(signup_date: date, the_date: date) -> Optional[int]:
    """注册后第几天；不在 0..6 窗口内返回 None。

    两个日期由调用方统一口径（端点传北京日期）后做差。
    """
    delta = (the_date - signup_date).days
    if 0 <= delta < SEED_WINDOW_DAYS:
        return delta
    return None


def get_daily_prompt(
    user_id: str,
    the_date: Optional[date] = None,
    use_llm: bool = True,
    signup_date: Optional[date] = None,
) -> Dict[str, Any]:
    """获取当日日课题目。

    选题规则：hash(user_id + 日期) 决定题库内轮转，天然按天轮换，
    不同老人同日题目不同；无需额外存储。
    冷启动：signup_date 提供且落在前 7 天窗口内时，按 SEED_SEQUENCE
    的类别定池（家族人物 + 老物件优先），窗口外回到全池。
    LLM 个性化：配置了 LLM 时尝试生成一句个性化追问（personalized_hint），
    失败静默回退——题目本身永远可用。
    """
    the_date = the_date or date.today()
    seed_day = _seed_day_index(signup_date, the_date) if signup_date else None
    if seed_day is not None:
        pool = [t for t in TOPIC_POOL if t["category"] == SEED_SEQUENCE[seed_day]]
    else:
        pool = TOPIC_POOL
    seed = hashlib.sha256(f"{user_id}:{the_date.isoformat()}".encode("utf-8")).hexdigest()
    topic = pool[int(seed[:8], 16) % len(pool)]

    result: Dict[str, Any] = {
        "date": the_date.isoformat(),
        "category": topic["category"],
        "topic": topic["topic"],
        # 大字渲染用（适老化 22pt+）
        "question": topic["question"],
        # TTS 朗读用（口语短句，无书面符号）
        "tts_text": topic["tts"],
        # 多模态呈现契约：voice 为主通道，text 供大字显示，haptic 起止提示
        "modality": dict(_FALLBACK_MODTALITY),
        "duration_hint": "60秒",
        # 冷启动种子进度：0-6 = 注册后第几天；null = 已出窗口
        "seed_day": seed_day,
        "personalized_hint": None,
        "llm_provider": None,
    }

    if use_llm:
        try:
            from app.config import get_settings
            from app.services.llm_client import is_llm_available, llm_call

            if is_llm_available():
                provider = get_settings().llm_provider
                hint = llm_call(
                    prompt=(
                        f"老人今天的日课话题是「{topic['topic']}」，题目：{topic['question']}\n"
                        f"请用一句不超过 20 个字的口语化追问，帮老人打开话匣子，"
                        f"不要书面语，不要问号以外的标点堆叠。只输出这一句话。"
                    ),
                    system_prompt="你是面向中国老年人的语音助手，语气像家人，用词简单温暖。",
                    temperature=0.8,
                    max_tokens=64,
                )
                hint = (hint or "").strip(" '\"\u201c\u201d`").strip()
                if hint:
                    result["personalized_hint"] = hint[:60]
                    result["llm_provider"] = provider
        except Exception as e:  # 静默回退：LLM 不可用时题目照常
            logger.info("日课 LLM 个性化失败，回退题库原题: %s", e)

    return result
