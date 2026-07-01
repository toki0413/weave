"""认知评估量表定义：MMSE 简易精神状态检查 + AD8 早期痴呆筛查"""

# ========== MMSE 简易精神状态检查 ==========
# 总分 30 分，<24 分提示认知障碍
# 7 个维度：定向力、记忆力、注意力计算、回忆、语言、复制图形、阅读理解
MMSE_QUESTIONS = [
    # 定向力 - 时间定向（5分）
    {
        "id": "mmse_1",
        "text": "请回答：今天是哪一年？几月？几日？星期几？什么季节？",
        "dimension": "定向力",
        "max_score": 5,
        "options": [
            {"score": 0, "label": "全部错误"},
            {"score": 1, "label": "答对1项"},
            {"score": 2, "label": "答对2项"},
            {"score": 3, "label": "答对3项"},
            {"score": 4, "label": "答对4项"},
            {"score": 5, "label": "全部正确"},
        ],
    },
    # 定向力 - 地点定向（5分）
    {
        "id": "mmse_2",
        "text": "请回答：我们在哪个省？哪个城市？哪个区？哪家医院/机构？第几层？",
        "dimension": "定向力",
        "max_score": 5,
        "options": [
            {"score": 0, "label": "全部错误"},
            {"score": 1, "label": "答对1项"},
            {"score": 2, "label": "答对2项"},
            {"score": 3, "label": "答对3项"},
            {"score": 4, "label": "答对4项"},
            {"score": 5, "label": "全部正确"},
        ],
    },
    # 记忆力 - 即刻记忆（3分）
    {
        "id": "mmse_3",
        "text": "我说三个词，请您记住：皮球、国旗、树木。请重复一遍。",
        "dimension": "记忆力",
        "max_score": 3,
        "options": [
            {"score": 0, "label": "全部记不住"},
            {"score": 1, "label": "记住1个"},
            {"score": 2, "label": "记住2个"},
            {"score": 3, "label": "全部记住"},
        ],
    },
    # 注意力计算（5分）
    {
        "id": "mmse_4",
        "text": "从100开始连续减7：100-7=？再减7？再减7？再减7？再减7？（93, 86, 79, 72, 65）",
        "dimension": "注意力计算",
        "max_score": 5,
        "options": [
            {"score": 0, "label": "全部错误"},
            {"score": 1, "label": "算对1个"},
            {"score": 2, "label": "算对2个"},
            {"score": 3, "label": "算对3个"},
            {"score": 4, "label": "算对4个"},
            {"score": 5, "label": "全部正确"},
        ],
    },
    # 回忆 - 延迟回忆（3分）
    {
        "id": "mmse_5",
        "text": "刚才让您记住的三个词是什么？",
        "dimension": "回忆",
        "max_score": 3,
        "options": [
            {"score": 0, "label": "全部忘记"},
            {"score": 1, "label": "想起1个"},
            {"score": 2, "label": "想起2个"},
            {"score": 3, "label": "全部想起"},
        ],
    },
    # 语言 - 命名（2分）
    {
        "id": "mmse_6",
        "text": "请说出这两样东西的名称（出示手表、铅笔）",
        "dimension": "语言",
        "max_score": 2,
        "options": [
            {"score": 0, "label": "全部错误"},
            {"score": 1, "label": "答对1个"},
            {"score": 2, "label": "全部正确"},
        ],
    },
    # 语言 - 复述（1分）
    {
        "id": "mmse_7",
        "text": "请跟我念：四十四只石狮子",
        "dimension": "语言",
        "max_score": 1,
        "options": [
            {"score": 0, "label": "错误"},
            {"score": 1, "label": "正确"},
        ],
    },
    # 语言 - 三步指令（3分）
    {
        "id": "mmse_8",
        "text": "请按我说的做：用右手拿这张纸，对折后放在大腿上",
        "dimension": "语言",
        "max_score": 3,
        "options": [
            {"score": 0, "label": "全部错误"},
            {"score": 1, "label": "完成1步"},
            {"score": 2, "label": "完成2步"},
            {"score": 3, "label": "全部完成"},
        ],
    },
    # 复制图形（1分）
    {
        "id": "mmse_9",
        "text": "请照着这个图形画下来（两个重叠的五边形）",
        "dimension": "复制图形",
        "max_score": 1,
        "options": [
            {"score": 0, "label": "错误"},
            {"score": 1, "label": "正确"},
        ],
    },
    # 阅读理解 - 阅读（1分）
    {
        "id": "mmse_10",
        "text": "请读这句话并照着做：闭上您的眼睛",
        "dimension": "阅读理解",
        "max_score": 1,
        "options": [
            {"score": 0, "label": "错误"},
            {"score": 1, "label": "正确"},
        ],
    },
    # 阅读理解 - 书写（1分）
    {
        "id": "mmse_11",
        "text": "请写一个完整的句子（要有主语和谓语）",
        "dimension": "阅读理解",
        "max_score": 1,
        "options": [
            {"score": 0, "label": "错误"},
            {"score": 1, "label": "正确"},
        ],
    },
]

