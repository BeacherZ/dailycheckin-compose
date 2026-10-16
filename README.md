# dailycheckin-plus

**给 [Sitoi/dailycheckin](https://github.com/Sitoi/dailycheckin) 加了一个网页管理后台。一条 `docker compose up -d` 或一条 `docker run`，浏览器里点几下就配好了。**

[![build](https://github.com/BeacherZ/dailycheckin-plus/actions/workflows/build.yml/badge.svg)](https://github.com/BeacherZ/dailycheckin-plus/actions/workflows/build.yml)
[![ghcr](https://img.shields.io/badge/ghcr.io-dailycheckin--plus-2496ed?logo=docker&logoColor=white)](https://github.com/BeacherZ/dailycheckin-plus/pkgs/container/dailycheckin-plus)
![license](https://img.shields.io/badge/license-MIT-green)

签到引擎沿用上游原项目（MIT，已内置 B 站接口修复），**网页后台是本项目新增的**。

---

## 为什么要它

上游引擎很能打，但配置体验对新手不太友好：

| 原来的做法 | 现在 |
|---|---|
| 手改 `config.json`，少个逗号就整个不跑 | 网页填表单，点保存，写错了直接告诉你错哪 |
| cookie 必须用 `; `（分号**加空格**）分隔，从浏览器复制常常不满足 | 粘什么格式都认，自动规范化成引擎要的形态 |
| cookie 过期了没提醒，只能翻日志猜 | 网页上直接标 ✅ 有效 / ❌ 失效 |
| 不知道某个站到底要哪几个字段 | 每个站点标出必填字段，缺了高亮 |
| 改定时时间要进容器改文件 | 网页选周期，保存即生效 |
| 每次签到推送一堆消息，一条一个站 | **恒定只推一条**，带标题，站点之间用分隔行隔开 |

---

## 功能一览

**网页后台**

- 🔐 **首次打开引导设置账号密码**，之后需登录；设置页可随时改账号密码、退出登录
- 🪧 **顶栏显示项目名、面板版本、引擎状态与签到概况**（有效 / 失效 / 未判定 / 已配置 / 上次任务），项目名可用 `PANEL_TITLE` 换成自己的叫法
- 🧩 **16 个签到站点**，卡片 / 列表两种视图（卡片一行 4 张、列表一行 2 个），带官网 LOGO，支持搜索、分类筛选、只看待配置，默认把已配置的站点排在最前面；**点卡片弹出该站的配置窗**，卡片本身永远等高，一排四个不会因为展开而参差
- 🍪 **粘贴即用**：浏览器复制、JSON 导出、DevTools 表格、curl 命令 —— 全都能识别并规范化
- ✅ **cookie 有效性判定**：本地格式体检 → 在线登录态校验 → 真实运行校验，三级递进
- 🎯 **每个站点标注必填字段**，缺哪个高亮哪个
- ▶️ 单站「立即签到」/ 一键「全部签到」，输出实时滚动
- ⏰ **定时任务**网页配置，只改自己那段 crontab，不动你别的任务
- 🔔 推送渠道全覆盖，**一次签到恒定只发一条**（带标题、分隔行、项目地址）
- 🛡️ `config.json` 原文编辑 + 每次保存前自动备份（保留 30 份，可一键恢复）
- 🔄 **上游加了新签到站点会自动出现**，一条命令同步引擎、自动重放本地补丁（[见下](#跟随上游更新)）

**运行时**

- 纯 Python 标准库实现的 Web 服务，**零额外框架依赖**，x86 / arm64 / armv7 都能跑
- 密码只存 PBKDF2 派生值 + 随机盐，会话是签名票据（面板重启不掉线）
- 登录失败按 IP 限速，挡最基础的爆破
- 多阶段镜像，`python:3.9-slim` 打底，带健康检查

---

## 快速开始

两种装法任选一种，效果完全一样：**docker compose**（推荐，以后改端口、加变量方便）或 **docker run**（不想建文件，一条命令跑起来）。

### 方式一：docker compose（推荐）

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

然后：

```bash
docker compose up -d
```

### 方式二：docker run

```bash
docker run -d \
  --name dailycheckin \
  --restart unless-stopped \
  -p 8080:8080 \
  -e TZ=Asia/Shanghai \
  -v "$PWD/config:/dailycheckin/config" \
  -v "$PWD/cron:/dailycheckin/cron" \
  -v "$PWD/logs:/dailycheckin/logs" \
  -v "$PWD/data:/dailycheckin/data" \
  ghcr.io/beacherz/dailycheckin-plus:latest
```

> **Windows（PowerShell / CMD）**：`$PWD` 换成 `${PWD}`，整行建议写成一行；
> 也可以把 `"$PWD/config:/dailycheckin/config"` 换成绝对路径，例如
> `D:/dailycheckin/config:/dailycheckin/config`。
> 想改端口就改 `-p` 左边那个数字（例如 `-p 9000:8080`）。

用 docker run 安装的话，以后升级是「拉新镜像 + 删旧容器 + 重新 run」：

```bash
docker pull ghcr.io/beacherz/dailycheckin-plus:latest
docker rm -f dailycheckin
# 再执行一遍上面那条 docker run（四个 -v 目录不变，数据都在）
```

### 打开后台

浏览器打开 **`http://你的地址:8080`** —— 第一次会引导你设置后台账号密码，设完就进后台了。

> **群晖 / 威联通**：compose 方式把上面的内容贴进 Container Manager（群晖）或 Container Station 的「项目 / 应用程序」；docker run 方式在「映像 → 新增容器」里照着填端口和四个目录映射即可。
> **想改端口**：把 `8080:8080` 左边那个数字改掉，例如 `9000:8080`。

### 数据放在哪

compose 方式下这四个目录会出现在 compose 文件同级；docker run 方式下就是你在 `-v` 里指定的那几个路径（上面例子是当前目录）：

| 目录 | 内容 |
|---|---|
| `config/` | `config.json`，站点与 cookie（和上游格式完全一致） |
| `cron/` | 定时任务定义 |
| `logs/` | 签到日志 |
| `data/` | 后台账号凭据、校验状态、运行历史、配置备份 |

删容器不丢数据，备份时把这四个目录一起拷走就行。

---

## 网页后台导览

### 1️⃣ 登录

首次打开会要求设置一个后台账号密码（账号 2–32 字符，密码至少 6 位），设置完自动登录。
之后每次打开都要登录；「设置 → 后台账号」里可以改账号、改密码、退出登录。

> 想跳过手动设置、由部署脚本直接建号，用环境变量 `PANEL_USERNAME` + `PANEL_PASSWORD`（见下方环境变量表）。

### 2️⃣ 找站点

首页把所有站点铺成卡片，一眼扫完：

- **卡片视图**：一行 4 张，每张卡左边一条颜色条表示 cookie 状态，右上角是分类标签和状态徽章；卡底一行概况（账号数 / 校验时间 / 依据 / 站点返回的信息），长度不一也统一收成一行加省略号 —— 这样**一排卡片高度完全齐平**，鼠标停一下能看全被截掉的内容
- **列表视图**：一行 2 个站，信息更密，适合站点多的时候快速定位（右上角「卡片 / 列表」切换）
- **排序默认「已配置优先」**：配好 cookie 的站点排在前面，还没配的沉到后面；下拉里可切成默认顺序 / 按名称 / 按分类
- 窗口变窄会自动降密度：卡片 4 → 3 → 2 → 1 列，列表 2 → 1 列
- 顶栏那条统计（有效 / 失效 / 未判定 / 已配置 / 上次任务）不用点开任何东西，一眼知道整体状态
- 顶部搜索框按站点名或 `KEY` 过滤（快捷键 `/`）
- 分类下拉按平台类型筛；「只看待配置」一键隐藏已经配好的
- 每个站都带官网 LOGO，加载不出来会回退成图标
- 跟随系统深浅色主题；状态色只在表达状态的地方出现，其余走中性灰阶

已经登录过的人再打开面板会**直接进管理界面**，不会先闪一屏登录页；没登录过的人先看到的是中性的「正在连接面板…」，等确认完状态再显示对应的那一屏。

### 3️⃣ 配置某个站点

**点任意一张卡片**（列表视图里点「配置」）弹出该站点的配置窗：

- 顶部是站点 LOGO、名称、分类与当前状态；中间是「怎么拿 cookie」的说明和账号表单；底栏是 **＋ 添加账号 / 立即签到 / 保存** —— 底栏固定，cookie 贴得再长也不用滚到底才能保存
- `Esc`、点窗外、「关闭」三种关法，关掉后卡片上的状态和账号数立刻同步
- 卡片本身永远只有「LOGO + 站名 + 分类 + 状态徽章 + 一行概况」，不会因为展开而被撑高，一排四个永远是齐的

> 表单类站点（AcFun、阿里云盘、i茅台这类用账号密码 / token 的）字段**直接摊开**在弹窗里；cookie 类站点的可选补充参数则收在「其它参数（可选）」折叠条里。

### 4️⃣ 加 cookie

在站点配置窗里把 cookie 整块粘进文本框就行。面板认这些形态：

| 你粘的内容 | 例子 |
|---|---|
| 浏览器复制的 cookie 串 | `SESSDATA=xxx; bili_jct=yyy` |
| 没空格的分号串 | `SESSDATA=xxx;bili_jct=yyy` |
| 每行一个字段 | `SESSDATA=xxx` ⏎ `bili_jct=yyy` |
| DevTools 表格整块复制（带 Tab 和域名列） | `SESSDATA␉xxx␉.bilibili.com␉/` |
| JSON 导出（对象 / `[{name,value}]` 数组） | 各种 cookie 插件导出的格式 |
| 带 `Cookie:` 前缀，或整条 curl 命令 | `curl '...' -H 'Cookie: SESSDATA=xxx'` |

**为什么非要规范化？** 上游引擎几乎所有站点都是这么解析的：

```python
{item.split("=")[0]: item.split("=")[1] for item in cookie.split("; ")}
```

它**硬依赖 `"; "`（分号 + 空格）**做分隔。用 `;` 没空格、或者换行分隔，整条 cookie 都会被解析错，而且不报错。
面板会自动把分隔符补齐成 `"; "`、结尾补 `;`，并在保存时再规范化一次。

### 5️⃣ 判断 cookie 到底有没有效

三级递进，可信度从低到高：

| 层级 | 怎么触发 | 说明 |
|---|---|---|
| **格式体检** | 粘贴后自动，不用点 | 不联网，秒出。告诉你识别出几个字段、**缺哪个必填字段** |
| **在线校验** | 站点配置窗里「校验 cookie」 | 请求站点的登录态接口，返回昵称 / 等级 / 余额，或明确的失效原因。**这是判定有效/失效的强证据** |
| **运行校验** | 「立即签到」/「全部签到」 | 跑真实签到。失败一定有问题；但**成功不等于 cookie 有效**，见下 |

校验结果会持久化，卡片上有徽章：🟢 有效 / 🔴 失效 / 🟡 无法判定 / ⚪ 未校验，并标注结论来源（`依据：登录态接口` / `依据：签到运行`）。

> **为什么「跑通」不等于「有效」？**
>
> 上游不少站点模块遇到无效 cookie 是**静默返回**的。比如 B 站模块 `main()` 开头就是 `if is_login:`，登录态不成立时直接跳过，一个异常都不抛，引擎照样打一排 ✅。
>
> 所以面板的规则是：**接口判定为 ❌ 的站点，跑签到即使没报错也继续标 ❌**，并在原因里写清楚「该站点模块对无效 cookie 是静默返回的，以接口判定为准」。

两个贴心细节：

- 在线校验遇到网络不通、接口改版，会老实报「**无法判定**」，绝不误报失效
- **改动 cookie 后，该站旧结论立刻作废回到 ⚪ 未校验**，不会让你对着过期结论做判断

### 6️⃣ 跑签到

- 单站：站点配置窗底栏「立即签到」（点完自动关窗，直接看右侧抽屉的输出）
- 全部：右上角「全部签到」
- 输出实时显示在右侧抽屉，可切「当前任务 / 历史任务 / 签到日志」三个标签页

### 7️⃣ 定时签到

「设置 → 定时签到」：选预设（每天 09:00 / 每天 00:30 / 每 6 小时 / 工作日 09:00）或自己填 cron，保存即写入容器 crontab 并生效。

面板只动自己那段带标记的区块，你其它定时任务不受影响：

```cron
# >>> dailycheckin-plus managed >>>
0 9 * * * cd /dailycheckin && dailycheckin >> /dailycheckin/logs/dailycheckin.log 2>&1
# <<< dailycheckin-plus managed <<<
```

> 从旧名字（`dailycheckin-compose`）升级过来的部署，crontab 里还是老标记，面板**认得出**，保存时会就地升级成新标记。如果 crontab 里有一行「裸的」签到任务（从官方镜像迁过来、或以前手写的），面板在第一次保存时会把它**整行注释掉并留档**再接管 —— 不然它会和新写入的任务并存，一天跑两遍、通知收两条。

### 8️⃣ 推送通知

「设置 → 推送通知」，渠道沿用上游全部支持：PushPlus、企业微信、Telegram、Bark、钉钉、飞书、Gotify、ntfy、Server 酱、Qmsg。只填自己要用的那几项，其它留空。

没有「消息条数」这类开关：**一次签到就是一条消息**。顶部带标题（**标题里就有项目名**），各站点结果之间用分隔行隔开，末尾补上任务元信息与项目地址：

```text
【dailycheckin-plus 每日签到 · 2026-10-16】

「V2EX 论坛」
帐号信息: BZGOGO
今日签到: 20261016 的每日登录奖励 13 铜币
帐号余额: 38259.34

——————————————

「哔哩哔哩」
第 1 个账号: ✅✅✅✅✅

——————————————

开始时间: 2026-10-16 09:00:01
任务用时: 1 秒
当前版本: 25.12.9
最新版本: 25.12.9
项目地址: https://github.com/beacherz/dailycheckin-plus
```

> **为什么不是多条？** 上游引擎在检测到「有渠道需要拆分」时会按站点各发一条，`MERGE_PUSH` 留空还会误判。本项目把这段逻辑整个删掉了 —— 见 `patches/0002-notice-single-message.patch`，同步上游时会自动重放。自带标题的渠道（server 酱、PushPlus、Gotify、ntfy、企业微信）会**同时**把标题用在渠道标题栏上。

### 9️⃣ 兜底能力

- **config.json 原文编辑**：设置页可直接改 JSON，语法错会拒绝保存
- **自动备份**：每次保存前留一份时间戳备份，最多 30 份，下拉选一份一键恢复
- **旧配置直接搬**：官方 `config/config.json` 复制到本项目 `config/` 即可，格式一模一样

---

## cookie 怎么拿

以 Chrome / Edge 为例：

1. 登录目标网站
2. 按 `F12` 打开开发者工具 → **Application**（应用）→ 左侧 **Cookies** → 选中站点域名
3. 在表格里按 `Ctrl+A` 全选，`Ctrl+C` 复制，直接粘进面板

或者用 [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) 之类的插件，选 **Export → JSON**，把 JSON 整块贴进来也行。

> cookie 等于账号密码，**别外发**。本项目把它存在你本机的 `config/config.json`，不会上传到任何地方。

---

## 支持的站点

站点清单从引擎里**自动发现** —— 上游加了新站，刷新面板就会出现，不用改代码。
下面是当前 16 个站，以及从引擎源码逐个核对出的必填字段：

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
| `PANEL_TITLE` | `dailycheckin-plus` | 页面标题：浏览器标签 + 后台顶栏的品牌名，可以改成你喜欢的叫法 |
| `PANEL_USERNAME` | 空 | 想跳过「首次打开手动设置」时，配合下一项直接建号 |
| `PANEL_PASSWORD` | 空 | 同上，只在后台还没初始化时生效 |
| `PANEL_TOKEN` | 空 | **可选**的脚本口令，给 curl / 自动化用；认证走 `X-Panel-Token` 头或 `?token=`，**不能替代登录**，也不建议开在公网 |
| `PANEL_RUN_TIMEOUT` | `1800` | 单次签到任务超时秒数（贴吧号多要跑很久） |
| `DC_HOME` | `/dailycheckin` | 工作目录，一般不用改 |

---

## 从源码构建

不想用现成镜像、或者改了引擎源码，用仓库里的 `docker-compose.build.yml`：

```bash
git clone https://github.com/BeacherZ/dailycheckin-plus.git
cd dailycheckin-plus
docker compose -f docker-compose.build.yml up -d --build
```

第一次要装 Python 依赖，大约 1～2 分钟。之后升级：

```bash
git pull
docker compose -f docker-compose.build.yml up -d --build
```

---

## 跟随上游更新

本项目把引擎源码**内置**在 `dailycheckin/` 里（而不是从 PyPI 装），好处是构建可复现、离线能编译、打过的补丁不会丢；代价是**上游更新不会自己流进来**，得显式同步一次。上游仓库：[Sitoi/dailycheckin](https://github.com/Sitoi/dailycheckin)。

同步已经做成一条命令。**不要手工把上游 `dailycheckin/` 目录盖过来** —— 那会悄悄抹掉 `patches/` 里的两个本地修复（B 站接口、通知只发一条）。

### 1. 先看有没有更新

```bash
python tools/sync_upstream.py --check
```

只查不改，几秒钟出结果：上游最新提交、本项目记录在案的提交、站点模块增减、哪些新站点还没元数据。退出码 `2` 表示有新东西可同步。

### 2. 同步

```bash
python tools/sync_upstream.py                 # 同步到 UPSTREAM.json 里记录的 ref（默认 main）
python tools/sync_upstream.py --ref 25.12.9   # 指定 tag / 分支 / commit
python tools/sync_upstream.py --dry-run       # 只比对，不落地
```

它会：下载上游源码 → 替换 `dailycheckin/` → **重放 `patches/` 里的本地补丁** → 更新 `UPSTREAM.json` → 报告站点目录变化与元数据缺口。任何补丁打不上就**整体回滚**，并指出是哪个文件哪段代码对不上，绝不会留下改了一半的引擎。

同步完照常提交推送，CI 会自动重建镜像：

```bash
git add -A && git commit -m "chore: 同步上游引擎" && git push
```

### 3. 或者点一下按钮

仓库 → **Actions → sync upstream → Run workflow**（可填 ref）。它会同步、提交、推送，并顺手把镜像重建发布到 ghcr.io。之所以自己构建而不是等 `build` 工作流，是因为用 `GITHUB_TOKEN` 推的提交不会再触发其它工作流（GitHub 防递归）。同一个工作流每周一还会自动检查一次，上游有新提交就开 issue 提醒。

### 4. 上游新增站点后，会看到什么

站点是引擎按 `CheckIn.__subclasses__()` 自动发现的，面板只是读引擎，所以：

- **开箱可用**：新站点自动出现在卡片列表里，能填 cookie、能保存、能签到；
- **精细度降一档**：面板不知道它的必填 cookie 字段（不做格式拦截）、没有在线校验按钮、LOGO 退回 🧩，卡片上会挂一个「通用配置」标记。

想要完整体验，照着 `panel/catalog.py` 里已有的写法补一段元数据即可（`required` / `verify` / `logo` / `howto` / `fields`）。同步结束时会打印「哪些站点还没有元数据」的清单，按那张清单补就行。

任何时候都能自测这套补丁/同步机制是否还好使（离线，不需要网络）：

```bash
python tools/test_sync_upstream.py    # 补丁重放 / 冲突回滚 / 新站点降级
python tools/test_notice.py           # 通知恒定一条、标题带项目名、结尾指向本项目
python tools/test_schedule.py         # crontab 托管区块：老标记兼容，不会变成两段任务
python tools/test_panel_static.py     # 前端契约：首屏不预置登录屏、默认已配置优先、卡片 4 列 / 列表 2 列、站点配置走弹窗
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
│   ├── 0001-bilibili-newlist.patch
│   └── 0002-notice-single-message.patch
├── tools/                      # 离线工具与自测（纯标准库，不参与镜像构建）
│   ├── sync_upstream.py        # --check 查更新 / --ref 同步并重放补丁
│   ├── test_sync_upstream.py   # 补丁重放、冲突回滚、新站点降级的离线自测
│   ├── test_notice.py          # 通知模块自测：恒定一条、标题带项目名、结尾指向本项目
│   ├── test_schedule.py        # crontab 托管区块自测：老项目名标记兼容、不会变成两段任务
│   └── test_panel_static.py    # 前端契约自测：首屏不预置登录屏、默认排序、卡片 / 列表密度、配置弹窗
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

**Q：我的 cookie 存哪儿？安全吗？**
存宿主机 `./config/config.json`，和引擎原生格式一致，**不会**上传到任何地方；`config/` 已在 `.gitignore` 里，不会误提交。
后台账号凭据存 `./data/panel_auth.json`，只保存 PBKDF2 派生值 + 随机盐，没有明文密码。

**Q：想挂到公网，怎么做？**
两步：① 登录后台设好账号密码（默认就要求登录，别关）；② 前面套一层 HTTPS 反向代理（Nginx / Caddy / Traefik），因为会话票据是 Bearer 语义，明文 HTTP 下有被截获的风险。反代记得转发 `X-Forwarded-Proto`，面板会据此给 cookie 加 `Secure`。

**Q：提示「某个字段的值里含 `=`，会被截断」是什么意思？**
引擎用 `cookie.split("=")[1]` 取值，值里再出现 `=` 只能取到第二个 `=` 之前的部分，Base64 结尾的填充符 `=` 正好踩这个坑。这不是面板的 bug，是上游解析方式的限制 —— 该站点若报签名/校验错误，可以把那个字段手工裁剪一下再试。

**Q：校验显示「无法判定」是不是 cookie 坏了？**
不一定。网络不通、接口改版、被风控拦截都会是「无法判定」，面板宁可不确定也不误报失效。这种情况可以点「立即签到」：**报错了一定有问题，没报错也不能证明有效**（原因见上面「为什么跑通不等于有效」）。

**Q：定时任务没生效？**
先看 `docker logs dailycheckin` 里有没有「定时任务已装载」，再确认「设置 → 定时签到」是开着的。cron 不继承容器环境变量，所以默认 crontab 头部显式写了 `TZ` 和 `PATH`。

**Q：从官方镜像 `sitoi/dailycheckin` 迁过来要做什么？**
先把旧容器停掉并删掉 —— 本项目容器名也叫 `dailycheckin`，不清理会撞名：

```bash
docker stop dailycheckin && docker rm dailycheckin
# 原来用 compose 起的，就进原目录 docker compose down
```

然后把原 `config/config.json` 复制到本项目 `config/`，`docker compose up -d` 即可，站点和账号自动识别。原来那种「pip 升级后手打补丁」的 cron 也可以删了。

**Q：上游更新了签到网站目录，我怎么更新？**
一条命令：`python tools/sync_upstream.py`（它会自动重放 `patches/` 里的本地补丁，冲突就整体回滚），然后在 Actions 里点一下 **sync upstream** 也行。**别手工覆盖 `dailycheckin/`**，那样会丢掉本地修复。详见上面的「跟随上游更新」。

**Q：通知怎么变成两条了？我改了代码但没变化？**
先看通知结尾那行 **`项目地址`**：写着 `github.com/beacherz/dailycheckin-plus` 才是本项目镜像；如果写的是 `github.com/Sitoi/dailycheckin`，说明**你跑的还是旧镜像** —— 本项目是从镜像里装引擎的，改了源码不 `pull` 不会生效：

```bash
docker compose pull && docker compose up -d
```

通知里带标题（`【dailycheckin-plus 每日签到 · 日期】`）也是新镜像的标志。本项目**恒定只发一条**，不存在「消息条数」开关；如果你的容器已经更新、通知结尾也确实是本项目地址，却仍然收到多条，那是别的程序在发，按下面这条排查。

**Q：更新后还是收到两条，怎么排查？**
两个「会重复跑」的点都堵上了，但值得对一下：

1. **有几份 cron 在跑**。官方镜像迁过来、或以前手写过 crontab 的，容器里可能同时存在「裸的签到行」和面板写入的托管区块。打开「设置 → 定时签到」随便保存一次，面板会把裸行注释留档并接管（`python tools/test_schedule.py` 就是锁这条行为的）；也可以直接 `docker exec dailycheckin crontab -l` 看有没有两行 `&& dailycheckin`。
2. **有别的 bot / 另一份脚本在发**。`docker logs dailycheckin --tail 50` 对一下发送时间；本项目发通知时会打印推送渠道名，两边的日志时间对不上就说明是外部程序。

**Q：项目从 `dailycheckin-compose` 改名叫 `dailycheckin-plus` 了，我要做什么？**
三件事，各花一分钟：

1. **换镜像名**：旧镜像 `ghcr.io/beacherz/dailycheckin-compose` **已从 Packages 里删除**（再拉会报 403 denied），改用 `ghcr.io/beacherz/dailycheckin-plus:latest`。compose 用户把 `image:` 那行改掉；docker run 用户按上面「方式二」的最后一段重跑一次。
2. **容器名不用动**：`container_name: dailycheckin` 故意保持没改 —— 改了会变成「新容器 + 旧容器」两份同时在跑，通知就会收到两条。
3. **crontab 不用手动改**：老标记 `dailycheckin-compose managed` 面板照样认，保存定时设置时自动升级成新标记。

**Q：通知标题里的 `dailycheckin-plus` 能改成我自己的吗？**
通知标题里的项目名来自引擎里的 `PROJECT_NAME` 常量（`dailycheckin/utils/message.py`），跟着仓库名走；网页顶栏显示的则是 `PANEL_TITLE`（默认 `dailycheckin-plus`），这个可以用环境变量随便改。注意 `dailycheckin/` 目录是上游引擎源码，手工改动会在下次同步上游时被 `patches/` 覆盖，要改就走补丁（见「跟随上游更新」）。

**Q：B 站日志里「直播签到：签到活动已下线」是 bug 吗？**
不是。B 站自己下线了直播签到活动，任何工具都做不了，不影响其它签到项。

---

## 关于引擎源码里的 B 站修复

上游的分区视频接口 `/x/web-interface/dynamic/region` 已下线，返回 `{"code":-404,"data":null}`，而代码写的是 `ret.get("data", {}).get("archives", [])` —— key 存在只是值为 `None`，兜底默认值不生效，于是抛 `AttributeError`，被 `main()` 捕获成一句 `❌❌❌❌❌`。

本仓库已改用出入参一致的 `/x/web-interface/newlist`，并给 `data` 为 `None` 的几处调用补了空值兜底、空 `aid_list` 保护。该修复也已提 PR 到上游（[Sitoi/dailycheckin#592](https://github.com/Sitoi/dailycheckin/pull/592)），上游合并后本仓库可直接跟随。

这段修复以补丁形式保存在 `patches/0001-bilibili-newlist.patch`，同步上游时会自动重放。等上游合并了这个 PR，把该补丁文件删掉即可（同步工具按 `patches/` 目录里实际存在的补丁来跑），不用改代码。

---

## 本地开发

面板零额外依赖，直接在仓库根目录跑：

```bash
pip install -r requirements.txt     # 只有引擎需要（requests / pycryptodome / rsa / urllib3）
python -m panel                     # 默认监听 0.0.0.0:8080，工作目录取仓库根目录
```

即使 `requests` 没装好、引擎导入失败，面板也能起来并给出提示（站点清单退化成扫源码获取），不会白屏。

---

## 致谢与许可

- 签到引擎来自 [Sitoi/dailycheckin](https://github.com/Sitoi/dailycheckin)（作者 Sitoi），MIT License，版权归原作者所有。
- 本项目的网页管理后台、Docker 编排与部署体验为新增部分，同样以 MIT 发布。
