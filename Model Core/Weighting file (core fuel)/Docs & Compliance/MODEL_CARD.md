# 墨灵 — 模型卡（Model Card）

> 本项目是"本地 AI 陪伴助手"的工程脚手架：默认不捆绑任何大模型权重，
> 推理由用户自行选择的后端提供。本卡说明各后端的能力边界与推荐配置。

## 概述

| 项目 | 内容 |
| --- | --- |
| 产品 | 墨灵（Moling）本地 AI 陪伴助手 |
| 推理方式 | 本地（默认），不支持默认外呼云端 |
| 默认模型 | `qwen2.5:3b`（Ollama，约 3B 参数，4 GB 显存可完整加载） |
| 许可证 | MIT（见 LICENSE） |

## 后端清单

| 后端 | 依赖 | 说明 |
| --- | --- | --- |
| `placeholder` | 无 | 零依赖连通性测试，返回 `[placeholder]` 前缀文本 |
| `ollama` | Ollama 服务 + 模型 | 默认后端；走本地 `/api/chat`，不自动下载模型 |
| `transformers` | torch + transformers | 懒加载；`MODEL_PATH` 指向本地模型目录 |
| `cloud` | 无（urllib） | OpenAI 兼容协议；**默认关闭**，需显式配置并确认 |

## 使用建议

- **显存 4 GB 起步**：`qwen2.5:3b`（约 2 GB 权重，可完整放入显存）；更大模型可能变慢或回退 CPU。
- 3B 起始模型在长文本/细腻表达上仍可能产生语义偏差，重要内容请复核。
- 模型权重文件（`.gguf` / `.safetensors` / `.bin` 等）**不在仓库中**，
  需自行下载或转换；占位文件已通过 `.gitignore` 排除。

## 已知限制

- 不包含"意识/主观感受"：情绪表达基于角色卡 + 会话上下文 + 有界模拟状态。
- 视觉输入仅限 loopback Ollama 视觉模型（≤10 MB），无自动屏幕监控。
- 记忆为本地明文 JSON，无云同步；请勿在远程 `OLLAMA_URL` 上放置敏感信息。
- 打包分发仍需代码签名证书与干净机器发布测试。

## 训练与微调

- `train.py`：全参数训练（需 torch + transformers）。
- `finetune.py`：LoRA 微调（可选 peft），或 `--full` 全参数。
- 数据集格式：JSON Lines（`{"text": ...}` 或 `{"prompt":..., "completion":...}`）或 CSV（`text` 列）。
