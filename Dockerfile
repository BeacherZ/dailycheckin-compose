# 自定义镜像：dailycheckin-plus —— 签到引擎 + 网页管理面板
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
# 构建期做一次自检：装不上、站点加载不出来就直接让构建失败，不要等运行时才发现。
# 顺序上必须先把 cwd 切走再删 /build —— 删掉当前工作目录会让 Python 的
# sys.path[0]（空串 = cwd）指向不存在的路径，pkgutil.extend_path 会直接抛 FileNotFoundError。
WORKDIR /build
COPY pyproject.toml setup.py requirements.txt ./
COPY dailycheckin ./dailycheckin
RUN set -eux; \
    pip install --no-cache-dir --upgrade pip setuptools wheel; \
    pip install --no-cache-dir -r requirements.txt; \
    pip install --no-cache-dir --no-deps .; \
    python -c "import dailycheckin, dailycheckin.configs as c; print('引擎自检通过，已加载', len(c.checkin_map), '个站点模块')"; \
    grep -q 'web-interface/newlist' "$(python -c 'import dailycheckin.bilibili.main as m; print(m.__file__)')"; \
    echo 'B 站接口修复已生效'; \
    python -c "import pathlib as p; s = p.Path('dailycheckin/main.py').read_text(encoding='utf-8'); assert 'PROJECT_URL' in s and 'PROJECT_NAME' in s, 'main.py 的引擎元信息没跟上'; print('引擎元信息自检通过')"; \
    python -c "import dailycheckin.utils.message as m; assert m.PROJECT_NAME == 'dailycheckin-plus', m.PROJECT_NAME; assert m.NOTICE_TITLE.endswith('每日签到') and m.PROJECT_NAME in m.NOTICE_TITLE, m.NOTICE_TITLE; assert m.PROJECT_URL.endswith('/dailycheckin-plus'), m.PROJECT_URL; print('通知模块自检通过：', m.NOTICE_TITLE, m.PROJECT_URL)"; \
    echo '通知模块修复已生效（恒定一条 + 标题带项目名 + 本项目地址）'; \
    cd / && rm -rf /build

# ---------- 2) 放入网页管理面板（纯标准库实现，不需要安装）----------
WORKDIR ${DC_HOME}
COPY panel ./panel
# 网页里的品牌字样也断言一次：装进镜像的必须是改名后的版本，
# 别出现「源码改了名字、镜像里还是老页面」这种事。
RUN set -eux; \
    grep -q 'dailycheckin-plus' panel/static/index.html; \
    grep -q 'dailycheckin-plus' panel/paths.py; \
    echo '面板品牌自检通过'

# 溯源信息：面板「设置 → 环境信息」里显示的引擎版本/上游提交就来自这里，
# 由 tools/sync_upstream.py 在同步上游时生成。
COPY UPSTREAM.json ./UPSTREAM.json
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 8080
VOLUME ["/dailycheckin/config", "/dailycheckin/cron", "/dailycheckin/logs", "/dailycheckin/data"]

HEALTHCHECK --interval=30s --timeout=6s --start-period=15s --retries=3 \
    CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PANEL_PORT','8080')+'/api/health',timeout=5)" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
