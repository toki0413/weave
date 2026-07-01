# ============ NLP 服务：jieba 分词 + 词典匹配 + 模式提取 ============
import re
import logging
import threading
from typing import List, Dict, Any, Optional

logger = logging.getLogger("cognitive_garden")

_jieba_lock = threading.Lock()

from app.services.emotion_analyzer import analyze_emotion
from app.services.temporal_parser import extract_temporal_references

# 尝试加载 jieba，失败则降级到纯 FMM
try:
    import jieba
    import jieba.posseg as pseg
    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False
    logger.warning("jieba 未安装，NLP 降级到纯词典匹配模式")

# ============================================================
# 词典：覆盖老人日常叙述的高频实体
# ============================================================

LEXICON = {
    "person": [
        # 家人
        "老伴", "儿子", "女儿", "孙子", "孙女", "女婿", "儿媳", "外孙", "外孙女",
        "爷爷", "奶奶", "爸爸", "妈妈", "哥哥", "姐姐", "弟弟", "妹妹",
        # 常见称呼
        "老张", "老王", "老李", "老刘", "老陈", "老赵", "老周", "老吴", "老孙",
        "张医生", "王医生", "李医生", "刘医生", "张护士", "王护士",
        "王阿姨", "李阿姨", "张阿姨", "刘阿姨",
        # 社会角色
        "邻居", "朋友", "医生", "护士", "护工", "保姆", "志愿者",
        "社区工作者", "居委会", "门卫", "保安", "清洁工",
        # 泛指
        "师傅", "同志", "先生", "女士", "老太太", "老头", "大爷", "大妈",
    ],
    "place": [
        # 住宅
        "家", "客厅", "卧室", "厨房", "卫生间", "阳台", "院子", "书房",
        "门口", "楼道", "电梯", "楼梯", "车库", "地下室",
        # 公共场所
        "公园", "广场", "花园", "菜市场", "超市", "商店", "商场",
        "医院", "诊所", "药店", "药房", "社区卫生站",
        "银行", "邮局", "理发店", "澡堂", "活动中心",
        "学校", "幼儿园", "图书馆", "博物馆", "体育馆",
        "车站", "地铁站", "公交站", "路口", "十字路口",
        # 泛指
        "外面", "里面", "楼上", "楼下", "附近", "对面",
    ],
    "event": [
        # 运动
        "打太极", "打太极剑", "晨练", "锻炼", "散步", "跑步", "做操",
        "跳舞", "打拳", "练功", "活动筋骨",
        # 日常
        "买菜", "买药", "买东西", "购物", "看病", "复诊", "检查", "量血压",
        "吃药", "服药", "打针", "输液", "抽血", "做检查",
        "吃饭", "做饭", "烧饭", "煮饭", "做早饭", "做午饭", "做晚饭",
        "洗碗", "洗衣服", "晾衣服", "打扫", "扫地", "拖地", "擦窗户",
        # 休闲
        "聊天", "聊家常", "下棋", "打牌", "打麻将", "看电视", "听广播",
        "看报纸", "看书", "读报", "听音乐", "唱戏", "唱歌",
        "浇花", "种菜", "养鸟", "遛鸟", "遛狗", "喂鱼",
        # 出行
        "回家", "出门", "逛街", "串门", "拜访", "聚会",
        "接送", "等车", "坐车", "乘车", "转车",
        # 其他
        "休息", "午休", "睡觉", "起床", "洗漱", "洗澡", "理发",
    ],
    "item": [
        # 运动器材
        "太极剑", "太极扇", "健身球", "跳绳", "哑铃",
        # 医疗
        "血压计", "血糖仪", "体温计", "药盒", "药瓶", "处方", "病历本",
        # 日常用品
        "购物袋", "保温杯", "茶杯", "水壶", "老花镜", "眼镜", "拐杖",
        "收音机", "手机", "钥匙", "钱包", "雨伞", "帽子", "手套", "围巾",
        "报纸", "杂志", "书本", "遥控器", "助听器", "假牙",
        # 食物
        "菜", "药", "水果", "牛奶", "鸡蛋", "面包", "馒头", "米饭",
        "面条", "饺子", "包子", "粥", "汤", "茶", "水",
    ],
}

