"""Brain 运行期数据目录（库文件 / 遗留 JSON）——与代码 checkout 解耦。

历史默认：数据库就在代码目录里（`server/data/`），换代码 / 重新部署会连数据一起动。
生产（Mac runtime）用 `BRAIN_DATA_DIR` 把数据指到 checkout 之外，例如：

    BRAIN_DATA_DIR=/Users/gaolei/database/home-agent-brain

优先级（与既有行为一致，单库覆盖仍然最高）：

    <库自己的 *_PATH>  >  BRAIN_DATA_DIR  >  <server>/data

注意：**惰性读取**。`home_brain.py` 在 import `db` 之后才加载 `server/.env`
（`import db` 在第 34 行，`_load_dotenv` 在第 197 行），所以调用方不要把这个目录
在模块顶层算成常量，要在函数里现取（`db.db_path()` / `dev_console_db.db_path()` 等已如此）。
"""

from __future__ import annotations

import os
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def data_dir() -> Path:
    """Brain 运行期数据目录（绝对路径；不建目录，由写入方自己 mkdir）。"""
    env = (os.environ.get("BRAIN_DATA_DIR") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return (_HERE / "data").resolve()


def data_file(name: str) -> Path:
    """数据目录下的一个文件（`data_file("brain.sqlite3")`）。"""
    return data_dir() / str(name)
