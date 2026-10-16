# dailycheckin-plus

**给 [Sitoi/dailycheckin](https://github.com/Sitoi/dailycheckin) 加了一个网页管理后台。一条 `docker compose up -d` 跑起来，浏览器里点几下就配好了。**

[![build](https://github.com/BeacherZ/dailycheckin-plus/actions/workflows/build.yml/badge.svg)](https://github.com/BeacherZ/dailycheckin-plus/actions/workflows/build.yml)
[![ghcr](https://img.shields.io/badge/ghcr.io-dailycheckin--plus-2496ed?logo=docker&logoColor=white)](https://github.com/BeacherZ/dailycheckin-plus/pkgs/container/dailycheckin-plus)
![license](https://img.shields.io/badge/license-MIT-green)

签到引擎沿用上游原项目（MIT，已内置 B 站接口修复），**网页后台是本项目新增的**。

![后台效果图](index.png)

*卡片视图：一行 4 个站点，顶栏是签到概况统计。*

## 它解决什么

| 上游的做法 | 现在 |
|---|---|
| 手改 `config.json`，少个逗号就整个不跑 | 网页填表单，点保存，写错了直接告诉你错哪 |
| cookie 必须用 `; `（分号**加空格**）分隔 | 粘什么格式都认，自动规范化成引擎要的形态 |
| cookie 过期了没提醒，只能翻日志猜 | 卡片上直接标 ✅ 有效 / ❌ 失效 |
| 不知道某个站到底要哪几个字段 | 每个站点标出必填字段，缺了高亮 |
| 改定时时间要进容器改文件 | 网页选周期，保存即生效 |
| 每次签到推送一堆消息，一条一个站 | **恒定只推一条**，带标题和分隔行 |

## 快速开始

在任意目录新建 `docker-compose.yml`：

```yaml
services:
  dailycheckin:
    image: ghcr.io/beacherz/dailycheckin-plus:latest
    container_name: dailycheckin
    restart: unless-stopped
    ports:
      - 8080:8080
    volumes:
      - ./config:/dailycheckin/config
      - ./cron:/dailycheckin/cron
      - ./logs:/dailycheckin/logs
      - ./data:/dailycheckin/data
    environment:
      - TZ=Asia/Shanghai
```

```bash
docker compose up -d
```

浏览器打开 `http://你的地址:8080`，第一次会引导你设置后台账号密码。

**升级**：`docker compose pull && docker compose up -d`。
设置页最下方的「关于本项目」显示当前构建的提交，并跟 GitHub 上 `main` 的最新提交比对 —— 有新提交就标出来，鼠标悬停能看到更新命令。

不用 compose 的话，拿同一个镜像挂上这**四个目录**用 `docker run` 起也行；Windows 把 `$PWD` 换成 `${PWD}`，群晖 / 威联通把上面这段贴进 Container Manager / Container Station 的「项目」。

### 数据放在哪

| 目录 | 内容 |
|---|---|
| `config/` | `config.json`，站点与 cookie（与上游格式完全一致） |
| `cron/` | 定时任务定义 |
| `logs/` | 签到日志 |
| `data/` | 后台账号凭据、校验状态、运行历史、配置备份 |

删容器不丢数据，备份把这四个目录一起拷走。

## 网页后台

- **站点列表**：16 个站点铺成卡片（一行 4 张，右上角可切列表视图），带官网 LOGO、状态色条与徽章；顶部搜索按站名或 `KEY` 过滤（快捷键 `/`），可按分类筛选、「只看待配置」；排序默认「已配置优先」；窗口变窄自动降密度；跟随系统深浅色。登录过的人再打开**直接进管理界面**，不会先闪一屏登录页。
- **配置站点**：点卡片开配置窗，里面有「怎么拿 cookie」的说明和账号表单，底栏固定放「＋ 添加账号 / 立即签到 / 保存」。表单类站点（AcFun、阿里云盘这类）字段直接摊开，cookie 类站点的可选参数收在折叠条里。
- **cookie 随便粘**：浏览器复制的分号串、没空格的分号串、每行一个字段、DevTools 表格整块、JSON 导出、带 `Cookie:` 前缀的 curl 命令 —— 都认，自动规范化成 `; ` 分隔。
  > 上游引擎几乎每个站点都写死 `cookie.split("; ")`，用 `;` 没空格或换行分隔会**静默解析错**、还不报错，所以面板替你补分隔符。
- **cookie 有效性**：三级递进 —— 格式体检（粘贴即出，指出缺哪个必填字段）→ 在线校验（请求站点登录态接口，返回昵称 / 等级 / 余额）→ 运行校验（跑真实签到）。结果存档在卡片徽章上并标注依据，**改动 cookie 后旧结论立刻作废**；遇到网络不通老实报「无法判定」，绝不误报失效。
  > 「跑通」不等于「有效」：上游不少模块遇到无效 cookie 是**静默返回**的（比如 B 站 `main()` 开头就 `if is_login:` 直接跳过），所以接口判定为 ❌ 的站点，跑签到没报错也继续标 ❌。
- **跑签到**：配置窗里单站跑，右上角「全部签到」跑全部；输出实时显示在右侧抽屉（可切当前任务 / 历史任务 / 日志）。
- **定时签到**：设置页选预设或自己填 cron，保存即写入容器 crontab。面板只动自己那段带标记的区块，你别的定时任务不受影响。
- **推送通知**：沿用上游全部渠道（PushPlus、企业微信、Telegram、Bark、钉钉、飞书、Gotify、ntfy、Server 酱、Qmsg），只填要用的，每种渠道一个独立方框。**一次签到恒定一条消息**：

```text
【dailycheckin-plus 每日签到 · 2026-10-16】

「V2EX 论坛」
帐号信息: ABC
今日签到: 20261016 的每日登录奖励 13 铜币

————————————

「哔哩哔哩」
第 1 个账号: ✅✅✅✅✅

————————————

任务用时: 1 秒
项目地址: https://github.com/beacherz/dailycheckin-plus
```

- **设置页**：后台账号密码 / 引擎溯源（上游仓库、提交、本地补丁清单）/ `config.json` 原文编辑（语法错拒绝保存，每次保存前自动留时间戳备份，最多 30 份可一键恢复）/ 关于本项目。

## 支持的站点

清单从引擎里**自动发现** —— 上游加了新站，刷新面板就会出现，不用改代码。当前 16 个：

| 站点 | KEY | 凭据（必填） |
|---|---|---|
| 哔哩哔哩 | `BILIBILI` | Cookie `SESSDATA`、`bili_jct` |
| 百度贴吧 | `TIEBA` | Cookie `BDUSS` |
| 百度网盘 | `BAIDUWP` | Cookie `BDUSS` |
| 爱奇艺 | `IQIYI` | Cookie `P00001` |
| 有道云笔记 | `YOUDAO` | Cookie `YNOTE_PERS` |
| V2EX | `V2EX` | Cookie `A2` |
| 什么值得买 | `SMZDM` | 建议整块复制 |
| 奥拉星 | `AOLAXING` | Cookie `BT_LOGIN_tt_common` |
| 恩山无线论坛 | `ENSHAN` | Cookie `TWcq_2132_auth` |
| 飞牛 NAS 论坛 | `FNNASCLUB` | Cookie `pvRK_2132_auth` |
| 全民 K 歌 | `KGQQ` | Cookie `uid`、`openid`、`openkey` |
| 阿里云盘 | `ALIYUN` | refresh_token |
| i 茅台 | `IMAOTAI` | `token`、`userid`、`mobile` 等 |
| AcFun | `ACFUN` | 账号密码 |
| 小米运动 | `MIMOTION` | 账号密码 |
| 百度站点提交 | `BAIDU` | 表单 |

新站**开箱可用**（能配、能存、能签到），只是精细度降一档：不拦必填字段、没有在线校验、LOGO 退回图标。想补全，照 `panel/catalog.py` 里已有写法加一段元数据即可。

**怎么拿 cookie**：登录目标网站 → `F12` → **Application** → **Cookies** → 选中域名 → 表格里 `Ctrl+A` `Ctrl+C` 复制。或用 [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) 插件 **Export → JSON** 整块贴进来。
cookie 等于账号密码，**别外发** —— 它只存在你本机的 `config/config.json`，不会上传到任何地方。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `TZ` | `Asia/Shanghai` | 时区，影响定时任务时间 |
| `PANEL_PORT` | `8080` | 容器内监听端口（改这个要同步改 compose 映射） |
| `PANEL_TITLE` | `dailycheckin-plus` | 浏览器标签 + 顶栏的品牌名 |
| `PANEL_USERNAME` / `PANEL_PASSWORD` | 空 | 想跳过「首次打开手动设账号」时填，只在后台还没初始化时生效 |
| `PANEL_TOKEN` | 空 | 可选的脚本口令，给 curl / 自动化用（`X-Panel-Token` 头或 `?token=`），**不能替代登录**，别开在公网 |
| `PANEL_RUN_TIMEOUT` | `1800` | 单次签到任务超时秒数 |
| `PANEL_REPO` | `BeacherZ/dailycheckin-plus` | 「关于本项目」里的链接、以及「要不要更新」的比对对象，换成自己的 fork 即可 |
| `PANEL_GH_TOKEN` | 空 | 访问 GitHub 接口时带上它，避免匿名限流（60 次/小时/IP） |
| `DC_HOME` | `/dailycheckin` | 工作目录，一般不用改 |

纯 Python 标准库实现，**零框架依赖**，x86 / arm64 / armv7 都能跑；后台密码只存 PBKDF2 派生值 + 随机盐，会话是签名票据（面板重启不掉线）；登录失败按 IP 限速。

## 跟随上游更新

引擎源码**内置**在 `dailycheckin/`（不从 PyPI 装）：构建可复现、离线能编译、补丁不会丢，代价是上游更新要显式同步一次。

```bash
python tools/sync_upstream.py --check     # 只查不改，退出码 2 = 有更新
python tools/sync_upstream.py             # 同步到 UPSTREAM.json 记录的 ref
python tools/sync_upstream.py --ref 25.12.9   # 指定 tag / 分支 / commit
```

它会下载上游源码、替换 `dailycheckin/`、**重放 `patches/` 里的本地补丁**、更新 `UPSTREAM.json`，并报告站点增减。补丁打不上就整体回滚，绝不留下改了一半的引擎 —— 所以**别手工把上游目录盖过来**，那会悄悄抹掉补丁。仓库 **Actions → sync upstream → Run workflow** 也能点一下自动同步并重建镜像。

两个本地补丁：`0001` 修 B 站分区接口（上游接口下线导致 `AttributeError`，已提 [PR #592](https://github.com/Sitoi/dailycheckin/pull/592)，上游合并后删掉即可）、`0002` 把通知改成恒定一条。

离线自测（不需要网络）：`python tools/test_sync_upstream.py`（补丁重放 / 冲突回滚）、`tools/test_notice.py`（通知一条）、`tools/test_schedule.py`（crontab 托管区块）、`tools/test_panel_static.py`（前端契约）。

## 常见问题

**想挂到公网？**
① 登录后台设好账号密码（默认就要求登录，别关）；② 前面套一层 HTTPS 反向代理（Nginx / Caddy / Traefik）—— 会话票据是 Bearer 语义，明文 HTTP 有被截获的风险。反代记得转发 `X-Forwarded-Proto`，面板会据此给 cookie 加 `Secure`。

**通知怎么变成两条了？改了代码没变化？**
先看通知结尾那行 **`项目地址`**：写着 `github.com/beacherz/dailycheckin-plus` 才是本项目镜像；如果是 `github.com/Sitoi/dailycheckin`，说明你跑的**还是旧镜像**：`docker compose pull && docker compose up -d`。
结尾确实对了却仍收多条，查两处：① `docker exec dailycheckin crontab -l` 看有没有两行签到任务（从官方镜像迁来的容器可能同时有「裸的签到行」和面板写的托管区块，去「设置 → 定时签到」随便保存一次让面板接管）；② `docker logs dailycheckin --tail 50` 对一下有没有别的脚本在发。

**从官方镜像 `sitoi/dailycheckin` 迁过来要做什么？**
先停掉旧容器 —— 本项目容器名也叫 `dailycheckin`，不清理会撞名：`docker stop dailycheckin && docker rm dailycheckin`。然后把原 `config/config.json` 复制到本项目 `config/`，`docker compose up -d` 即可。

**校验显示「无法判定」是不是 cookie 坏了？**
不一定。网络不通、接口改版、被风控都会这样，面板宁可不确定也不误报失效。这种情况点「立即签到」：**报错了一定有问题，没报错也不能证明有效**。

## 本地开发

```bash
pip install -r requirements.txt    # 只有引擎需要（requests / pycryptodome / rsa / urllib3）
python -m panel                    # 默认监听 0.0.0.0:8080
```

即使引擎导入失败（比如 `requests` 没装好），面板也能起来并给出提示，不会白屏。从源码构建镜像用 `docker compose -f docker-compose.build.yml up -d --build`。

目录：`panel/` 后台（纯标准库）、`dailycheckin/` 引擎（上游源码 + `patches/`）、`tools/` 离线工具与自测、`docker/entrypoint.sh` 容器入口。

## 致谢与许可

签到引擎来自 [Sitoi/dailycheckin](https://github.com/Sitoi/dailycheckin)（作者 Sitoi），MIT License，版权归原作者所有。本项目的网页管理后台、Docker 编排与部署体验为新增部分，同样以 MIT 发布。
