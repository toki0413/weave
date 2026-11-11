"""全量 GET 端点冒烟：不允许任何端点一调用就 500

第 8 条会话的 NameError 说明单点测试容易漏掉整条路径。这里用更低成本的方式
兜底：把 app 上所有 GET 路由按"路径参数填 UUID"的方式各调一次，只断言
不出现 5xx。404/403/422 都算正常（资源不存在或权限不足），500 才是缺陷。

新增 GET 端点会自动纳入本测试，不需要维护清单。
"""
import re

import pytest

# 流式响应会挂住测试客户端；健康检查与指标另有专门用例
_SKIP = {"/events", "/metrics"}


def _iter_get_routes():
    """从 OpenAPI schema 枚举 GET 路由。

    不走 app.routes：FastAPI 0.162 把 include_router 的结果包装成
    _IncludedRouter，路由树不再是扁平的 APIRoute 列表，遍历会漏掉全部
    业务路由。schema 是稳定契约，不受内部实现变化影响。
    """
    from app.main import app, v1_app

    for path, ops in v1_app.openapi().get("paths", {}).items():
        if "get" in ops:
            yield "/api/v1" + path
    for path, ops in app.openapi().get("paths", {}).items():
        if "get" in ops and path not in _SKIP:
            yield path


def test_no_get_endpoint_returns_500(client, auth_headers):
    headers = auth_headers["headers"]
    failures = []

    for path in _iter_get_routes():
        concrete = re.sub(r"\{[^}]+\}", "00000000-0000-0000-0000-000000000000", path)
        try:
            r = client.get(concrete, headers=headers)
        except Exception as e:  # 连接被端点自身关闭等异常同样视为缺陷
            failures.append((path, "EXC", str(e)[:80]))
            continue
        if r.status_code >= 500:
            failures.append((path, r.status_code, r.text[:120]))

    assert not failures, "以下 GET 端点返回 5xx：\n" + "\n".join(
        f"  {p} -> {code} {body}" for p, code, body in failures
    )


def test_get_routes_are_discovered():
    """防止正则/枚举逻辑写坏导致测试空转"""
    paths = list(_iter_get_routes())
    assert len(paths) >= 15, f"只发现 {len(paths)} 个带参数的 GET 路由，枚举逻辑可能失效"
