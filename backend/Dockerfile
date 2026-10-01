# 一个进程同时提供 API 与静态原型站。
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Bangkok

WORKDIR /srv

# 先装依赖,让代码改动不失效 layer 缓存
COPY backend/requirements.txt /srv/backend/requirements.txt
RUN pip install --no-cache-dir -r /srv/backend/requirements.txt \
    && pip install --no-cache-dir 'psycopg[binary]>=3.2'

# 静态站(index.html / css / js)与数据层都要在镜像里 —— app.main 会把仓库根挂成静态目录
COPY index.html /srv/index.html
COPY css /srv/css
COPY js /srv/js
COPY data /srv/data
COPY config /srv/config
COPY p /srv/p
COPY sitemap.xml robots.txt privacy.html about.html admin.html favicon.svg feed.xml llms.txt llms-full.txt /srv/
COPY assets /srv/assets
COPY tools /srv/tools
COPY backend /srv/backend

RUN mkdir -p /srv/var

WORKDIR /srv/backend
EXPOSE 8000

# 首次启动:建表 + 载入词表与事实层(幂等,重启不会重复插)
# 启动时:建表 + 载入事实层(幂等)→ 重新导出派生产物(落地页里的 canonical 用 SITE_URL)
CMD ["sh", "-c", "python -m app.ingest && python -m app.export && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