# 所有词条展平，带类型标注
ALL_WORDS: List[Dict[str, str]] = []
for _type, _words in LEXICON.items():
    for _w in _words:
        ALL_WORDS.append({"word": _w, "type": _type})

# 语义规则：事件 → 预期地点
SEMANTIC_RULES = {
    "打太极": {"expectedPlaces": ["公园", "广场", "院子"], "severity": "warn"},
    "打太极剑": {"expectedPlaces": ["公园", "广场", "院子"], "severity": "warn"},
    "晨练": {"expectedPlaces": ["公园", "广场", "院子"], "severity": "warn"},
    "锻炼": {"expectedPlaces": ["公园", "广场", "院子", "家"], "severity": "warn"},
    "散步": {"expectedPlaces": ["公园", "广场", "院子", "门口"], "severity": "warn"},
    "跳舞": {"expectedPlaces": ["广场", "公园", "活动中心"], "severity": "warn"},
    "买菜": {"expectedPlaces": ["菜市场", "超市", "商店"], "severity": "warn"},
    "买药": {"expectedPlaces": ["药店", "药房", "医院"], "severity": "warn"},
    "看病": {"expectedPlaces": ["医院", "诊所"], "severity": "danger"},
    "复诊": {"expectedPlaces": ["医院", "诊所"], "severity": "danger"},
    "检查": {"expectedPlaces": ["医院", "诊所", "社区卫生站"], "severity": "danger"},
    "量血压": {"expectedPlaces": ["医院", "家", "社区卫生站"], "severity": "warn"},
    "吃药": {"expectedPlaces": ["家", "客厅", "卧室"], "severity": "warn"},
    "下棋": {"expectedPlaces": ["公园", "广场", "客厅", "活动中心"], "severity": "warn"},
    "打牌": {"expectedPlaces": ["活动中心", "客厅", "公园"], "severity": "warn"},
    "打麻将": {"expectedPlaces": ["活动中心", "客厅"], "severity": "warn"},
    "浇花": {"expectedPlaces": ["阳台", "院子", "花园"], "severity": "warn"},
    "种菜": {"expectedPlaces": ["院子", "花园"], "severity": "warn"},
    "做饭": {"expectedPlaces": ["家", "厨房"], "severity": "warn"},
    "看电视": {"expectedPlaces": ["客厅", "卧室", "家"], "severity": "warn"},
    "看报纸": {"expectedPlaces": ["家", "客厅", "公园"], "severity": "warn"},
    "洗衣服": {"expectedPlaces": ["家", "卫生间", "阳台"], "severity": "warn"},
    "洗澡": {"expectedPlaces": ["家", "卫生间"], "severity": "warn"},
    "理发": {"expectedPlaces": ["理发店"], "severity": "warn"},
}

# 时间表达：用于异常检测
TIME_EXPRESSIONS = {
    "凌晨": range(0, 5),
    "半夜": range(0, 4),
    "深夜": range(22, 24),
    "早上": range(5, 9),
    "早晨": range(5, 9),
    "上午": range(8, 12),
    "中午": range(11, 14),
    "下午": range(13, 18),
    "傍晚": range(17, 20),
    "晚上": range(18, 24),
    "夜里": range(20, 24),
}

# 事件-时间预期：某些事件在特定时段出现属于异常
EVENT_TIME_EXPECTATIONS = {
    "打太极": {"expected": ["早上", "早晨", "上午"], "severity": "warn"},
    "晨练": {"expected": ["早上", "早晨"], "severity": "warn"},
    "散步": {"expected": ["早上", "早晨", "下午", "傍晚", "晚上"], "severity": "warn"},
    "睡觉": {"expected": ["晚上", "夜里", "半夜", "凌晨"], "severity": "warn"},
    "起床": {"expected": ["早上", "早晨", "上午"], "severity": "warn"},
    "午休": {"expected": ["中午", "下午"], "severity": "warn"},
    "买菜": {"expected": ["早上", "早晨", "上午", "下午"], "severity": "warn"},
    "看电视": {"expected": ["下午", "傍晚", "晚上", "夜里"], "severity": "warn"},
}

