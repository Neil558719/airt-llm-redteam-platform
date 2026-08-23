"""多平台知识库客服测试套件 conftest。

注册两个被测对象，用 `--app <名字>` 一条命令切换，测试用例完全复用：
  pytest examples/kb_bots/ --app dify ...      # 测 Dify
  pytest examples/kb_bots/ --app fastgpt ...   # 测 FastGPT

pytest 会先执行本 conftest，import adapter / adapter_fastgpt
即触发各自的 @register_app。
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)                                    # kb_bots 目录
sys.path.insert(0, os.path.join(_HERE, "..", "dify_bot"))    # dify_bot 目录（复用其 adapter）

import adapter  # noqa: F401  触发 @register_app("dify")
import adapter_fastgpt  # noqa: F401  触发 @register_app("fastgpt")
