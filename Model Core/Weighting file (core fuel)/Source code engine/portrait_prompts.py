"""K1 立绘生成经验库（供墨灵「试画」工具与生成脚本共用）。

来源：K1 阶段 11 轮真实生成迭代的经验沉淀（见 Docs & Compliance/K1_ARTIST_NOTES.md）。
墨灵调用 draw_portrait 时，默认使用这里的中性风格模板；用户/墨灵可在
style_prompt 里追加或覆盖局部描述。

注意：
- Counterfeit-V2.5 是 SD1.5 底模，4GB 显存下竖版 1024×1536 腿部/裙摆易崩，
  负面词里的腿部防护不可删。
- 服装描述必须具体（军装/外套+裙），抽象词（"优雅服装"）容易漂成白袍/纱裙。
- 背景装饰（披风/飘带/烟雾）会干扰 rembg 透明化，生成时默认禁掉。
"""

from __future__ import annotations

# 墨灵基准立绘（2026-10-12 定稿）：红眸 / 白猫耳 / 银白长发 / 黑白主色带蓝红点缀
PORTRAIT_BASELINE = {
    "eyes": "bright red eyes",
    "ears": "white cat ears",
    "hair": "silver white long flowing hair",
    "outfit": "black and white elegant outfit, white shirt with black high collar jacket, "
    "(blue accents) and (red accents) trims, gold insignia, black skirt with red and blue trim, "
    "black stockings, black boots",
    "expression": "calm mysterious gentle expression",
    "pose": "standing on two legs, normal legs, facing viewer directly, "
    "both arms relaxed at sides, symmetrical frontal pose",
}

# 默认正向模板：竖版立绘、单人正面、纯白背景、无背景装饰
POSITIVE_TEMPLATE = (
    "masterpiece, best quality, anime illustration, "
    "elegant gothic dark fantasy style, "
    "1girl, solo, single character, "
    "%EARS%, %HAIR%, %EYES%, %EXPRESSION%, "
    "%OUTFIT%, %POSE%, "
    "plain pure white background, clean lineart, detailed"
)

# 默认负向模板：腿部/身体防护 + 历史踩坑元素（务必保留）
NEGATIVE_TEMPLATE = (
    "lowres, bad anatomy, bad hands, extra fingers, watermark, text, signature, "
    "blurry, jpeg artifacts, deformed, "
    "bad legs, deformed legs, extra legs, three legs, triple legs, fused legs, "
    "malformed feet, skirt overlap, clipping, "
    "maid outfit, apron, lace dress, frilly skirt, "
    "gun, weapon, firearm, rifle, sword, "
    "mermaid, fish tail, tail, animal tail, "
    "purple cape, green dress, green coat, "
    "garbage bag, plastic bag, trash bag, holding bag, "
    "flower petals, petals, mist, fog, smoke, "
    "twin tails, twin-tail hair, double ponytail, pigtails, "
    "two girls, multiple people, second person, duo, "
    "cape, hood, scarf, ribbon trail"
)

# 推荐 seed：K1 验证过腿部/裙摆较稳的区间；每次生成请更换
RECOMMENDED_SEEDS = [
    20261031,
    20261012 + 19,
    20261012 + 23,
    20261012 + 29,
    20261012 + 41,
    20261012 + 47,
    20261012 + 53,
]

# 画布与采样（RTX 3050 Ti 4GB 可承受）
DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 1536
DEFAULT_STEPS = 20
DEFAULT_CFG = 7.0


def build_positive(
    *,
    style_prompt: str | None = None,
    override: dict[str, str] | None = None,
) -> str:
    """按基准特征组装正向提示词；override 可覆盖单个特征（如 eyes）。

    style_prompt 追加在画布与背景描述之前，用于墨灵补充风格方向。
    """
    fields = dict(PORTRAIT_BASELINE)
    if override:
        fields.update(override)
    positive = (
        POSITIVE_TEMPLATE.replace("%EARS%", fields["ears"])
        .replace("%HAIR%", fields["hair"])
        .replace("%EYES%", fields["eyes"])
        .replace("%EXPRESSION%", fields["expression"])
        .replace("%OUTFIT%", fields["outfit"])
        .replace("%POSE%", fields["pose"])
    )
    if style_prompt and style_prompt.strip():
        # 追加在 "1girl..." 之后、画布背景之前
        positive = positive.replace(
            "plain pure white background",
            f"{style_prompt.strip()}, plain pure white background",
            1,
        )
    return positive