# ========== AD8 早期痴呆筛查 ==========
# 8 个问题，每题 0-2 分，总分 ≥2 分提示需进一步评估
AD8_QUESTIONS = [
    {
        "id": "ad8_1",
        "text": "和过去相比，患者的判断力是否出现问题（如做决定困难、容易受骗）？",
        "dimension": "判断力",
        "max_score": 2,
        "options": [
            {"score": 0, "label": "没有变化"},
            {"score": 1, "label": "有变化，但不频繁"},
            {"score": 2, "label": "有变化，且较频繁"},
        ],
    },
    {
        "id": "ad8_2",
        "text": "和过去相比，患者对以前感兴趣的事情或爱好是否缺乏兴趣？",
        "dimension": "兴趣爱好",
        "max_score": 2,
        "options": [
            {"score": 0, "label": "没有变化"},
            {"score": 1, "label": "有变化，但不频繁"},
            {"score": 2, "label": "有变化，且较频繁"},
        ],
    },
    {
        "id": "ad8_3",
        "text": "和过去相比，患者是否经常重复相同的问题、故事或陈述？",
        "dimension": "重复问题",
        "max_score": 2,
        "options": [
            {"score": 0, "label": "没有变化"},
            {"score": 1, "label": "有变化，但不频繁"},
            {"score": 2, "label": "有变化，且较频繁"},
        ],
    },
    {
        "id": "ad8_4",
        "text": "和过去相比，患者学习使用小工具、电器或新设备是否有困难？",
        "dimension": "学习新事物",
        "max_score": 2,
        "options": [
            {"score": 0, "label": "没有变化"},
            {"score": 1, "label": "有变化，但不频繁"},
            {"score": 2, "label": "有变化，且较频繁"},
        ],
    },
    {
        "id": "ad8_5",
        "text": "和过去相比，患者是否忘记正确的年月、日期或重要的约会？",
        "dimension": "记忆日期",
        "max_score": 2,
        "options": [
            {"score": 0, "label": "没有变化"},
            {"score": 1, "label": "有变化，但不频繁"},
            {"score": 2, "label": "有变化，且较频繁"},
        ],
    },
    {
        "id": "ad8_6",
        "text": "和过去相比，患者处理复杂的财务问题（如报税、理财）是否有困难？",
        "dimension": "处理财务",
        "max_score": 2,
        "options": [
            {"score": 0, "label": "没有变化"},
            {"score": 1, "label": "有变化，但不频繁"},
            {"score": 2, "label": "有变化，且较频繁"},
        ],
    },
    {
        "id": "ad8_7",
        "text": "和过去相比，患者是否难以记住与他人的约定或日常安排？",
        "dimension": "记住约会",
        "max_score": 2,
        "options": [
            {"score": 0, "label": "没有变化"},
            {"score": 1, "label": "有变化，但不频繁"},
            {"score": 2, "label": "有变化，且较频繁"},
        ],
    },
    {
        "id": "ad8_8",
        "text": "和过去相比，患者在处理日常事务（如购物、做饭、打扫）时是否出现困难？",
        "dimension": "日常事务",
        "max_score": 2,
        "options": [
            {"score": 0, "label": "没有变化"},
            {"score": 1, "label": "有变化，但不频繁"},
            {"score": 2, "label": "有变化，且较频繁"},
        ],
    },
]

# 量表元信息
# 注意：MMSE/AD8 是临床筛查工具，有练习效应，不能每日使用
# 建议频率：初次建档 + 每季度复评，由医生/家属发起
SCALES = {
    "mmse": {
        "id": "mmse",
        "name": "简易精神状态检查（MMSE）",
        "description": "国际通用的认知功能筛查工具，覆盖定向、记忆、注意、语言等多个维度，总分30分。",
        "total_score": 30,
        "duration_min": 10,
        "questions": MMSE_QUESTIONS,
        "recommended_frequency": "每季度一次",
        "frequency_reason": "MMSE有练习效应，频繁测试会导致分数虚高，失去筛查意义",
        "who_fills": "由医生或受过培训的家属提问，老人作答",
    },
    "ad8": {
        "id": "ad8",
        "name": "早期痴呆筛查（AD8）",
        "description": "由知情者填写，用于早期发现认知功能变化的筛查工具，总分16分，≥2分提示需进一步评估。",
        "total_score": 16,
        "duration_min": 5,
        "questions": AD8_QUESTIONS,
        "recommended_frequency": "每季度一次",
        "frequency_reason": "AD8关注的是变化趋势，需要间隔足够长才能观察到有意义的改变",
        "who_fills": "由了解老人日常的家属填写，不是老人自答",
    },
}


