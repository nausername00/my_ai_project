"""T1 待办：trio 真实模型验收（ollama qwen2.5:0.5b）。

用临时目录承载 CharacterStore（只读复用项目真实角色卡，
运行痕迹不污染源码/角色目录）。
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.environ.get("ENG", os.path.abspath(".")))
from inference import InferenceEngine
from avatar_trio import run_trio, list_trio_roles

from character import CharacterStore


def main() -> int:
    print("== 角色清单 ==")
    for role in list_trio_roles():
        print(f"  {role['name']} ({role['key']}) — {role['focus']}")

    engine = InferenceEngine.from_environment()
    print(f"\n== 引擎 ==")
    print(f"  backend={type(engine.backend).__name__} model={engine.model_name}")

    # 只读复用项目真实角色卡：拷入临时目录再构造，避免在源码/角色目录写痕迹
    project = Path(__file__).resolve().parents[2]  # .../Model Core/Weighting file (core fuel)
    real_card = project / "Character" / "characters" / "default.json"
    with tempfile.TemporaryDirectory(prefix="moling_trio_acc_") as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "characters").mkdir(parents=True, exist_ok=True)
        if real_card.is_file():
            shutil.copy2(real_card, tmp_path / "characters" / "default.json")
        store = CharacterStore(
            str(tmp_path / "characters" / "default.json"),
            str(tmp_path / "memory.json"),
            str(tmp_path / "assets"),
        )
        prompt = store.build_system_prompt(context_text="测试三角协作全链路。")
        result = run_trio(
            engine, prompt, "周末怎么安排陪墨灵的时间最合理？", max_rounds=1
        )
        print(f"\n== 三角结果 ==")
        print(
            f"  rounds_used={result['rounds_used']} model={result['model']} "
            f"source={result['source']} duration_ms={result['duration_ms']}"
        )
        for round_ in result["rounds"]:
            text = round_["response"][:200].replace("\n", " ")
            print(f"  [{round_['name']}] verdict={round_.get('verdict', '-')}")
            print(f"      {text}...")
        print(
            f"  [调和·衡] action={result['decision']['action']} "
            f"reason={result['decision']['reason'][:80]}"
        )
        print(f"      final={result['decision']['final'][:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
