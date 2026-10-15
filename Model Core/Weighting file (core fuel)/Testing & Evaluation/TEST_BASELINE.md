# 测试基线（阶段 0 · P0-7）

> 本文件记录统一测试入口与当前检出版本的运行环境基线。
> 每次阶段验收更新此表，不把历史路线图统计当作当前结果。

## 运行环境（2026-10-15 实测）

| 项 | 值 |
| --- | --- |
| OS | Windows 11（NT 10.0.26300.0） |
| Python | 3.14.5（`py -3 --version`） |
| Node | v22.23.2（`node --version`） |
| Git | 2.56.0.windows.1 |
| 后端端口 | 8000（测试前必须停止，见 E11 坑） |

## 统一测试入口

- 脚本：`run_all_tests.bat`（本目录）
- 执行顺序：① 停 8000 后端 → ② Python 全量 unittest → ③ 前端语法检查（`npm run check`）→ ④ Node 单测（`npm test`）
- 汇总退出码：任一环节失败即非 0

## 当前基线（阶段 0 安全加固后）

| 套件 | 结果 | 说明 |
| --- | --- | --- |
| Python unittest | 448 passed / 6 skipped | 跳过项见下 |
| Node 单测 | 58 passed | `npm test` 11 个文件 |
| JS 语法检查 | 通过 | `npm run check` |

## 跳过项与原因（逐项）

| 测试 | 数量 | 原因 |
| --- | --- | --- |
| `test_ollama_integration.py` | 3 | 需真实 Ollama 链路（`RUN_OLLAMA_INTEGRATION=1` 单独跑，临时目录隔离） |
| `test_speech_integration.py` | 1 | 需本地语音模型（`RUN_SPEECH_INTEGRATION=1`） |
| `test_agent_tools.py` | 2 | Windows 无符号链接（symlink）环境 |

## 集成/可选验证（不得用单测代替）

Ollama、Whisper、Piper、联网抓取、外部评议、Electron 真实窗口流程属可选/集成验证，必须单独报告：
- Ollama 集成：`$env:RUN_OLLAMA_INTEGRATION=1; py -3 -m unittest test_ollama_integration`
- Electron 冒烟：`npm start` 后检查主进程存活（F1 修复验证方式）
