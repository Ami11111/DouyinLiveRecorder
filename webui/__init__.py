# -*- coding: utf-8 -*-
"""本地网页管理界面 (fork 新增, 与上游 ihmily/DouyinLiveRecorder 无关)。

设计约束:
  1. 本包内任何模块都不得 import main, 也不得 import src。
     主程序在启动时通过 start_webui(...) 把路径、锁、回调注入进来。
     这样 `python3 -c "import webui.server"` 是零副作用的, 便于单独测试。
  2. 只使用 Python 标准库, 不新增任何第三方依赖 (loguru 除外,
     它已经是主项目的依赖, 且 src/logger.py 已配好 sink)。
"""

__all__ = ['start_webui']


def __getattr__(name):
    # 延迟导入, 保证 `import webui` 本身不拉起 http.server 等模块
    if name == 'start_webui':
        from webui.server import start_webui
        return start_webui
    raise AttributeError(name)
