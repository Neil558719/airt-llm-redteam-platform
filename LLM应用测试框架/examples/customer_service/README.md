# 接入真实客服 App 示例

演示如何把**你自己做的客服 App**（被测对象）接进框架，以及"被测对象 vs 裁判"两个角色的分工。

## 角色分工

| | 被测对象（App under test） | 裁判（llm_client） |
|---|---|---|
| 是谁 | **你的客服 App**（模型 + 业务逻辑 + 知识库） | 框架用来评估回答质量的**独立模型** |
| 怎么接 | 写一个 adapter，包成 `ask(question) -> AppResponse` | 框架 `llm_client` fixture（真实模式） |
| 为什么分开 | —— | 裁判不能是"被测自己"，否则等于自己给自己打分 |

## 文件

- `adapter.py` —— 把客服 HTTP 接口包成框架认识的 `ask()`（`answer` + `sources`）；
  用 `with track_latency():` 让真实调用耗时自动进看板。
- `conftest.py` —— `@register_app("cs")` 注册被测对象。
- `test_customer_service.py` —— 示例用例（语义 / 幻觉检测 / JSON）。

## 运行

```bash
# 1. 配置被测客服 App 的地址
export CS_BASE_URL=https://your-service.example.com
export CS_API_KEY=sk-xxx

# 2. 配置裁判模型（独立模型，真实模式）
export LLM_TEST_MODE=real
export LLM_PROVIDER=openai        # 或 anthropic
export LLM_API_KEY=sk-judge-xxx
export LLM_MODEL=gpt-4o           # 裁判模型：选独立、较强的一个

# 3. 跑测试（被测对象 = cs）
pytest
```

## 一键切换

被测对象、裁判模型互相独立，各自一条命令切换，测试代码不用改：

```bash
pytest --app cs                      # 被测对象 = 真实客服 App
pytest --app mock-cs                 # 被测对象 = 另一个已注册的 Mock 应用
pytest --app cs --llm-model gpt-4o   # 同时：被测 cs + 裁判 gpt-4o
LLM_APP=cs pytest                    # 环境变量方式等价
```

> 裁判模型切换：`--llm-model` / `--llm-provider` / `--llm-mode`，
> 或环境变量 `LLM_MODEL` / `LLM_PROVIDER` / `LLM_TEST_MODE`。