def get_scale(scale_id):
    """根据 id 取量表定义，不存在返回 None"""
    return SCALES.get(scale_id)


def list_scales():
    """返回量表列表（不含题目详情，减少传输量）"""
    return [
        {
            "id": s["id"],
            "name": s["name"],
            "description": s["description"],
            "total_score": s["total_score"],
            "duration_min": s["duration_min"],
            "question_count": len(s["questions"]),
            "recommended_frequency": s.get("recommended_frequency", ""),
            "frequency_reason": s.get("frequency_reason", ""),
            "who_fills": s.get("who_fills", ""),
        }
        for s in SCALES.values()
    ]


def correlate_scale_with_graph(scale_type, scale_score, graph_metrics):
    """
    量表分数与图谱指标的关联分析。
    不是让老人每天答题，而是看图谱趋势是否与定期量表结果一致。
    graph_metrics: dict，包含 connectivity/clustering/density/avgPathLen/smallWorld 等
    返回: list of {dimension, scale_finding, graph_finding, consistency, suggestion}
    """
    findings = []

    if scale_type == "mmse":
        # 定向力 vs 图谱地点节点
        if scale_score < 24:
            findings.append({
                "dimension": "定向力",
                "scale_finding": "MMSE定向力得分偏低（{}分/30分）".format(scale_score),
                "graph_finding": "图谱中地点类节点占比 {}%，平均路径长度 {}".format(
                    round(graph_metrics.get("density", 0) * 100, 1),
                    round(graph_metrics.get("avgPathLen", 0), 2)
                ),
                "consistency": "需关注" if graph_metrics.get("avgPathLen", 0) > 3 else "尚可",
                "suggestion": "定向力下降可能与空间记忆网络稀疏有关，建议关注老人对地点的叙述频率",
            })
        # 记忆力 vs 图谱连通度
        findings.append({
            "dimension": "记忆力",
            "scale_finding": "MMSE总分 {} 分".format(scale_score),
            "graph_finding": "图谱连通度 {}%，聚类系数 {}%".format(
                round(graph_metrics.get("connectivity", 0) * 100),
                round(graph_metrics.get("clustering", 0) * 100)
            ),
            "consistency": "一致" if (scale_score >= 27 and graph_metrics.get("connectivity", 0) > 0.7) or
                                      (scale_score < 24 and graph_metrics.get("connectivity", 0) < 0.5) else "部分一致",
            "suggestion": "图谱连通度反映记忆网络完整性，与MMSE记忆力维度应呈正相关",
        })

    elif scale_type == "ad8":
        if scale_score >= 2:
            findings.append({
                "dimension": "整体认知变化",
                "scale_finding": "AD8得分 {} 分，提示需进一步评估".format(scale_score),
                "graph_finding": "近期图谱健康度趋势：小世界系数 {}".format(
                    round(graph_metrics.get("smallWorld", 0), 2)
                ),
                "consistency": "需关注" if graph_metrics.get("smallWorld", 0) < 1.0 else "尚可",
                "suggestion": "AD8反映家属观察到的变化，应与图谱趋势对照分析",
            })

    return findings


def interpret_mmse(score):
    """MMSE 分数解读：27-30正常，24-26轻度，18-23中度，<18重度"""
    if score >= 27:
        return "正常", "认知功能正常，建议定期复查"
    elif score >= 24:
        return "轻度认知障碍", "存在轻度认知障碍，建议进一步评估并定期随访"
    elif score >= 18:
        return "中度认知障碍", "存在中度认知障碍，建议尽快就医进行详细评估"
    else:
        return "重度认知障碍", "存在重度认知障碍，需立即就医并制定照护方案"


def interpret_ad8(score):
    """AD8 分数解读：0-1正常，2+需进一步评估"""
    if score <= 1:
        return "正常", "未发现明显认知功能变化，建议定期复查"
    else:
        return "需进一步评估", "认知功能存在变化，建议尽快到记忆门诊进行详细评估"


def interpret(scale_id, score):
    """根据量表类型返回 (level, detail)"""
    if scale_id == "mmse":
        return interpret_mmse(score)
    elif scale_id == "ad8":
        return interpret_ad8(score)
    return "未知", "无法解读该量表"
