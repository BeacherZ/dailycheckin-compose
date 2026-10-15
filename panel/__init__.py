"""dailycheckin 网页管理面板。

* 在浏览器里维护各站点的 cookie，粘贴即自动规范化成引擎要的格式
* 本地格式体检 + 在线登录态校验，一眼看出哪个 cookie 已经失效
* 一键跑签到 / 单站点签到，实时看输出
* 定时任务在网页里开关和调整
"""

from .server import PANEL_VERSION

__version__ = PANEL_VERSION
__all__ = ["__version__"]
