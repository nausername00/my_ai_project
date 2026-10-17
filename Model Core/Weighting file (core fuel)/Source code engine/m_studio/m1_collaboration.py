"""M1 · 多智能体环节：四角色评审「低模底座 + AI 有机贴图」方案并输出分工。

流程：Ollama qwen2.5:3b 本地推理 → collaboration.run_collaboration
（architecture/code/ui/testing 四角色分别给方案 → 综合共识）→ JSON 落盘。
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collaboration import run_collaboration  # noqa: E402
from inference import InferenceEngine, OllamaBackend  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "m1_collaboration_result.json")

SYSTEM_PROMPT = (
    "你是墨灵创作工作台的分身评审团。墨灵正在做 M1 最小演示："
    "用 Blender BPY 程序化建模一个低多边形底座（圆柱台座 + 锥体主体 + 圆环顶饰），"
    "再应用一张 AI 生成的有机装饰贴图作为材质纹理。请从你的专业视角给出建议。"
)

TASK = (
    "请评审以下方案并给出分工建议：\n"
    "1) 有机贴图应用在哪个部件最合适（台座侧面 / 锥体表面 / 圆环），为什么；\n"
    "2) 贴图应采用什么材质节点方案（Base Color 直贴 / 混合 / 法线辅助），需要什么 UV 处理；\n"
    "3) 装配顺序建议（先贴图后装配 vs 先装配后贴图），以及渲染验证要点；\n"
    "4) 指出这个最小演示最值得改进的一点。\n"
    "请用中文，输出 2-4 条简洁、可执行的意见。"
)


def main(argv: list[str] | None = None) -> int:
    """评审入口（含优化 2 模型分级/轻量模式）：
    --model qwen2.5:3b|qwen2.5:0.5b   推理模型分级（默认 3b）
    --light                            轻量模式：仅架构+代码 2 角色（无分歧时省一半推理）
    --out <json>                       输出路径
    """
    argv = argv if argv is not None else sys.argv[1:]
    model = "qwen2.5:3b"
    if "--model" in argv:
        model = argv[argv.index("--model") + 1]
    light = "--light" in argv
    out = OUT
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]

    backend = OllamaBackend(model_name=model, base_url="http://127.0.0.1:11434")
    engine = InferenceEngine(backend)
    if light:
        # 轻量模式：只保留架构 + 代码两个角色（方向明确时足够，省一半推理）
        import collaboration
        role_configs = [
            {"key": c.key, "enabled": True, "instruction": c.instruction}
            for c in collaboration.COLLABORATORS if c.key in ("architecture", "code")
        ]
    else:
        role_configs = None
    result = run_collaboration(engine, SYSTEM_PROMPT, TASK, role_configs=role_configs)
    result["meta"] = {"model": model, "light": light, "roles": len(result.get("collaborators", []))}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[M1-collab] saved -> {out}")
    print(f"lead={result.get('lead')} model={model} light={light} "
          f"roles={result.get('meta', {}).get('roles')} synthesis_error={result.get('synthesis_error')}")
    for c in result.get("collaborators", []):
        print(f"  - {c.get('name')}/{c.get('focus')}: status={c.get('status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
