"""确保 Dify 适配器被加载，否则 `@register_app("dify")` 不会执行，
pytest --app dify 会报「未注册的被测应用: 'dify'」。

pytest 会自动收集并执行本目录的 conftest.py，这里 import adapter
即触发模块级注册。测试文件本身不 import adapter（避免循环依赖）。
"""

import adapter  # noqa: F401  触发 @register_app("dify")
