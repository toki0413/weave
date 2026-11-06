#!/bin/sh
# 容器入口：修正挂载卷属主后降权为 appuser 执行。
# 背景：compose 的 named volume 首次创建属主为 root，非 root 进程无法写入;
# 以 root 仅做 chown，随后立即 exec gosu 降权，主进程始终非 root。
set -e

if [ "$(id -u)" = "0" ]; then
    mkdir -p /app/uploads /app/logs /app/data
    chown -R appuser:appuser /app/uploads /app/logs /app/data 2>/dev/null || true
    exec gosu appuser "$@"
fi

exec "$@"
