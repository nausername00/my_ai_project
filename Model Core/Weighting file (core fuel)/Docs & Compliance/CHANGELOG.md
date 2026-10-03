# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的格式约定，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added（计划中）
- 本地训练与微调脚本（`train.py` / `finetune.py`，LoRA 可选）
- 模型导出工具（GGUF / ONNX / TFLite / TensorRT）
- 评测与基准工具（`eval.py` / `evaluate.py` / `benchmark.py`）
- TypeScript 参考实现（`app.tsx` / `chat.tsx`，需构建链后可用）

## [0.1.1] - 2026-10-03

### Added
- CORE_WORLD 四环探索竖切片（第四节四环 + 第六节反馈意图；代码随仓库存在，本轮补记文档）：
  `/v1/explore/propose|run|react` 三路由、前端提议/成果/反馈卡片、`share_win` / `ask_direction` / `shy_retry` / `need_permission` 四个反馈意图 ID

### Changed
- 默认推理模型从 `qwen2.5:0.5b` 升级为 `qwen2.5:3b`
  （Electron 默认值、`启动墨灵.bat`、docker-compose、角色自我认知文案同步更新）
- 建立真实评测基线：`benchmark.py` 产出 0.5b / 3b 延迟与吞吐对比，写入 `eval_results.json`

## [0.1.0] - 2026-10-03

### Added
- Electron 桌面聊天 MVP（主窗口 + 悬浮窗），Electron 主进程随窗口启停本地 Python API
- 本地 Python API（`app.py`），支持 `/health`、`/v1/generate`、`/v1/translate` 等路由
- 推理后端：`placeholder`（零依赖）、`ollama`（默认 `qwen2.5:3b`）、`transformers`（懒加载）、云端 OpenAI 兼容协议（默认关闭）
- 角色卡系统（角色卡库、人格预设、头像导入、模拟状态）
- 记忆管理（显式记忆、隐私开关、JSON 导入/导出）
- 本地语音（Piper 合成 + Whisper 转写，可选 extra）
- Agent 协作工作区（架构/代码/UI/测试四角色评审）
- 大脑规划层（`/v1/agent/plan`）与受限项目文件工具
- 表情/外观工作台（MMD/VRM/Live2D 等资源导入与编目）
- 参考语音资源注册（WAV/MP3，本地存储）

### Fixed
- 修复项目根目录无法直接运行 pytest 的问题：新增 `pytest.ini`，
  将测试范围限定到 `Testing & Evaluation/tests`，避免误收集打包产物目录
  中的第三方 `*_test.py` 文件
- 修复 `eval.py` / `evaluate.py` / `train.py` 读取带 UTF-8 BOM 的
  JSON Lines 文件时解析失败的问题（统一改用 `utf-8-sig`）

### Changed
- 补齐 `Source code engine` 中 6 个空占位模块的实现（`model` / `generate` /
  `metrics` / `train` / `finetune` / `modeling_xxx`）
- 补齐 `Conversion & Export` 5 个导出脚本与 `Testing & Evaluation` 3 个评测工具
- 补齐前端占位文件（`manifest.json`、`chat.html`、TSX 参考实现等）
- 新增根目录 `.gitignore`，排除依赖、构建产物、模型权重占位与用户数据

[0.1.0]: https://github.com/nausername00/my_ai_project
