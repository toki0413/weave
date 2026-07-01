import signal
import sys
import os

# 确保 backend 目录在 sys.path 中
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)


def _graceful_shutdown(signum, frame):
    print(f"\n收到信号 {signum}，正在优雅关闭...")
    if server:
        server.should_exit = True


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("CG_PORT", "8004"))
    config = uvicorn.Config("app.main:app", host=os.environ.get("CG_HOST", "127.0.0.1"), port=port, reload=False, log_level="warning")
    server = uvicorn.Server(config)
    signal.signal(signal.SIGINT, _graceful_shutdown)
    signal.signal(signal.SIGTERM, _graceful_shutdown)
    server.run()