# jieba 初始化：加载自定义词典
if JIEBA_AVAILABLE:
    with _jieba_lock:
        for _w in ALL_WORDS:
            jieba.add_word(_w["word"], tag=_w["type"])
    logger.info("jieba 词典加载完成，共 %d 个词条", len(ALL_WORDS))


def fmm_segment(text: str, custom_words: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, Any]]:
    """分词：优先 jieba，降级到 FMM。custom_words 会临时加入分词器"""
    if JIEBA_AVAILABLE:
        return _jieba_segment(text, custom_words)
    return _fmm_segment(text, custom_words)


def _jieba_segment(text: str, custom_words: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, Any]]:
    """jieba 分词 + 词典类型标注"""
    # 临时把用户自定义词喂给 jieba，分完再撤掉，避免污染全局词典
    added = []
    if custom_words:
        for cw in custom_words:
            w = cw.get("word") or cw.get("type")
            if not w:
                continue
            wtype = cw.get("type") or cw.get("word_type")
            with _jieba_lock:
                jieba.add_word(w, tag=wtype or "")
            added.append(w)

    try:
        result = []
        pos = 0
        for word, flag in pseg.cut(text):
            if not word.strip():
                pos += len(word)
                continue
            # 优先用词典类型，其次用 jieba 词性推断
            wtype = _lookup_type(word, custom_words) or _pos_to_type(flag)
            if wtype:
                result.append({
                    "word": word,
                    "type": wtype,
                    "start": pos,
                    "end": pos + len(word),
                })
            pos += len(word)
        return result
    finally:
        # 撤回临时词，防止跨请求累积
        for w in added:
            try:
                with _jieba_lock:
                    jieba.del_word(w)
            except Exception:
                pass


def _fmm_segment(text: str, custom_words: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, Any]]:
    """纯 FMM 降级方案"""
    result = []
    i = 0
    while i < len(text):
        matched = False
        for j in range(min(8, len(text) - i), 1, -1):
            sub = text[i:i + j]
            wtype = _lookup_type(sub, custom_words)
            if wtype:
                result.append({"word": sub, "type": wtype, "start": i, "end": i + j})
                i += j
                matched = True
                break
        if not matched:
            i += 1
    return result


def _lookup_type(word: str, custom_words: Optional[List[Dict[str, str]]] = None) -> str:
    """查词典返回类型，无匹配返回空串。custom_words 优先于静态词典"""
    if custom_words:
        for entry in custom_words:
            if entry.get("word") == word:
                return entry.get("type") or entry.get("word_type") or ""
    for entry in ALL_WORDS:
        if entry["word"] == word:
            return entry["type"]
    return ""


def _pos_to_type(pos: str) -> str:
    """jieba 词性标注转实体类型"""
    if pos.startswith("nr"):
        return "person"
    if pos.startswith("ns"):
        return "place"
    if pos.startswith("vn") or pos.startswith("v"):
        return "event"
    return ""


def extract_entities(text: str, custom_words: Optional[List[Dict[str, str]]] = None) -> Dict[str, List[str]]:
    """提取实体。custom_words 为用户自定义词典，会临时加入分词器"""
    tokens = fmm_segment(text, custom_words)
    ent = {"persons": [], "places": [], "events": [], "items": []}
    for t in tokens:
        cat = t["type"] + "s"
        if cat in ent and t["word"] not in ent[cat]:
            ent[cat].append(t["word"])
    return ent


def extract_anon_features(text: str) -> List[str]:
    """提取匿名节点特征词：那个...的"""
    m = re.search(r"那个(.+?)的(?=[，。！？]|$)", text) or re.search(r"那个(.+)的", text)
    if m:
        return [f.replace("的", "").strip() for f in re.split(r"[、，和]", m.group(1)) if f.strip()]
    return []


