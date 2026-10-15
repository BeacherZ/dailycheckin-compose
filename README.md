# dailycheckin-compose

**给 [Sitoi/dailycheckin](https://github.com/Sitoi/dailycheckin) 加了一个网页管理后台。一条 `docker compose up -d`，浏览器里点几下就配好了。**

[![build](https://github.com/BeacherZ/dailycheckin-compose/actions/workflows/build.yml/badge.svg)](https://github.com/BeacherZ/dailycheckin-compose/actions/workflows/build.yml)
[![ghcr](https://img.shields.io/badge/ghcr.io-dailycheckin--compose-2496ed?logo=docker&logoColor=white)](https://github.com/BeacherZ/dailycheckin-compose/pkgs/container/dailycheckin-compose)
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
| 每次签到推送一堆消息，一条一个站 | 合并成一条，站点之间用分隔行隔开 |

---

## 功能一览

**网页后台**

- 🔐 **首次打开引导设置账号密码**，之后需登录；设置页可随时改账号密码、退出登录
- 🧩 **16 个签到站点**，卡片 / 列表两种视图，带官网 LOGO，支持搜索、分类筛选、只看待配置
- 🍪 **粘贴即用**：浏览器复制、JSON 导出、DevTools 表格、curl 命令 —— 全都能识别并规范化
- ✅ **cookie 有效性判定**：本地格式体检 → 在线登录态校验 → 真实运行校验，三级递进
- 🎯 **每个站点标注必填字段**，缺哪个高亮哪个
- ▶️ 单站「立即签到」/ 一键「全部签到」，输出实时滚动
- ⏰ **定时任务**网页配置，只改自己那段 crontab，不动你别的任务
- 🔔 推送渠道全覆盖，**支持合并成一条**
- 🛡️ `config.json` 原文编辑 + 每次保存前自动备份（保留 30 份，可一键恢复）

**运行时**

- 纯 Python 标准库实现的 Web 服务，**零额外框架依赖**，x86 / arm64 / armv7 都能跑
- 密码只存 PBKDF2 派生值 + 随机盐，会话是签名票据（面板重启不掉线）
- 登录失败按 IP 限速，挡最基础的爆破
- 多阶段镜像，`python:3.9-slim` 打底，带健康检查

---

## 快速开始

在任意目录新建 `docker-compose.yml`：

```yaml
services:
  dailycheckin:
    image: ghcr.io/beacherz/dailycheckin-compose:latest
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

浏览器打开 **`http://你的地址:8080`** —— 第一次会引导你设置后台账号密码，设完就进后台了。

> **群晖 / 威联通**：把上面的 compose 内容贴进 Container Manager（群晖）或 Container Station 的「项目 / 应用程序」即可。
> **想改端口**：把 `8080:8080` 左边那个数字改掉，例如 `9000:8080`。

### 数据放在哪

上面 `volumes` 的四个目录会出现在 compose 文件同级：

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

- **卡片视图**：每站一张卡，左边一条颜色条表示 cookie 状态，右上角是分类标签和状态徽章
- **列表视图**：一行一个站，信息更密，适合站点多的时候快速定位（右上角「卡片 / 列表」切换）
- 顶部搜索框按站点名或 `KEY` 过滤（快捷键 `/`）
- 分类下拉按平台类型筛；「只看待配置」一键隐藏已经配好的
- 每个站都带官网 LOGO，加载不出来会回退成图标

点卡片标题就能展开配置区。

### 3️⃣ 加 cookie

展开卡片，把 cookie 整块粘进文本框就行。面板认这些形态：

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

### 4️⃣ 判断 cookie 到底有没有效

三级递进，可信度从低到高：

| 层级 | 怎么触发 | 说明 |
|---|---|---|
| **格式体检** | 粘贴后自动，不用点 | 不联网，秒出。告诉你识别出几个字段、**缺哪个必填字段** |
| **在线校验** | 卡片里「校验 cookie」 | 请求站点的登录态接口，返回昵称 / 等级 / 余额，或明确的失效原因。**这是判定有效/失效的强证据** |
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

### 5️⃣ 跑签到

- 单站：卡片内「立即签到」
- 全部：右上角「全部签到」
- 输出实时显示在右侧抽屉，可切「当前任务 / 历史任务 / 签到日志」三个标签页

### 6️⃣ 定时签到

「设置 → 定时签到」：选预设（每天 09:00 / 每天 00:30 / 每 6 小时 / 工作日 09:00）或自己填 cron，保存即写入容器 crontab 并生效。

面板只动自己那段带标记的区块，你其它定时任务不受影响：

```cron
# >>> dailycheckin-compose managed >>>
0 9 * * * cd /dailycheckin && dailycheckin >> /dailycheckin/logs/dailycheckin.log 2>&1
# <<< dailycheckin-compose managed <<<
```

### 7️⃣ 推送通知

「设置 → 推送通知」，渠道沿用上游全部支持：PushPlus、企业微信、Telegram、Bark、钉钉、飞书、Gotify、ntfy、Server 酱、Qmsg。只填自己要用的那几项，其它留空。

顶部的「**消息条数**」默认是 **合并成一条**，各站点结果之间用分隔行隔开，末尾补上任务元信息：

```text
「V2EX 论坛」
帐号信息: BZGOGO
今日签到: 20261015 的每日登录奖励 14 铜币
帐号余额: 38246.34

——————————————

「哔哩哔哩」
第 1 个账号: ✅✅✅✅✅

——————————————

开始时间: 2026-10-15 22:44:52
任务用时: 0 秒
当前版本: 25.12.9
```

想每站单独一条就切到另一个选项。

### 8️⃣ 兜底能力

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
| `PANEL_TITLE` | `签到管理面板` | 页面标题 |
| `PANEL_USERNAME` | 空 | 想跳过「首次打开手动设置」时，配合下一项直接建号 |
| `PANEL_PASSWORD` | 空 | 同上，只在后台还没初始化时生效 |
| `PANEL_TOKEN` | 空 | **可选**的脚本口令，给 curl / 自动化用；认证走 `X-Panel-Token` 头或 `?token=`，**不能替代登录**，也不建议开在公网 |
| `PANEL_RUN_TIMEOUT` | `1800` | 单次签到任务超时秒数（贴吧号多要跑很久） |
| `DC_HOME` | `/dailycheckin` | 工作目录，一般不用改 |

---

## 从源码构建

不想用现成镜像、或者改了引擎源码，用仓库里的 `docker-compose.build.yml`：

```bash
git clone https://github.com/BeacherZ/dailycheckin-compose.git
cd dailycheckin-compose
docker compose -f docker-compose.build.yml up -d --build
```

第一次要装 Python 依赖，大约 1～2 分钟。之后升级：

```bash
git pull
docker compose -f docker-compose.build.yml up -d --build
```

---

## 目录结构

```
.
├── docker-compose.yml          # 一键部署（用 ghcr.io 现成镜像）
├── docker-compose.build.yml    # 从源码构建版
├── Dockerfile                  # 引擎 + 面板，多阶段构建
├── panel/                      # 网页管理后台（纯标准库，零额外依赖）
│   ├── server.py               # HTTP 服务、路由、鉴权
│   ├── auth.py                 # 后台账号密码与会话票据
│   ├── cookies.py              # cookie 解析与规范化
│   ├── catalog.py              # 站点元数据（必填字段、LOGO、怎么拿 cookie）
│   ├── verify.py               # 各站点在线登录态校验
│   ├── runner.py               # 跑签到、解析输出、回写有效性状态
│   ├── store.py                # config.json 读写 + 备份
│   ├── schedule.py             # crontab 管理
│   └── static/                 # 单页界面（原生 HTML/CSS/JS，无构建步骤）
├── dailycheckin/               # 签到引擎（来自上游，含 B 站接口修复）
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

**Q：B 站日志里「直播签到：签到活动已下线」是 bug 吗？**
不是。B 站自己下线了直播签到活动，任何工具都做不了，不影响其它签到项。

---

## 关于引擎源码里的 B 站修复

上游的分区视频接口 `/x/web-interface/dynamic/region` 已下线，返回 `{"code":-404,"data":null}`，而代码写的是 `ret.get("data", {}).get("archives", [])` —— key 存在只是值为 `None`，兜底默认值不生效，于是抛 `AttributeError`，被 `main()` 捕获成一句 `❌❌❌❌❌`。

本仓库已改用出入参一致的 `/x/web-interface/newlist`，并给 `data` 为 `None` 的几处调用补了空值兜底、空 `aid_list` 保护。该修复也已提 PR 到上游（[Sitoi/dailycheckin#592](https://github.com/Sitoi/dailycheckin/pull/592)），上游合并后本仓库可直接跟随。

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
