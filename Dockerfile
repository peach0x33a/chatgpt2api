ARG BUILDPLATFORM
ARG TARGETPLATFORM
ARG TARGETARCH

FROM --platform=$BUILDPLATFORM node:22-alpine AS web-build

WORKDIR /app/web

COPY web/package.json web/bun.lock ./
RUN npm install

COPY web ./
RUN npm run build


# 依赖在独立阶段编译：gcc / libpq-dev 只出现在这里，不进最终镜像。
FROM --platform=$TARGETPLATFORM python:3.13-slim AS python-deps

ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
# 用 BuildKit 缓存挂载 uv 的下载缓存，避免每次构建重新拉包。
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project


FROM --platform=$TARGETPLATFORM python:3.13-slim AS app

ARG TARGETPLATFORM
ARG TARGETARCH

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# 运行期只需要这些：
# - git: Git 存储后端需要
# - openssl: 加密备份需要（python 镜像只有 libssl，没有命令行）
# 装完顺手清掉 man/doc，git 的文档占了不少体积。
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    openssl \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /usr/share/doc/* /usr/share/man/* /usr/share/info/* \
    && rm -rf /var/lib/dpkg/info/*.md5sums

# 只搬虚拟环境，不搬 uv 缓存和编译工具链。
COPY --from=python-deps /app/.venv /app/.venv

COPY main.py ./
COPY config.json ./
COPY VERSION ./
COPY api ./api
COPY services ./services
COPY utils ./utils
COPY scripts ./scripts
COPY --from=web-build /app/web/dist ./web_dist

EXPOSE 80

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80", "--access-log"]
