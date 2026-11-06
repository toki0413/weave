# ============ 织忆 · 认知花园 后端镜像 ============
# 两阶段构建：构建期编译依赖，运行期只带产物；以非 root 用户运行。

FROM python:3.11-slim AS builder

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ---- 运行镜像 ----
FROM python:3.11-slim AS runtime

# gosu：以 root 完成卷属主修正后降权执行（named volume 首次挂载属主为 root）
RUN apt-get update && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r appuser && useradd -r -g appuser -u 10001 -m appuser

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/home/appuser/.local/bin:$PATH \
    CG_LOG_DIR=/app/logs

COPY --from=builder /root/.local /home/appuser/.local
COPY . .

RUN mkdir -p /app/uploads /app/logs \
    && chown -R appuser:appuser /app /home/appuser/.local

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8004

# 就绪探针：/health 返回 200 即进程可服务（内部含 DB 连通判断）
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8004/health', timeout=4).status == 200 else 1)"

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "run.py"]
