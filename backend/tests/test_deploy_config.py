"""部署编排与容器配置的交付级校验

这些配置无法在单元测试中真实起服务，但可以用静态断言锁住
"改回去就出事故"的关键属性：暴露面、必填密钥、健康检查、
反代的安全头与 SSE 缓冲策略、依赖分层。
"""
from pathlib import Path

import pytest
import yaml

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------- 反向代理 ----------

def test_nginx_conf_exists_and_is_mounted():
    conf = REPO_ROOT / "nginx.conf"
    assert conf.exists(), "compose 挂载的 nginx.conf 必须存在，否则 with-nginx 部署直接失败"
    compose = yaml.safe_load(_read(REPO_ROOT / "docker-compose.yml"))
    volumes = compose["services"]["nginx"]["volumes"]
    assert any("nginx.conf" in v for v in volumes)


def test_nginx_sse_disables_buffering():
    body = _read(REPO_ROOT / "nginx.conf")
    sse_block = body.split("location = /events")[1].split("location")[0]
    assert "proxy_buffering off" in sse_block
    assert "proxy_read_timeout 1h" in sse_block


def test_nginx_sets_security_headers():
    body = _read(REPO_ROOT / "nginx.conf")
    for header in (
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
        "Content-Security-Policy",
        "Permissions-Policy",
    ):
        assert header in body, f"缺少安全响应头: {header}"
    assert "server_tokens off" in body


def test_nginx_blocks_metrics_and_uploads_from_public():
    body = _read(REPO_ROOT / "nginx.conf")
    metrics_block = body.split("location = /metrics")[1].split("location")[0]
    assert "deny all" in metrics_block
    uploads_block = body.split("location /uploads/")[1].split("location")[0]
    assert "deny all" in uploads_block


def test_nginx_limits_upload_size_and_has_spa_fallback():
    body = _read(REPO_ROOT / "nginx.conf")
    assert "client_max_body_size" in body
    assert "try_files $uri $uri/ /index.html" in body


# ---------- 编排暴露面 ----------

@pytest.fixture(scope="module")
def compose():
    return yaml.safe_load(_read(REPO_ROOT / "docker-compose.yml"))


def test_compose_does_not_publish_database_ports(compose):
    """数据库与缓存不得映射到宿主机公网端口"""
    for svc in ("postgres", "redis"):
        assert "ports" not in compose["services"][svc], (
            f"{svc} 不应发布端口；容器网络内访问即可")


def test_compose_backend_port_bound_to_loopback(compose):
    ports = compose["services"]["backend"]["ports"]
    assert all(p.startswith("127.0.0.1:") for p in ports), (
        "backend 端口只应绑定回环，对外流量走 nginx")


def test_compose_requires_critical_secrets(compose):
    env = compose["services"]["backend"]["environment"]
    joined = " ".join(env)
    for var in ("CG_JWT_SECRET", "CG_PG_PASSWORD", "CG_REDIS_PASSWORD"):
        assert f"{var}:?" in joined, f"{var} 必须以 ${var}:? 形式强制注入"


def test_compose_redis_requires_password(compose):
    cmd = compose["services"]["redis"]["command"]
    assert any("--requirepass" in str(c) for c in cmd)


def test_compose_services_have_healthchecks(compose):
    for svc in ("backend", "postgres", "redis"):
        assert "healthcheck" in compose["services"][svc], f"{svc} 缺少健康检查"
    assert compose["services"]["postgres"]["healthcheck"]["test"]
    # nginx 必须等 backend 就绪再启动
    dep = compose["services"]["nginx"]["depends_on"]["backend"]
    assert dep["condition"] == "service_healthy"


def test_compose_log_rotation_configured(compose):
    for svc in ("backend", "postgres", "redis"):
        logging_cfg = compose["services"][svc].get("logging", {})
        opts = logging_cfg.get("options", {})
        assert opts.get("max-size"), f"{svc} 未限制日志体积，长跑会打满磁盘"


# ---------- 容器镜像 ----------

def test_dockerfile_has_healthcheck_and_entrypoint():
    body = _read(BACKEND_DIR / "Dockerfile")
    assert "HEALTHCHECK" in body
    assert "docker-entrypoint.sh" in body
    assert (BACKEND_DIR / "docker-entrypoint.sh").exists()


def test_container_drops_root_privileges():
    body = _read(BACKEND_DIR / "Dockerfile")
    entry = _read(BACKEND_DIR / "docker-entrypoint.sh")
    assert "appuser" in body
    assert "gosu appuser" in entry, "入口必须以非 root 用户执行主进程"


def test_dockerignore_excludes_secrets_and_data():
    body = _read(BACKEND_DIR / ".dockerignore")
    for pattern in (".env", "uploads/", "*.db", "tests/"):
        assert pattern in body, f".dockerignore 必须排除 {pattern}"


# ---------- 依赖分层 ----------

def test_production_requirements_exclude_test_tools():
    body = _read(BACKEND_DIR / "requirements.txt")
    for pkg in ("pytest", "hypothesis", "sphinx"):
        assert pkg not in body, f"生产依赖不应包含 {pkg}"


def test_dev_requirements_include_test_tools():
    body = _read(BACKEND_DIR / "requirements-dev.txt")
    assert "-r requirements.txt" in body
    for pkg in ("pytest", "hypothesis", "sphinx"):
        assert pkg in body


def test_ci_installs_dev_requirements():
    body = _read(REPO_ROOT / ".github" / "workflows" / "ci.yml")
    assert "requirements-dev.txt" in body


def test_ci_security_scan_actually_blocks():
    """静态扫描步骤不得用 `|| true` 吞掉失败，否则等于没有门禁"""
    body = _read(REPO_ROOT / ".github" / "workflows" / "ci.yml")
    bandit_lines = [ln for ln in body.splitlines() if "bandit -r" in ln]
    assert bandit_lines, "CI 缺少 bandit 扫描步骤"
    assert all("|| true" not in ln for ln in bandit_lines), (
        "bandit 步骤不得附加 || true，中危及以上必须阻断构建")


# ---------- 部署说明完整性 ----------

def test_env_example_lists_required_variables():
    body = _read(REPO_ROOT / ".env.example")
    for var in ("CG_PG_PASSWORD", "CG_REDIS_PASSWORD", "CG_JWT_SECRET", "CG_KMS_MASTER_KEY"):
        assert var in body, f".env.example 未说明 {var}"


def test_env_example_kms_key_format_matches_implementation():
    """KMS 段必须写 base64(32B)；EnvKMS 不接受十六进制串"""
    body = _read(REPO_ROOT / ".env.example")
    kms_block = body.split("KMS 主密钥包装")[1].split("---- 跨域")[0]
    assert "base64" in kms_block.lower()
    assert "rand -hex" not in kms_block
