# === Stage 1: builder (含编译依赖) ===
FROM python:3.12-slim AS builder

# 切到 aliyun mirror 避免 deb.debian.org:80 限流
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources

WORKDIR /build

# 系统依赖 (编译 + audio 处理)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ ffmpeg libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir --target=/install .

# === Stage 2: runtime (slim, 60%+ 体积小) ===
FROM python:3.12-slim AS runtime

# 切到 aliyun mirror 避免 deb.debian.org:80 限流
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources

# 运行时最小系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg tini \
    && rm -rf /var/lib/apt/lists/*

# 从 builder 复制已安装的 Python 包
COPY --from=builder /install /usr/local/lib/python3.12/site-packages

# 复制源码
WORKDIR /app
COPY src/ /app/src/
COPY config/ /app/config/
COPY prompts/ /app/prompts/
COPY pyproject.toml /app/

# tini 0 号信号处理 (PID 1 收 SIGTERM 优雅退出)
ENTRYPOINT ["/usr/bin/tini", "--"]

# 默认命令 (CLI mode)
CMD ["python", "-m", "builderpulse", "run"]
