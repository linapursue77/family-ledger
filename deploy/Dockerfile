# 家庭财务通 · 后端镜像
#
# 构建语境（context）必须是仓库根目录：
#   docker build -f deploy/Dockerfile -t family-ledger-web .
# 前端产物 frontend/dist 会被一起打进去（供 SERVE_WEB=1 单端口模式使用）；
# 用 nginx 发静态时可以忽略它。
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

# PyMySQL 是纯 Python 实现，不需要编译 mysqlclient，所以无需装任何编译依赖
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
# 公司内网/国内服务器拉 PyPI 慢时，构建期覆盖：--build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
# （docker-compose.yml 已把它接出来，写进 deploy/.env 即可，不用改 Dockerfile）
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install -r /app/backend/requirements.txt -i ${PIP_INDEX_URL}

COPY backend /app/backend
COPY frontend/dist /app/frontend/dist
COPY deploy/entrypoint.sh /app/deploy/entrypoint.sh
RUN chmod +x /app/deploy/entrypoint.sh \
    && mkdir -p /app/backend/media /app/backend/logs

WORKDIR /app/backend
EXPOSE 8000

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
# 2 workers 对两口之家绰绰有余；账单解析是 django-q 异步任务，不占请求线程
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
