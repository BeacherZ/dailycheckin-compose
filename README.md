# dailycheckin-compose

**给 [Sitoi/dailycheckin](https://github.com/Sitoi/dailycheckin) 配了一个网页管理后台，一条 `docker compose up -d` 就能用。**

签到引擎沿用原项目（MIT，已内置 B 站接口修复），管理后台是本项目新增的。

---

## 它解决什么问题

原项目的签到逻辑很成熟，但配置体验对小白的门槛不低：

| 原始体验 | 本项目 |
|---|---|
| 手工编辑 `config.json`，JSON 写错一个逗号就不跑 | 网页表单，点保存 |
| cookie 必须用 `; `（分号 + 空格）分隔，从浏览器直接复制常常不满足，失败还没提示 | 粘贴什么格式都行，自动规范化成引擎要的形态 |
| cookie 过期了没有提示，只能翻日志猜 | 网页上直接标注 ✅ 有效 / ❌ 失效 |
| 不知道某个站到底要哪几个 cookie 字段 | 每个站点标注必填字段，缺了就高亮 |
| 改定时时间要进容器改文件 | 网页上选周期，保存即生效 |

---

## 快速开始

```bash
git clone https://github.com/BeacherZ/dailycheckin-compose.git
cd dailycheckin-compose
cp .env.example .env        # 可选：改端口、设访问口令
docker compose up -d
```

然后浏览器打开 **`http://你的NAS地址:8080`**（端口在 `.env` 的 `WEB_PORT` 里改）。

> **群晖 / 威联通**：把仓库放到共享文件夹，用 Container Manager（群晖）或 Container Station 的「项目 / 应用程序」指向这个目录即可，会自动读 `docker-compose.yml`。
> 第一次构建要装 python 依赖，大约 1～2 分钟。

启动后：

1. 在首页找到要签到的站点（比如「哔哩哔哩」），点开
2. 粘贴 cookie，点「规范化」
3. 点「校验 cookie」确认登录态
4. 点「保存」，就完事了 —— 之后每天由容器内的 cron 自动签到

---

## 网页后台怎么用

### 1. 加 cookie：粘贴就完事

面板能识别下面这些形态，全部会自动转成引擎要的格式：

| 你粘贴的内容 | 例子 |
|---|---|
| 浏览器复制的 cookie 串 | `SESSDATA=xxx; bili_jct=yyy` |
| 没有空格的分号串 | `SESSDATA=xxx;bili_jct=yyy` |
| 每行一个字段（从 Cookie 表格直接拖选） | `SESSDATA=xxx`<br>`bili_jct=yyy` |
| DevTools 表格整块复制（带 Tab 和域名列） | `SESSDATA<TAB>xxx<TAB>.bilibili.com<TAB>/` |
| JSON 导出（对象 / `[{name,value}]` 数组） | 各类 cookie 插件导出的格式 |
| 带 `Cookie:` 前缀，或整条 curl 命令 | `curl '...' -H 'Cookie: SESSDATA=xxx'` |

**为什么一定要规范化？** 引擎源码里几乎所有站点都是这么解析 cookie 的：

```python
{item.split("=")[0]: item.split("=")[1] for item in cookie.split("; ")}
```

它硬依赖 `"; "` 作为分隔符 —— 用 `;` 没空格、或者换行分隔，整条 cookie 都会被解析错。面板会把分隔符补齐成 `"; "`，并在结尾补上 `;`。

### 2. 三级校验：格式 / 登录态 / 真实运行

| 层级 | 怎么触发 | 特点 |
|---|---|---|
| **格式体检** | 粘贴后自动、无需点击 | 不联网，秒出。告诉你识别出几个字段、**缺哪个必填字段**、有没有隐患字符 |
| **在线校验** | 卡片里的「校验 cookie」 | 请求站点自己的登录态接口，返回昵称 / 等级 / 硬币余额，或明确的失效原因。**这是唯一能判定「有效 / 失效」的强证据** |
| **运行校验** | 「立即签到」/「全部签到」 | 跑一遍真实签到。失败一定说明有问题（连错误原因一起写进状态）；但**成功不等于 cookie 有效**，见下面说明 |

校验结果会持久化，卡片左边有颜色条和徽章：🟢 有效 / 🔴 失效 / 🟡 无法判定 / ⚪ 未校验。

> **为什么「跑通」不等于「有效」？**
>
> 上游引擎里有不少站点模块，遇到无效 cookie 时是**静默返回**的。比如 B 站模块 `main()` 开头就是 `if is_login:`，登录态不成立时直接跳过，一个异常都不抛，引擎照样打一排 ✅。
>
> 所以面板的处理规则是：**接口判定为 ❌ 的站点，跑签到即使没报错，也继续标 ❌**，并在原因里写清楚「该站点模块对无效 cookie 是静默返回的，以接口判定为准」。反过来说，想确认 cookie 是不是真的有效，请点「校验 cookie」，别只看签到输出。

> 在线校验遇到网络不通、接口改版这类情况，会老老实实报「**无法判定**」，而不是误报失效 —— 这时候点「立即签到」看真实结果更靠谱。

修改某个站点的 cookie 后，它的旧校验结果会**自动作废回到 ⚪ 未校验**，不会让你对着过期的结论做判断。

### 3. 跑签到

- **单站点**：卡片里的「立即签到」
- **全部**：右上角「全部签到」
- 输出实时显示在右侧抽屉里，可以随时切去看历史任务和引擎日志

### 4. 定时任务

「设置」→ 定时签到：选预设周期（每天 09:00 / 每天 00:30 / 每 6 小时 / 工作日 09:00）或自己填 cron，保存后立刻装进容器内的 crontab 并生效。

面板只改 crontab 里一段带标记的区块，你自己加的其它定时任务不受影响：

```cron
# >>> dailycheckin-compose managed >>>
0 9 * * * cd /dailycheckin && dailycheckin >> /dailycheckin/logs/dailycheckin.log 2>&1
# <<< dailycheckin-compose managed <<<
```

### 5. 推送通知

「设置」→ 推送通知，支持原项目的全部渠道（PushPlus、企业微信、Telegram、Bark、钉钉、飞书、Gotify、ntfy、Server 酱、Qmsg）。填了就会把签到结果推给你。

### 6. 兜底能力

- **config.json 直接编辑**：设置页有原文编辑器和语法校验（写错 JSON 会拒绝保存）
- **自动备份**：每次保存前留一份时间戳备份，最多 30 份，面板里可一键恢复
- **旧配置导入**：原来官方的 `config/config.json` 直接复制到本项目的 `config/` 目录即可，两边格式完全一致

---

## 支持的站点

站点清单从引擎里**自动发现** —— 上游加了新站点，面板刷新就会出现，不用改代码。
下面是当前 16 个站点，以及从引擎源码里逐个核对出来的必填 cookie 字段：

| 站点 | KEY | 凭据 | 必填 cookie 字段 | 在线校验 |
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
| 全民 K 歌 | `KGQQ` | Cookie | `uid`、`openid`、`openkey` | 用运行校验 |
| 阿里云盘 | `ALIYUN` | refresh_token | — | 用运行校验 |
| i 茅台 | `IMAOTAI` | 表单 | `token`、`userid`、`mobile`… | 用运行校验 |
| AcFun | `ACFUN` | 账号密码 | — | 用运行校验 |
| 小米运动 | `MIMOTION` | 账号密码 | — | 用运行校验 |
| 百度站点提交 | `BAIDU` | 表单 | — | 用运行校验 |

> 「用运行校验」的站点没有公开的登录态接口，直接点「立即签到」，成功与否就是最准的答案。

---

## 目录结构

```
.
├── docker-compose.yml          # 一键部署
├── Dockerfile                  # 引擎 + 面板
├── .env.example                # 端口 / 口令 / 时区
├── panel/                      # 网页管理后台（纯 Python 标准库，零额外依赖）
│   ├── server.py               # HTTP 服务与所有接口
│   ├── cookies.py              # cookie 解析与规范化
│   ├── catalog.py              # 站点元数据（必填字段、校验方式、怎么拿 cookie）
│   ├── verify.py               # 各站点在线登录态校验
│   ├── runner.py               # 跑签到、解析输出、回写有效/失效状态
│   ├── store.py                # config.json 读写 + 备份
│   ├── schedule.py             # crontab 管理
│   └── static/                 # 单页界面（原生 HTML/CSS/JS，无构建步骤）
├── dailycheckin/               # 签到引擎（来自上游，含 B 站接口修复）
└── docker/entrypoint.sh        # 容器入口：准备配置 → 装定时任务 → 起 crond + 面板
```

运行时的 `config/`、`cron/`、`logs/`、`data/` 四个目录会挂载到宿主机，容器重建不丢数据。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `WEB_PORT` | `8080` | 映射到宿主机的端口 |
| `PANEL_TOKEN` | 空 | 面板访问口令。留空不校验；映射到公网**务必**设置 |
| `PANEL_TITLE` | `签到管理面板` | 页面标题 |
| `TZ` | `Asia/Shanghai` | 时区，影响定时任务时间 |
| `DC_HOME` | `/dailycheckin` | 工作目录，一般不用改 |
| `PANEL_RUN_TIMEOUT` | `1800` | 单次签到任务超时秒数（贴吧号多会跑很久） |

---

## 常见问题

**Q：我的 cookie 存在哪儿？安全吗？**
存在宿主机 `./config/config.json` 里，和引擎原生格式完全一样，**不会**上传到任何地方。项目已把 `config/` 加进 `.gitignore`，不会误提交。
但要注意：面板默认**不带鉴权**，同一局域网内谁都能打开。映射到公网请务必在 `.env` 里设 `PANEL_TOKEN`，或套一层带 HTTPS 的反向代理。

**Q：提示「某个字段的值里含 `=`，会被截断」是什么意思？**
引擎用 `cookie.split("=")[1]` 取值，值里再出现 `=` 就只取到第二个 `=` 之前的部分。Base64 结尾的填充符 `=` 正好会踩这个坑。这不是面板的 bug，是上游解析方式的限制 —— 如果该站点签到报签名/校验错误，可以把那个字段手工裁剪一下再试。

**Q：校验显示「无法判定」是不是 cookie 坏了？**
不一定。网络不通、站点接口改版、被风控拦截都会是「无法判定」。这种情况点「立即签到」，用真实运行结果判断更准确。

**Q：定时任务没生效？**
容器内的 cron 是关键，先看 `docker logs dailycheckin` 里有没有「定时任务已装载」。另外确认「设置 → 定时签到」是开着的。cron 不会继承容器环境变量，所以默认 crontab 头部显式写了 `TZ` 和 `PATH`。

**Q：从官方镜像 `sitoi/dailycheckin` 迁过来要做什么？**
先把旧容器停掉并删除 —— 本项目的容器名也叫 `dailycheckin`，不清理会撞名：

```bash
docker stop dailycheckin && docker rm dailycheckin
# 或者原来是用 compose 起的，就进原目录 docker compose down
```

然后把原 `config/config.json` 复制到本项目的 `config/` 目录，`docker compose up -d` 即可。
格式一模一样，站点和账号都会自动识别出来。原来那套「pip 升级后手打补丁」的 cron 也可以删掉了。

**Q：为什么镜像里 `/dailycheckin` 下没有 `dailycheckin` 源码目录？**
引擎是用 `pip install .` 装进 site-packages 的，面板自己不需要安装（纯标准库）。想改引擎代码，改仓库里的 `dailycheckin/` 再 `docker compose build` 即可。

**Q：B 站日志里「直播签到：签到活动已下线」是 bug 吗？**
不是。B 站自己下线了直播签到活动，任何工具都做不了，其它签到项目不受影响。

**Q：怎么升级？**
```bash
git pull
docker compose up -d --build
```

---

## 关于引擎源码里的 B 站修复

上游的分区视频接口 `/x/web-interface/dynamic/region` 已下线，返回 `{"code":-404,"data":null}`，而代码写的是 `ret.get("data", {}).get("archives", [])` —— key 存在只是值为 `None`，兜底默认值不生效，于是抛 `AttributeError`，被 `main()` 捕获成一句 `❌❌❌❌❌`。

本仓库已改用出入参完全一致的 `/x/web-interface/newlist`，并顺带对 `data` 为 `None` 的几处调用加了空值兜底、空 `aid_list` 保护。修复也已作为 PR 提到上游（[Sitoi/dailycheckin#592](https://github.com/Sitoi/dailycheckin/pull/592)），上游合并后本仓库可以直接跟随。

---

## 本地开发

面板不需要任何额外依赖，直接在仓库根目录跑：

```bash
pip install -r requirements.txt     # 只有引擎需要（requests / pycryptodome / rsa / urllib3）
python -m panel                     # 默认监听 0.0.0.0:8080，工作目录取仓库根目录
```

一个好处是：即使 `requests` 还没装好、引擎导入失败，面板也能起来并给出提示（站点清单会退化成扫源码获取），不会白屏。

## 致谢与许可

- 签到引擎来自 [Sitoi/dailycheckin](https://github.com/Sitoi/dailycheckin)（作者 Sitoi），MIT License，版权归原作者所有。
- 本项目的网页管理后台、Docker 编排与部署体验为新增部分，同样以 MIT 发布。
