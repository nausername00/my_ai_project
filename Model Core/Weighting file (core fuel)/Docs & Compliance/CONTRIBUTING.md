# 贡献指南（CONTRIBUTING）

感谢你愿意为墨灵（Moling）贡献代码、文档或反馈！

## 行为准则

请阅读并遵守 [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md)。

## 本地开发环境

- Python 3.10+（推荐 3.11+），Node.js 20+，npm
- 可选：Ollama 服务与 `qwen2.5:3b` 模型（默认推理后端）

```powershell
# 后端测试（从仓库根目录）
py -3 -m pytest

# 前端语法检查与单元测试
Set-Location "Model Core\Weighting file (core fuel)\Frontend"
npm run check
npm test
```

## 提交流程

1. Fork 本仓库并创建特性分支：`git checkout -b feat/your-change`。
2. 提交信息使用约定式风格（如 `feat: 新增 ...`、`fix: 修复 ...`）。
3. 运行测试并确保通过；新增功能请附带测试。
4. 发起 Pull Request，描述改动动机与影响面。

## 代码约定

- Python：`from __future__ import annotations`、类型注解、中文或英文 docstring
  均可，但同一模块内保持一致；不引入未必要的运行时依赖
  （ML 依赖一律懒加载，缺失时给出清晰安装提示）。
- 前端：当前运行时为 vanilla JS（`renderer.js` + `index.html` + `style.css`）；
  `.tsx` 文件为迁移参考，引入构建链前不应被运行时加载。
- 路径含空格与括号（如 `Model Core\Weighting file (core fuel)`），
  脚本请始终用引号包裹路径。

## 模型与数据

模型权重文件不入库；涉及模型格式的改动请同步更新 `MODEL_CARD.md`。
新增环境变量请同步更新 `.env.example` 与 `README.md`。
