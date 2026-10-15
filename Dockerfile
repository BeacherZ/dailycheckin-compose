# 自定义镜像：签到引擎 + 网页管理面板
# 引擎来自 https://github.com/Sitoi/dailycheckin（MIT），本项目在其之上加了管理后台
FROM python:3.9-slim

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    TZ=Asia/Shanghai \
    DC_HOME=/dailycheckin \
    PANEL_HOST=0.0.0.0 \
    PANEL_PORT=8080

# cron 负责定时签到，tini 负责正确回收子进程
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends cron tzdata tini; \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime; \
    echo "$TZ" > /etc/timezone; \
    rm -rf /var/lib/apt/lists/*

# ---------- 1) 安装签到引擎（含 B 站接口修复）----------
WORKDIR /build
COPY pyproject.toml setup.py requirements.txt ./
COPY dailycheckin ./dailycheckin
RUN set -eux; \
    pip install --no-cache-dir --upgrade pip setuptools wheel; \
    pip install --no-cache-dir -r requirements.txt; \
    pip install --no-cache-dir --no-deps .; \
    rm -rf /build; \
    # 构建期自检：装不上、站点加载不出来就直接让构建失败，不要等到运行才发现
    python -c "import dailycheckin, dailycheckin.configs as c; print('引擎自检通过，已加载', len(c.checkin_map), '个站点模块')"; \
    grep -q 'web-interface/newlist' "$(python -c 'import dailycheckin.bilibili.main as m; print(m.__file__)')"; \
    echo 'B 站接口修复已生效'

# ---------- 2) 放入网页管理面板（纯标准库实现，不需要安装）----------
WORKDIR ${DC_HOME}
COPY panel ./panel
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 8080
VOLUME ["/dailycheckin/config", "/dailycheckin/cron", "/dailycheckin/logs", "/dailycheckin/data"]

HEALTHCHECK --interval=30s --timeout=6s --start-period=15s --retries=3 \
    CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PANEL_PORT','8080')+'/api/health',timeout=5)" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