def check_anomalies(text: str, entities: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    """语义异常检测：事件-地点不匹配 + 事件-时间不匹配"""
    anomalies = []

    # 1. 事件-地点不匹配
    for event in entities.get("events", []):
        rule = SEMANTIC_RULES.get(event)
        if rule:
            has_expected = any(p in rule["expectedPlaces"] for p in entities.get("places", []))
            if not has_expected:
                # 检查是否有非预期地点与事件同句出现，升级为 danger
                severity = rule["severity"]
                for pl in entities.get("places", []):
                    if pl not in rule["expectedPlaces"]:
                        # 同句检测
                        for sentence in re.split(r"[，。；]", text):
                            if event in sentence and pl in sentence:
                                severity = "danger"
                                break
                anomalies.append({
                    "event": event,
                    "expected_places": rule["expectedPlaces"],
                    "severity": severity,
                    "type": "event-place-mismatch",
                })

    # 2. 事件-时间不匹配
    for event in entities.get("events", []):
        time_rule = EVENT_TIME_EXPECTATIONS.get(event)
        if time_rule:
            # 检测文本中的时间表达
            found_times = [t for t in TIME_EXPRESSIONS if t in text]
            if found_times:
                # 任一时间不在预期内则报警
                unexpected = [t for t in found_times if t not in time_rule["expected"]]
                if unexpected:
                    anomalies.append({
                        "event": event,
                        "unexpected_times": unexpected,
                        "expected_times": time_rule["expected"],
                        "severity": time_rule["severity"],
                        "type": "event-time-mismatch",
                    })

    # 去重：同 event + 同 type 保留最高严重级
    unique = {}
    for a in anomalies:
        key = (a["event"], a["type"])
        if key not in unique or a["severity"] == "danger":
            unique[key] = a
    return list(unique.values())


def _extract_relations(text: str, entities: Dict[str, List[str]]) -> List[Dict[str, str]]:
    """基于模式匹配提取关系（与前端 parse.js 对齐）"""
    relations = []
    m = None

    # 在...碰见/遇见... → 空间关系
    m = re.search(r"在(.+?)(碰见|遇见|遇到|碰到)(.+?)(?:，|。|然后|一起)", text)
    if m:
        p1 = next((p for p in entities["places"] if p in m.group(1)), None)
        p2 = next((p for p in entities["persons"] if p in m.group(3)), None)
        if p1 and p2:
            relations.append({"from": f"persons:{p2}", "to": f"places:{p1}", "type": "space"})

    # 一起... → 情感关系
    m = re.search(r"一起(.+?)(?:，|。|然后|去|回)", text)
    if m:
        ev = next((e for e in entities["events"] if e in m.group(1)), None)
        ps = entities["persons"][0] if entities["persons"] else None
        if ps and ev:
            relations.append({"from": f"persons:{ps}", "to": f"events:{ev}", "type": "emotion"})

    # 然后/之后 → 时间关系
    if re.search(r"然后|之后|接着", text) and len(entities["events"]) >= 2:
        relations.append({
            "from": f"events:{entities['events'][0]}",
            "to": f"events:{entities['events'][1]}",
            "type": "time",
        })

    # 去...买... → 空间+关联
    m = re.search(r"去(.+?)(?:买|取|拿)(了)?(.+?)(?:，|。|然后|回家)", text)
    if m:
        pl = next((p for p in entities["places"] if p in m.group(1)), None)
        it = next((i for i in entities["items"] if i in m.group(3)), None)
        if pl:
            relations.append({"from": "persons:SELF", "to": f"places:{pl}", "type": "space"})
        if it:
            relations.append({"from": "persons:SELF", "to": f"items:{it}", "type": "custom"})

    # ...陪我去... → 情感+空间
    m = re.search(r"(.+?)陪(我|他|她)?去(.+?)(?:看|买|量|复诊|检查)", text)
    if m:
        pp = next((p for p in entities["persons"] if p in m.group(1)), None)
        pl2 = next((p for p in entities["places"] if p in m.group(3)), None)
        if pp:
            relations.append({"from": "persons:SELF", "to": f"persons:{pp}", "type": "emotion"})
        if pp and pl2:
            relations.append({"from": f"persons:{pp}", "to": f"places:{pl2}", "type": "space"})

    # 在...(打/做/看/...) → 空间关系
    m = re.search(r"在(.+?)(打|做|看|吃|聊|下|散|浇|听|读|买|锻炼|休息|起床)", text)
    if m:
        pl3 = next((p for p in entities["places"] if p in m.group(1)), None)
        ev3 = next((e for e in entities["events"] if e in m.group(0)), None)
        if pl3 and ev3:
            relations.append({"from": f"events:{ev3}", "to": f"places:{pl3}", "type": "space"})

    # 和/跟/与...一起 → 情感关系
    m = re.search(r"(和|跟|与)(.+?)(?:一起|聊天|散步|下棋|打牌|吃饭|逛街)", text)
    if m:
        pp = next((p for p in entities["persons"] if p in m.group(2)), None)
        if pp:
            relations.append({"from": "persons:SELF", "to": f"persons:{pp}", "type": "emotion"})

    # ...给/帮... → 情感关系（帮助行为）
    m = re.search(r"(.+?)(给|帮|替)(我|他|她|老伴|儿子|女儿)(.+?)(?:，|。|然后)", text)
    if m:
        helper = next((p for p in entities["persons"] if p in m.group(1)), None)
        receiver = next((p for p in entities["persons"] if p in m.group(3)), None)
        if helper and receiver and helper != receiver:
            relations.append({"from": f"persons:{helper}", "to": f"persons:{receiver}", "type": "emotion"})

    # ...带...去... → 情感+空间
    m = re.search(r"(.+?)带(我|他|她|老伴|儿子|女儿)?去(.+?)(?:看|买|检查|复诊|玩|逛)", text)
    if m:
        leader = next((p for p in entities["persons"] if p in m.group(1)), None)
        pl = next((p for p in entities["places"] if p in m.group(3)), None)
        if leader:
            relations.append({"from": "persons:SELF", "to": f"persons:{leader}", "type": "emotion"})
        if leader and pl:
            relations.append({"from": f"persons:{leader}", "to": f"places:{pl}", "type": "space"})

    # ...叫/让...来... → 情感关系
    m = re.search(r"(叫|让|请)(.+?)(?:来|过来|帮忙)(?:，|。|然后)", text)
    if m:
        pp = next((p for p in entities["persons"] if p in m.group(2)), None)
        if pp:
            relations.append({"from": "persons:SELF", "to": f"persons:{pp}", "type": "emotion"})

    # ...遇到/碰见... → 情感关系（偶遇）
    m = re.search(r"(遇到|碰见|遇见|碰到)(.+?)(?:，|。|然后|在|一起)", text)
    if m:
        pp = next((p for p in entities["persons"] if p in m.group(2)), None)
        if pp:
            relations.append({"from": "persons:SELF", "to": f"persons:{pp}", "type": "emotion"})

    # 自我节点与所有实体的初始连接
    for p in entities["persons"]:
        relations.append({"from": "persons:SELF", "to": f"persons:{p}", "type": "emotion"})
    for e in entities["events"]:
        relations.append({"from": "persons:SELF", "to": f"events:{e}", "type": "time"})
    for p in entities["places"]:
        relations.append({"from": "persons:SELF", "to": f"places:{p}", "type": "space"})
    for i in entities["items"]:
        relations.append({"from": "persons:SELF", "to": f"items:{i}", "type": "custom"})

    return relations


def parse_narrative(text: str, custom_words: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """主 NLP 管线：文本 → 实体 + 关系 + 异常 + 时间引用。custom_words 为用户自定义词典"""
    # 预处理
    text = text.replace("量了血压", "量血压")
    text = text.replace("聊了天", "聊天")

    entities = extract_entities(text, custom_words)
    anomalies = check_anomalies(text, entities)
    relations = _extract_relations(text, entities)
    anon_features = extract_anon_features(text)
    temporal_references = extract_temporal_references(text)

    return {
        "entities": entities,
        "relations": relations,
        "anomalies": anomalies,
        "tokens": fmm_segment(text, custom_words),
        "anon_features": anon_features,
        "temporal_references": temporal_references,
        "emotion": analyze_emotion(text),
    }
