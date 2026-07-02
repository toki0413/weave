import signal
import sys
import os
import socket

# Windows 控制台默认 GBK，强制 stdout/stderr 用 utf-8 输出中文
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 确保 backend 目录在 sys.path 中
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# 直接导入 app 对象，避免 frozen 模式下 uvicorn 用字符串重新 import 导致重复初始化
from app.main import app

server = None


def _find_free_port(default=8004):
    """优先用 CG_PORT；否则在 default..default+50 里找空闲端口"""
    env_port = os.environ.get("CG_PORT")
    if env_port:
        return int(env_port)
    for port in range(default, default + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    # 都被占用，让系统分配
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _graceful_shutdown(signum, frame):
    print(f"\n收到信号 {signum}，正在优雅关闭...")
    if server:
        server.should_exit = True


if __name__ == "__main__":
    import uvicorn
    port = _find_free_port()
    host = os.environ.get("CG_HOST", "127.0.0.1")
    print(f"\n=== Weave · 织忆 ===\n  URL:  http://{host}:{port}\n  Docs: http://{host}:{port}/docs (need DEBUG=1)\n", flush=True)
    config = uvicorn.Config(app, host=host, port=port, reload=False, log_level="warning")
    server = uvicorn.Server(config)
    signal.signal(signal.SIGINT, _graceful_shutdown)
    signal.signal(signal.SIGTERM, _graceful_shutdown)
    server.run()
