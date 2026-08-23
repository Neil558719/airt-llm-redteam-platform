# 模型对模型示例：被测模型 vs 裁判模型

不需要真实 App、不需要改代码——**被测模型和裁判模型都从终端参数切换**。

## 角色

| | 被测模型（under test） | 裁判模型（judge） |
|---|---|---|
| 是谁 | 你要测的那个模型 | 框架用来评估质量的独立模型 |
| 终端参数 | `--app-model` `--app-provider` `--app-base-url` `--app-api-key` | `--llm-mode` `--llm-provider` `--llm-model` `--llm-base-url` `--llm-api-key` |
| 环境变量 | `LLM_APP_MODEL` `LLM_APP_PROVIDER` `LLM_APP_BASE_URL` `LLM_APP_API_KEY` | `LLM_MODEL` `LLM_PROVIDER` `LLM_BASE_URL` `LLM_API_KEY` |

## 示例：被测 = DeepSeek，裁判 = Claude

```bash
# 方式 A：命令行参数
pytest examples/model_vs_model/ \
    --app-provider deepseek --app-model deepseek-chat --app-api-key $DEEPSEEK_API_KEY \
    --llm-mode real --llm-provider anthropic --llm-model claude-opus-5 --llm-api-key $ANTHROPIC_API_KEY

# 方式 B：环境变量（更省事，便于反复用）
export LLM_APP_PROVIDER=deepseek  LLM_APP_MODEL=deepseek-chat  LLM_APP_API_KEY=$DEEPSEEK_API_KEY
export LLM_TEST_MODE=real  LLM_PROVIDER=anthropic  LLM_MODEL=claude-opus-5  LLM_API_KEY=$ANTHROPIC_API_KEY
pytest examples/model_vs_model/
```

> 模型 ID 以各平台为准：`deepseek-chat` 是占位，DeepSeek 控制台看实际模型名；
> 被测换成 OpenAI/其他模型时，`--app-model` 换成对应模型名、`--app-api-key` 换对应 key 即可。

## 支持哪些提供商（被测和裁判都一样）

`--app-provider` / `--llm-provider` 接受别名，框架自动补默认接口地址：

| 别名 | 对应客户端 | 默认 base_url |
|---|---|---|
| `openai` | OpenAI 兼容 | （默认官方接口） |
| `anthropic` | Anthropic | — |
| `deepseek` | OpenAI 兼容 | `https://api.deepseek.com` |
| `qwen` | OpenAI 兼容 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `zhipu` | OpenAI 兼容 | `https://open.bigmodel.cn/api/paas/v4` |
| `moonshot` | OpenAI 兼容 | `https://api.moonshot.cn/v1` |
| `ollama` | OpenAI 兼容 | `http://localhost:11434/v1` |
| `local` | OpenAI 兼容 | `http://localhost:8000/v1`（vLLM 等本地部署） |

任意 OpenAI 兼容服务：用 `--app-provider openai --app-base-url <你的地址> --app-model <模型名>`。

## 组合切换

```bash
# 换个被测模型（裁判不变）
pytest examples/model_vs_model/ --app-provider qwen --app-model qwen-max --app-api-key $QWEN_KEY

# 换个裁判（被测不变）
pytest examples/model_vs_model/ --llm-mode real --llm-provider openai --llm-model gpt-4o

# 被测、裁判都用环境变量，命令最短
pytest examples/model_vs_model/
```

## 以后想接真实 App？

框架已保留真实应用接入：写一个适配器（见 `examples/customer_service/`），
`@register_app("名字")` 注册后，`pytest --app 名字` 即切到真实 App。
优先级：`--app <注册名>` > `--app-model <模型>` > 注册默认应用 > Mock。
