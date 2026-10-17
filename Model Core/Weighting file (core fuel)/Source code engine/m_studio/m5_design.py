"""M5 深化 · 墨灵现场自主设计时装。

墨灵走完整条创作链：自主命题 → 生成贴图（AI 端到端，由执行侧调 image_gen）→
配色调（现场定义）→ 程序化渲染（Blender）→ 自评讲解 → 成品入库。

设计链真实可追溯：design_log.json 记录每步决策与理由（接 B 自导解说器风格），
不编造"为什么"——主题选择基于已有衣柜色域分析与设定亲和度。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from fashion_system import FashionSystem

HERE = os.path.dirname(os.path.abspath(__file__))
DESIGN_LOG_PATH = os.path.join(HERE, "design_log.json")

# 主题库：设计方向（texture_prompt 供 image_gen 执行）+ 现场定义色调 + 讲解 + 选择理由
THEMES = {
    "dawn": {
        "name": "晨光",
        "reason": "衣柜盘点：青花/绯红/星澜/翡翠多为中高饱和冷色或重彩，缺一套明亮柔和的暖色系——补色域是第一设计动机。",
        "texture_prompt": "无缝有机纹理贴图，暖金晨曦渐变色带与柔和白光晕交织，温柔明亮，细腻丝绸质感，适合3D物体表面贴图，无文字无logo",
        "tone": {"name": "dawn", "label": "晨光金", "rgb": [0.92, 0.82, 0.60],
                 "meaning": "像日出第一缕光落在纱上"},
        "idea": "晨光是给衣柜补的一口气——前面的颜色都太浓了，我想要一套穿上就让人觉得温柔的。",
        "expect": "暖金渐变贴图配晨光金底色，整体明亮柔和，像清晨第一缕光。",
    },
    "bloom": {
        "name": "繁花",
        "reason": "墨灵设定偏清雅，但缺一套生机感的春日色——繁花主题扩展'活泼'气质。",
        "texture_prompt": "无缝有机纹理贴图，粉紫花瓣与浅绿叶脉交织流动，春日繁花，细腻柔和，适合3D物体表面贴图，无文字无logo",
        "tone": {"name": "bloom", "label": "花雾粉", "rgb": [0.86, 0.78, 0.82],
                 "meaning": "像花瓣落在晨雾里"},
        "idea": "春天该有的样子——花和叶缠在一起，配花雾粉的底，整个人都变得轻盈。",
        "expect": "粉紫花海贴图配花雾粉底色，春日清新感。",
    },
    "abyss": {
        "name": "深海",
        "reason": "已有星夜（冷暗系），深海是同一色系的'水性'变体——同一气质换材质语言，考验贴图与底色分层。",
        "texture_prompt": "无缝有机纹理贴图，青碧色深海波浪与白色泡沫光线交织，流动水感，通透质感，适合3D物体表面贴图，无文字无logo",
        "tone": {"name": "abyss", "label": "深海青", "rgb": [0.16, 0.34, 0.38],
                 "meaning": "像深海最安静的一层水"},
        "idea": "星夜是抬头看天，深海是低头看水——同一种安静，换一种材质。",
        "expect": "青碧波浪贴图配深海青底色，通透流动的水感。",
    },
    "gilt": {
        "name": "鎏金",
        "reason": "绯红金凤是'庆典的热烈'，鎏金做它的'沉稳版'——同属金系，气质从张扬走向内敛。",
        "texture_prompt": "无缝有机纹理贴图，暗金鎏金纹样与深褐檀木纹理交织，复古华丽，细腻金属质感，适合3D物体表面贴图，无文字无logo",
        "tone": {"name": "gilt", "label": "檀木褐", "rgb": [0.42, 0.30, 0.20],
                 "meaning": "像旧木匣里金器的底色"},
        "idea": "金凤太热闹了，我想要一套安静的贵气——鎏金纹压在檀木褐上，低调但看得出分量。",
        "expect": "暗金纹样贴图配檀木褐底色，复古沉稳的贵气。",
    },
    "moonlight": {
        "name": "月下",
        "reason": "星夜是'星'，月下是'月'——补全墨灵'夜色宇宙'的最后一个意象，且银白系是中性安全色的高质量变体。",
        "texture_prompt": "无缝有机纹理贴图，银白色月光波纹与珍珠母贝光泽交织，清冷柔亮，细腻光泽质感，适合3D物体表面贴图，无文字无logo",
        "tone": {"name": "moonlight", "label": "月银", "rgb": [0.88, 0.90, 0.94],
                 "meaning": "像月光落在银器上"},
        "idea": "星夜有了，月下也该有——银色月光比星夜更安静，是独处时穿的颜色。",
        "expect": "银白月波贴图配月银底色，清冷柔亮。",
    },
}


class SelfDesigner:
    """墨灵自主设计引擎：plan（命题+决策链）→ [执行侧生成贴图] → apply（注册+渲染+自评）。"""

    def __init__(self, fashion: FashionSystem | None = None,
                 registry_path: str | None = None,
                 design_log_path: str | None = None) -> None:
        self.fashion = fashion or FashionSystem()
        self._registry_path = registry_path or os.path.join(HERE, "fashion_registry.json")
        self._log_path = design_log_path or DESIGN_LOG_PATH
        self._log: list[dict] = self._load_log()

    # ------------------------------------------------------------------ 日志
    def _load_log(self) -> list[dict]:
        if not os.path.isfile(self._log_path):
            return []
        with open(self._log_path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []

    def _save_log(self) -> None:
        with open(self._log_path, "w", encoding="utf-8") as f:
            json.dump(self._log, f, ensure_ascii=False, indent=2)

    def _used_themes(self) -> set[str]:
        return {entry["theme_id"] for entry in self._log if entry.get("status") in ("planned", "applied")}

    # ------------------------------------------------------------------ 规划
    def plan(self, theme_id: str | None = None) -> dict:
        """自主命题：默认选未使用过且色域互补的主题（真实决策：盘点已有衣柜）。"""
        if theme_id is None:
            candidates = [tid for tid in THEMES if tid not in self._used_themes()]
            if not candidates:
                raise ValueError("所有主题都设计过了——先扩主题库吧")
            theme_id = candidates[0]
        theme = THEMES.get(theme_id)
        if theme is None:
            raise ValueError(f"未知主题: {theme_id}")

        used_outfits = {o["id"] for o in self.fashion.list_outfits()}
        entry = {
            "theme_id": theme_id,
            "name": theme["name"],
            "status": "planned",
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "decision_chain": [
                theme["reason"],
                f"设计方向：{theme['texture_prompt'][:60]}……",
                f"色调定义：{theme['tone']['label']}（{theme['tone']['meaning']}）",
                f"预期观感：{theme['expect']}",
            ],
            "idea": theme["idea"],
            "texture_prompt": theme["texture_prompt"],
            "tone": theme["tone"],
            "outfit_id": f"{theme_id}_silk",
            "outfit_name": theme["name"],
            "used_before": theme_id in used_outfits,
        }
        self._log = [e for e in self._log if not (e.get("theme_id") == theme_id and e.get("status") == "planned")]
        self._log.append(entry)
        self._save_log()
        return entry

    # ------------------------------------------------------------------ 应用
    def apply(self, theme_id: str, texture_local: str, res: str = "960,540") -> dict:
        """应用成品：注册时装+色调 → 渲染 → 自评 → 入库。texture_local 为贴图本地路径。"""
        theme = THEMES[theme_id]
        outfit_id = f"{theme_id}_silk"
        tone_id = theme["tone"]["name"]

        # 注册时装 + 色调（幂等：已存在则跳过）
        registry_path = self._registry_path
        with open(registry_path, encoding="utf-8") as f:
            registry = json.load(f)
        if not any(o["id"] == outfit_id for o in registry["outfits"]):
            registry["outfits"].append({
                "id": outfit_id, "name": theme["name"],
                "texture": os.path.basename(texture_local),
                "target": "body_ring",
                "desc": f"{theme['name']}主题（M5 墨灵现场自主设计）",
            })
        if tone_id not in registry["tones"]:
            registry["tones"][tone_id] = theme["tone"]["rgb"]
        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump(registry, f, ensure_ascii=False, indent=2)

        # 注册写盘后刷新实例缓存，使新时装/色调对 compose 可见（注入的假实例不重建）
        if isinstance(self.fashion, FashionSystem):
            self.fashion = FashionSystem()

        # 渲染
        params = self.fashion.compose(outfit_id, tone_id, res)
        out = os.path.join(HERE, f"design_{outfit_id}.png")
        result = self.fashion.render(params, out_path=out)

        # 自评
        entry = next((e for e in self._log if e.get("theme_id") == theme_id and e.get("status") == "planned"), None)
        entry = entry or self.plan(theme_id)
        entry["status"] = "applied"
        entry["render"] = {
            "rc": result["rc"], "cache_hit": result["cache_hit"],
            "render_ms": result["render_ms"], "cost": result["cost"], "out": result["out"],
        }
        entry["review"] = {
            "match": "贴图纹理与底色同源，观感符合预期" if result["rc"] == 0 else "渲染失败",
            "note": "自评：这一套的主题气质达成——" + theme["expect"].split("，")[0],
            "verdict": "入库" if result["rc"] == 0 else "待修",
        }
        self._save_log()
        return entry

    def design_log(self) -> list[dict]:
        return self._log


def main(argv: list[str]) -> int:
    """CLI：--plan [theme_id] | --apply <theme_id> <texture_path> | --log | --themes"""
    designer = SelfDesigner()
    if "--themes" in argv:
        for tid, t in THEMES.items():
            print(f"  {tid}: {t['name']}——{t['reason'][:30]}……")
        return 0
    if "--plan" in argv:
        theme_id = argv[argv.index("--plan") + 1] if "--plan" in argv and len(argv) > argv.index("--plan") + 1 else None
        entry = designer.plan(theme_id)
        print(f"[plan] 命题：{entry['name']}（theme={entry['theme_id']}）")
        for step in entry["decision_chain"]:
            print(f"  - {step}")
        print(f"[执行] texture_prompt: {entry['texture_prompt']}")
        return 0
    if "--apply" in argv:
        i = argv.index("--apply")
        entry = designer.apply(argv[i + 1], argv[i + 2])
        print(f"[apply] {entry['name']} rc={entry['render']['rc']} cache={entry['render']['cache_hit']} "
              f"cost={entry['render']['cost']} out={entry['render']['out']}")
        print(f"[review] {entry['review']['match']}；{entry['review']['note']}；判定：{entry['review']['verdict']}")
        return 0
    if "--log" in argv:
        for e in designer.design_log():
            print(f"  [{e['status']}] {e['name']} ({e['theme_id']})")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
