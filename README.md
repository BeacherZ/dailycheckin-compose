# dailycheckin-plus

**给 [Sitoi/dailycheckin](https://github.com/Sitoi/dailycheckin) 加了一个网页管理后台。一条 `docker compose up -d` 跑起来，浏览器里点几下就配好了。**

[![build](https://github.com/BeacherZ/dailycheckin-plus/actions/workflows/build.yml/badge.svg)](https://github.com/BeacherZ/dailycheckin-plus/actions/workflows/build.yml)
[![ghcr](https://img.shields.io/badge/ghcr.io-dailycheckin--plus-2496ed?logo=docker&logoColor=white)](https://github.com/BeacherZ/dailycheckin-plus/pkgs/container/dailycheckin-plus)
![license](https://img.shields.io/badge/license-MIT-green)

签到引擎沿用上游原项目（MIT，已内置 B 站接口修复），**网页后台是本项目新增的**。

![后台效果图](index.png)

*后台效果图：卡片视图，一行 4 个站点，顶栏是签到概况统计（有效 / 失效 / 未判定 / 已配置）。*

---

## 它解决什么

| 上游的做法 | 现在 |
|---|---|
| 手改 `config.json`，少个逗号就整个不跑 | 网页填表单，点保存，写错了直接告诉你错哪 |
| cookie 必须用 `; `（分号**加空格**）分隔，从浏览器复制常常不满足 | 粘什么格式都认，自动规范化成引擎要的形态 |
| cookie 过期了没提醒，只能翻日志猜 | 卡片上直接标 ✅ 有效 / ❌ 失效 |
| 不知道某个站到底要哪几个字段 | 每个站点标出必填字段，缺了高亮 |
| 改定时时间要进容器改文件 | 网页选周期，保存即生效 |
| 每次签到推送一堆消息，一条一个站 | **恒定只推一条**，带标题和分隔行 |

---

## 快速开始

### docker compose（推荐）

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

### docker run

```bash
docker run -d --name dailycheckin --restart unless-stopped -p 8080:8080 -e TZ=Asia/Shanghai \
  -v "$PWD/config:/dailycheckin/config" -v "$PWD/cron:/dailycheckin/cron" \
  -v "$PWD/logs:/dailycheckin/logs" -v "$PWD/data:/dailycheckin/data" \
  ghcr.io/beacherz/dailycheckin-plus:latest
```

> **Windows**：`$PWD` 换成 `${PWD}`，或直接写绝对路径（`D:/dailycheckin/config:/dailycheckin/config`）。
> **群晖 / 威联通**：把 compose 内容贴进 Container Manager / Container Station 的「项目」里。
> **改端口**：改 `-p` 左边那个数字，例如 `9000:8080`。

### 打开后台

浏览器打开 `http://你的地址:8080` —— 第一次会引导你设置后台账号密码，设完就进后台。

### 升级

```bash
docker compose pull && docker compose up -d
```

docker run 方式：`docker pull` 拉新镜像 → `docker rm -f dailycheckin` → 重跑上面那条 `docker run`（四个 `-v` 目录不用变，数据都在）。

### 数据放在哪

| 目录 | 内容 |
|---|---|
| `config/` | `config.json`，站点与 cookie（和上游格式完全一致） |
| `cron/` | 定时任务定义 |
| `logs/` | 签到日志 |
| `data/` | 后台账号凭据、校验状态、运行历史、配置备份 |

删容器不丢数据，备份把这四个目录一起拷走就行。

---

## 网页后台

### 站点列表

首页把 16 个站点铺成卡片，**卡片视图**一行 4 张、**列表视图**一行 2 个，右上角切换。每个站带官网 LOGO（加载不出来回退成图标）。

- 左边一条色条表示 cookie 状态，右上角是分类标签和状态徽章，卡底一行概况
- 概况长度不一也统一收成一行加省略号，所以**一排卡片高度完全齐平**；鼠标停一下能看全被截掉的内容
- 顶部搜索框按站名或 `KEY` 过滤（快捷键 `/`），分类下拉筛选，「只看待配置」一键隐藏配好的
- 排序默认**「已配置优先」**，下拉可切默认顺序 / 按名称 / 按分类
- 窗口变窄自动降密度：卡片 4 → 3 → 2 → 1 列，列表 2 → 1 列
- 顶栏统计条（有效 / 失效 / 未判定 / 已配置 / 上次任务）不用点开任何东西
- 跟随系统深浅色主题

登录过的人再打开会**直接进管理界面**，不会先闪一屏登录页。

### 配置站点

**点任意一张卡片**（列表视图点「配置」）弹出配置窗：

- 中间是「怎么拿 cookie」的说明和账号表单，底栏**固定**放「＋ 添加账号 / 立即签到 / 保存」—— cookie 贴得再长也不用滚到底才能保存
- `Esc`、点窗外、「关闭」三种关法，关掉后卡片状态立刻同步
- 表单类站点（AcFun、阿里云盘、i 茅台这类用账号密码 / token 的）字段**直接摊开**；cookie 类站点的可选参数收在「其它参数（可选）」折叠条里

### cookie

整块粘进配置窗就行，面板认这些形态：

| 你粘的内容 | 例子 |
|---|---|
| 浏览器复制的 cookie 串 | `SESSDATA=xxx; bili_jct=yyy` |
| 没空格的分号串 | `SESSDATA=xxx;bili_jct=yyy` |
| 每行一个字段 | `SESSDATA=xxx` ⏎ `bili_jct=yyy` |
| DevTools 表格整块复制（带 Tab 和域名列） | `SESSDATA␉xxx␉.bilibili.com␉/` |
| JSON 导出（对象 / `[{name,value}]` 数组） | 各种 cookie 插件导出的格式 |
| 带 `Cookie:` 前缀，或整条 curl 命令 | `curl '...' -H 'Cookie: SESSDATA=xxx'` |

上游引擎几乎每个站点都是这么解析的：

```python
{item.split("=")[0]: item.split("=")[1] for item in cookie.split("; ")}
```

它**硬依赖 `"; "`（分号加空格）**做分隔 —— 用 `;` 没空格或换行分隔，整条 cookie 都会被解析错，而且不报错。面板会自动补齐分隔符、结尾补 `;`，保存时再规范化一次。

**怎么拿**：登录目标网站 → `F12` → **Application** → 左侧 **Cookies** → 选中域名 → 表格里 `Ctrl+A` 全选 `Ctrl+C` 复制。或者用 [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) 插件选 **Export → JSON** 整块贴进来。

> cookie 等于账号密码，**别外发**。本项目存在你本机的 `config/config.json`，不会上传到任何地方。

### cookie 有效性

三级递进，可信度从低到高：

| 层级 | 怎么触发 | 说明 |
|---|---|---|
| **格式体检** | 粘贴后自动 | 不联网，秒出。告诉你识别出几个字段、**缺哪个必填字段** |
| **在线校验** | 配置窗里「校验 cookie」 | 请求站点的登录态接口，返回昵称 / 等级 / 余额，或明确的失效原因 |
| **运行校验** | 「立即签到」 | 跑真实签到。失败一定有问题，但**成功不等于 cookie 有效**，见下 |

结果会持久化，卡片上有徽章：🟢 有效 / 🔴 失效 / 🟡 无法判定 / ⚪ 未校验，并标注来源（`依据：登录态接口` / `依据：签到运行`）。**改动 cookie 后该站旧结论立刻作废**。在线校验遇到网络不通、接口改版会老实报「无法判定」，绝不误报失效。

> **为什么「跑通」不等于「有效」？** 上游不少站点模块遇到无效 cookie 是**静默返回**的 —— 比如 B 站模块 `main()` 开头就是 `if is_login:`，登录态不成立直接跳过，异常都不抛，引擎照样打一排 ✅。所以面板的规则是：接口判定为 ❌ 的站点，跑签到即使没报错也继续标 ❌。

### 跑签到

- 单站：配置窗底栏「立即签到」（点完自动关窗）
- 全部：右上角「全部签到」
- 输出实时显示在右侧抽屉，可切「当前任务 / 历史任务 / 签到日志」

### 定时签到

「设置 → 定时签到」选预设（每天 09:00 / 每天 00:30 / 每 6 小时 / 工作日 09:00）或自己填 cron，保存即写入容器 crontab 生效。面板**只动自己那段带标记的区块**，你其它定时任务不受影响：

```cron
# >>> dailycheckin-plus managed >>>
0 9 * * * cd /dailycheckin && dailycheckin >> /dailycheckin/logs/dailycheckin.log 2>&1
# <<< dailycheckin-plus managed <<<
```

> 从旧名字 `dailycheckin-compose` 升级来的部署，crontab 里还是老标记，面板认得出，保存时自动升级。如果 crontab 里有一行「裸的」签到任务（从官方镜像迁来或以前手写的），面板第一次保存时会把它整行**注释掉留档**再接管 —— 不然两份任务并存，一天跑两遍、通知收两条。

### 推送通知

「设置 → 推送通知」沿用上游全部渠道：PushPlus、企业微信、Telegram、Bark、钉钉、飞书、Gotify、ntfy、Server 酱、Qmsg。只填要用的，其它留空。

没有「消息条数」开关，**一次签到就是一条消息**：

```text
【dailycheckin-plus 每日签到 · 2026-10-16】

「V2EX 论坛」
帐号信息: BZGOGO
今日签到: 20261016 的每日登录奖励 13 铜币
帐号余额: 38259.34

————————————

「哔哩哔哩」
第 1 个账号: ✅✅✅✅✅

————————————

开始时间: 2026-10-16 09:00:01
任务用时: 1 秒
项目地址: https://github.com/beacherz/dailycheckin-plus
```

自带标题的渠道（server 酱、PushPlus、Gotify、ntfy、企业微信）会**同时**把标题用在渠道标题栏上。

### 设置页

- **后台账号**：改账号、改密码、退出登录
- **环境信息**：当前引擎的上游仓库 / 提交 / 版本 / 本地补丁清单
- **config.json 原文编辑**：语法错会拒绝保存；每次保存前自动留一份时间戳备份（最多 30 份，可一键恢复）
- **旧配置直接搬**：官方 `config/config.json` 拷进本项目 `config/` 即可，格式一模一样

---

## 支持的站点

站点清单从引擎里**自动发现** —— 上游加了新站，刷新面板就会出现，不用改代码。当前 16 个，以及从引擎源码逐个核对出的必填字段：

| 站点 | KEY | 凭据 | 必填字段 | 在线校验 |
|---|---|---|---|---|
| 哔哩哔哩 | `BILIBILI` | Cookie | `SESSDATA`、`bili_jct` | ✅ |
| 百度贴吧 | `TIEBA` | Cookie | `BDUSS` | ✅ |
| 百度网盘 | `BAIDUWP` | Cookie | `BDUSS` | ✅ |
| 爱奇艺 | `IQIYI` | Cookie | `P00001` | ✅ |
| 有道云笔记 | `YOUDAO` | Cookie | `YNOTE_PERS` | ✅ |
| V2EX | `V2EX` | Cookie | `A2` | ✅ |
| 什么值得买 | `SMZDM` | Cookie | 建议整块复制 | ✅ |
| 奥拉星 | `AOLAXING` | Cookie | `BT_LOGIN_tt_common` | ✅ |
| 恩山无线论坛 | `ENSHAN` | Cookie | `TWcq_2132_auth` | ✅ |
| 飞牛 NAS 论坛 | `FNNASCLUB` | Cookie | `pvRK_2132_auth` | ✅ |
| 全民 K 歌 | `KGQQ` | Cookie | `uid`、`openid`、`openkey` | 运行校验 |
| 阿里云盘 | `ALIYUN` | refresh_token | — | 运行校验 |
| i 茅台 | `IMAOTAI` | 表单 | `token`、`userid`、`mobile`… | 运行校验 |
| AcFun | `ACFUN` | 账号密码 | — | 运行校验 |
| 小米运动 | `MIMOTION` | 账号密码 | — | 运行校验 |
| 百度站点提交 | `BAIDU` | 表单 | — | 运行校验 |

> 标「运行校验」的站点没有公开的登录态接口，点「立即签到」，结果就是最准的答案。

---

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `TZ` | `Asia/Shanghai` | 时区，影响定时任务时间 |
| `PANEL_PORT` | `8080` | 容器内监听端口（改这个要同步改 compose 映射） |
| `PANEL_TITLE` | `dailycheckin-plus` | 浏览器标签 + 后台顶栏的品牌名，可以改成你喜欢的叫法 |
| `PANEL_USERNAME` | 空 | 想跳过「首次打开手动设置」时，配合下一项直接建号 |
| `PANEL_PASSWORD` | 空 | 同上，只在后台还没初始化时生效 |
| `PANEL_TOKEN` | 空 | **可选**的脚本口令，给 curl / 自动化用（`X-Panel-Token` 头或 `?token=`），**不能替代登录**，不建议开在公网 |
| `PANEL_RUN_TIMEOUT` | `1800` | 单次签到任务超时秒数（贴吧号多要跑很久） |
| `DC_HOME` | `/dailycheckin` | 工作目录，一般不用改 |

运行时特性：纯 Python 标准库实现，**零框架依赖**，x86 / arm64 / armv7 都能跑；后台密码只存 PBKDF2 派生值 + 随机盐，会话是签名票据（面板重启不掉线）；登录失败按 IP 限速；多阶段构建，`python:3.9-slim` 打底，带健康检查。

---

## 跟随上游更新

引擎源码**内置**在 `dailycheckin/` 里（不从 PyPI 装），好处是构建可复现、离线能编译、补丁不会丢；代价是上游更新要显式同步一次。

**别手工把上游 `dailycheckin/` 盖过来** —— 那会悄悄抹掉 `patches/` 里的两个本地修复。

```bash
python tools/sync_upstream.py --check              # 只查不改，退出码 2 = 有更新
python tools/sync_upstream.py                      # 同步到 UPSTREAM.json 记录的 ref
python tools/sync_upstream.py --ref 25.12.9        # 指定 tag / 分支 / commit
python tools/sync_upstream.py --dry-run            # 只比对，不落地
```

它会：下载上游源码 → 替换 `dailycheckin/` → **重放 `patches/` 里的本地补丁** → 更新 `UPSTREAM.json` → 报告站点增减与元数据缺口。任何补丁打不上就**整体回滚**并指出对不上的位置，绝不留下改了一半的引擎。

也可以在仓库 **Actions → sync upstream → Run workflow**（可填 ref）里点一下：自动同步、提交、推送，并重建镜像发布到 ghcr.io。同一个工作流每周一还会自动检查，上游有新提交就开 issue。之所以自己构建而不是等 `build` 工作流，是因为用 `GITHUB_TOKEN` 推的提交不会再触发其它工作流（GitHub 防递归）。

### 上游新增站点后会怎样

站点由引擎按 `CheckIn.__subclasses__()` 自动发现，面板只是读引擎，所以新站**开箱可用**（能填 cookie、能保存、能签到），只是**精细度降一档**：不拦截必填字段、没有在线校验按钮、LOGO 退回 🧩，卡片上挂一个「通用配置」标记。想补全，照 `panel/catalog.py` 里已有写法补一段元数据即可（`required` / `verify` / `logo` / `howto` / `fields`）；同步结束时会打印「哪些站点还没有元数据」的清单。

### 两个本地补丁

- `0001-bilibili-newlist.patch` —— 上游的分区视频接口 `/x/web-interface/dynamic/region` 已下线，返回 `{"code":-404,"data":null}`，而代码写的是 `ret.get("data", {}).get("archives", [])`，key 存在但值是 `None`，兜底默认值不生效，于是抛 `AttributeError`。本仓库改用出入参一致的 `/x/web-interface/newlist`，并给几处 `None` 补了空值兜底。该修复也已提 PR 到上游（[Sitoi/dailycheckin#592](https://github.com/Sitoi/dailycheckin/pull/592)），上游合并后删掉这个补丁文件即可，不用改代码。
- `0002-notice-single-message.patch` —— 删掉上游「按渠道自动拆分 + `MERGE_PUSH` 开关」那套逻辑（配置留白时会误判成多条），改成恒定一条、带标题与分隔行、结尾指向本项目。

### 离线自测

不需要网络，随时能验证这套机制还好使：

```bash
python tools/test_sync_upstream.py    # 补丁重放 / 冲突回滚 / 新站点降级
python tools/test_notice.py           # 通知恒定一条、标题带项目名、结尾指向本项目
python tools/test_schedule.py         # crontab 托管区块：老标记兼容，不会变成两段任务
python tools/test_panel_static.py     # 前端契约：首屏不预置登录屏、默认排序、密度、配置弹窗
```

---

## 目录结构

```
.
├── docker-compose.yml          # 一键部署（用 ghcr.io 现成镜像）
├── docker-compose.build.yml    # 从源码构建版
├── Dockerfile                  # 引擎 + 面板
├── UPSTREAM.json               # 引擎溯源：上游仓库 / ref / commit / 版本 / 本地补丁清单
├── patches/                    # 相对上游的本地补丁（同步时自动重放）
├── tools/                      # 离线工具与自测（纯标准库，不参与镜像构建）
│   ├── sync_upstream.py        # --check 查更新 / --ref 同步并重放补丁
│   └── test_*.py               # 同步机制 / 通知 / crontab / 前端契约的自测
├── panel/                      # 网页管理后台（纯标准库，零额外依赖）
│   ├── server.py               # HTTP 服务、路由、鉴权
│   ├── auth.py                 # 后台账号密码与会话票据
│   ├── cookies.py              # cookie 解析与规范化
│   ├── catalog.py              # 站点元数据（必填字段、LOGO、怎么拿 cookie）
│   ├── upstream.py             # 读 UPSTREAM.json，给面板显示引擎来源
│   ├── verify.py               # 各站点在线登录态校验
│   ├── runner.py               # 跑签到、解析输出、回写有效性状态
│   ├── store.py                # config.json 读写 + 备份
│   ├── schedule.py             # crontab 管理
│   └── static/                 # 单页界面（原生 HTML/CSS/JS，无构建步骤）
├── dailycheckin/               # 签到引擎（上游源码 + patches/ 补丁）
└── docker/entrypoint.sh        # 容器入口：准备配置 → 装定时任务 → 起 crond + 面板
```

---

## 常见问题

**cookie 存哪儿？安全吗？**
存宿主机 `./config/config.json`，和引擎原生格式一致，**不会**上传到任何地方；`config/` 已在 `.gitignore` 里。后台账号凭据存 `./data/panel_auth.json`，只有 PBKDF2 派生值 + 随机盐，没有明文密码。

**想挂到公网？**
① 登录后台设好账号密码（默认就要求登录，别关）；② 前面套一层 HTTPS 反向代理（Nginx / Caddy / Traefik），因为会话票据是 Bearer 语义，明文 HTTP 有被截获的风险。反代记得转发 `X-Forwarded-Proto`，面板会据此给 cookie 加 `Secure`。

**通知怎么变成两条了？改了代码没变化？**
先看通知结尾那行 **`项目地址`**：写着 `github.com/beacherz/dailycheckin-plus` 才是本项目镜像；如果是 `github.com/Sitoi/dailycheckin`，说明**你跑的还是旧镜像**（本项目从镜像里装引擎，改源码不 `pull` 不生效）：`docker compose pull && docker compose up -d`。

容器已更新、结尾也确实是本项目地址，却仍收到多条，查两个点：① **有几份 cron 在跑** —— 官方镜像迁来的容器里可能同时存在「裸的签到行」和面板写入的托管区块，打开「设置 → 定时签到」随便保存一次让面板接管（`docker exec dailycheckin crontab -l` 看有没有两行 `&& dailycheckin`）；② **有别的 bot / 脚本在发** —— `docker logs dailycheckin --tail 50` 对一下发送时间。

**定时任务没生效？**
先看 `docker logs dailycheckin` 里有没有「定时任务已装载」，再确认「设置 → 定时签到」是开着的。cron 不继承容器环境变量，所以默认 crontab 头部显式写了 `TZ` 和 `PATH`。

**提示「某个字段的值里含 `=`，会被截断」是什么意思？**
引擎用 `cookie.split("=")[1]` 取值，值里再出现 `=` 只能取到第二个 `=` 之前的部分，Base64 结尾的填充符 `=` 正好踩这个坑。这不是面板的 bug，是上游解析方式的限制 —— 该站若报签名 / 校验错误，把那个字段手工裁剪一下再试。

**校验显示「无法判定」是不是 cookie 坏了？**
不一定。网络不通、接口改版、被风控拦截都会这样，面板宁可不确定也不误报失效。这种情况可以点「立即签到」：**报错了一定有问题，没报错也不能证明有效**。

**从官方镜像 `sitoi/dailycheckin` 迁过来要做什么？**
先停掉旧容器 —— 本项目容器名也叫 `dailycheckin`，不清理会撞名：

```bash
docker stop dailycheckin && docker rm dailycheckin
```

然后把原 `config/config.json` 复制到本项目 `config/`，`docker compose up -d` 即可，站点和账号自动识别。原来那种「pip 升级后手打补丁」的 cron 也可以删了。

**项目名从 `dailycheckin-compose` 改成了 `dailycheckin-plus`，我要动什么？**
只有一件事：换镜像名。旧镜像 `ghcr.io/beacherz/dailycheckin-compose` **已从 Packages 里删除**（再拉会 403 denied），改成 `ghcr.io/beacherz/dailycheckin-plus:latest`。容器名故意保持 `dailycheckin` 没改（改了会变成新旧两个容器同时在跑，通知收两条），crontab 老标记面板也照样认。

**B 站日志里「直播签到：签到活动已下线」是 bug 吗？**
不是。B 站自己下线了直播签到活动，任何工具都做不了，不影响其它签到项。

---

## 本地开发

面板零额外依赖，直接在仓库根目录跑：

```bash
pip install -r requirements.txt     # 只有引擎需要（requests / pycryptodome / rsa / urllib3）
python -m panel                     # 默认监听 0.0.0.0:8080，工作目录取仓库根目录
```

即使 `requests` 没装好、引擎导入失败，面板也能起来并给出提示（站点清单退化成扫源码获取），不会白屏。

想从源码构建镜像用 `docker-compose.build.yml`：

```bash
git clone https://github.com/BeacherZ/dailycheckin-plus.git && cd dailycheckin-plus
docker compose -f docker-compose.build.yml up -d --build
```

---

## 致谢与许可

- 签到引擎来自 [Sitoi/dailycheckin](https://github.com/Sitoi/dailycheckin)（作者 Sitoi），MIT License，版权归原作者所有。
- 本项目的网页管理后台、Docker 编排与部署体验为新增部分，同样以 MIT 发布。
