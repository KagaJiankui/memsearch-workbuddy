#!/usr/bin/env python3
# diag-hook 的配置模块（由旧版 ponytail diag.py 改名而来）。
# diag-hook.py 用 importlib 按路径加载本文件（文件名含连字符，不能直接 import）。
# 同名环境变量可临时覆盖下列常量，便于不改文件切换。

import os


def _env_bool(name, default):
    v = os.environ.get(name, "")
    if not v:
        return default
    return v.strip().lower() not in ("0", "false", "no", "off")


# 全局开关：False 时 diag-hook 只向 stdout 回合法 JSON、不读 stdin、不写日志。
# 覆盖：MEMSEARCH_DIAG_ENABLED=0/1
# ENABLED = _env_bool("MEMSEARCH_DIAG_ENABLED", True)
ENABLED = False

# 日志文件完整路径；留空 = 沿用内置候选链（stdin cwd → 工程根 → ~ → tempdir）。
# 支持 ~ 与 $VAR 展开，父目录不存在时自动创建。
# 覆盖：MEMSEARCH_DIAG_LOG=/abs/or/relative/path/to.log
LOG_PATH = os.path.expanduser(os.path.expandvars(os.environ.get("MEMSEARCH_DIAG_LOG", r"D:\Electronics\agent-plugins\workbuddy_plugin_memsearch\.memsearch-diag.log")))
