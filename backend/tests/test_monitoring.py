"""S1 监控指标接线测试

覆盖：STT 计数器按 provider/result 递增、漏录 job 成功时间戳 Gauge、
monitoring/ 配置文件语法与规则引用一致性。
"""
import pytest
from prometheus_client import REGISTRY

from app.routers.stt import record_stt_result, STT_REQUESTS


def _sample(name, labels):
    return REGISTRY.get_sample_value(name, labels)


def test_record_stt_result_increments_counter():
    provider = "unit-test-provider"
    labels_ok = {"provider": provider, "result": "ok"}
    labels_fail = {"provider": provider, "result": "fail"}
    before_ok = _sample("stt_requests_total", labels_ok) or 0
    before_fail = _sample("stt_requests_total", labels_fail) or 0

    record_stt_result(provider, True)
    record_stt_result(provider, False)
    record_stt_result(provider, False)

    assert _sample("stt_requests_total", labels_ok) == before_ok + 1
    assert _sample("stt_requests_total", labels_fail) == before_fail + 2


def test_missed_checkin_run_sets_gauge():
    import time as _time
    from app.services import missed_checkin_job

    before = REGISTRY.get_sample_value(
        "missed_checkin_last_success_timestamp") or 0
    missed_checkin_job.run_once()
    after = REGISTRY.get_sample_value("missed_checkin_last_success_timestamp")
    assert after >= before
    assert after <= _time.time() + 1


def test_monitoring_configs_are_consistent():
    """prometheus.yml 引用的规则文件存在，规则里引用的指标由后端导出"""
    yaml = pytest.importorskip("yaml")
    from pathlib import Path
    mon = Path(__file__).resolve().parents[2] / "monitoring"

    prom = yaml.safe_load((mon / "prometheus.yml").read_text(encoding="utf-8"))
    assert prom["scrape_configs"][0]["metrics_path"] == "/metrics"
    rule_files = prom["rule_files"]
    for rf in rule_files:
        assert (mon / Path(rf).name).exists(), f"规则文件缺失: {rf}"

    rules = yaml.safe_load((mon / "alert_rules.yml").read_text(encoding="utf-8"))
    expr_text = "\n".join(
        r["expr"] for g in rules["groups"] for r in g["rules"])
    # 后端确实导出这三条规则引用的指标
    assert "http_requests_total" in expr_text
    assert "stt_requests_total" in expr_text
    assert "missed_checkin_last_success_timestamp" in expr_text
