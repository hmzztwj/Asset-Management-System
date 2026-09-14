# ---- 资产管理系统 生产部署镜像 ----
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 先装依赖，充分利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝项目代码
COPY . .

RUN sed -i 's/\r$//' docker-entrypoint.sh \
    && chmod +x docker-entrypoint.sh \
    && mkdir -p /app/data /app/backup

EXPOSE 8000

# 容器健康检查：探测登录页是否可访问（内网部署不需要 curl，用 Python 标准库）
HEALTHCHECK --interval=60s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/login/', timeout=4).status == 200 else 1)"

ENTRYPOINT ["./docker-entrypoint.sh"]
