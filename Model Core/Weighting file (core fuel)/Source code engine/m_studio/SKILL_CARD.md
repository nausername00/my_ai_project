# 技能卡：Blender 程序化建模渲染（m_studio 三路结合管线）

> 来源里程碑：M0–M2（2026-10-17）｜ 3D 深化 M9（2026-10-20）
> 注册 id：`blender_render`（avatar_evolution.py 预置）
> 定位：墨灵创作工作台（M 线）的基础创作管线——**分身出方案 → AI 造素材 → 程序化精确落地 → 快照回传复核**，全程过程可见。

## 适用场景

- 用户想"做个 3D 物件 / 摆件 / 时装部件"并看到过程（直播式创作）。
- 需要"改一处 → 立即重渲回图对比"的交互回路。
- 需要**动起来**的展示（旋转 / 漂浮动画 → GIF）。
- 时装 / 换装系统（远期）：换贴图 = 换"衣服"，换颜色 = 换"配色"，同一管线接驳。

## 管线流程（三路结合）

```
1. 分身评审出方案     m1_collaboration.py → m1_collaboration_result.json
   （Ollama qwen2.5:3b，架构/代码/界面/测试四角色 + 综合共识）
2. AI 端到端造素材     image_gen → 有机贴图（PNG/JPG，建议 1024-2048 方图）
3. 程序化建模+贴图     m2_bpy_render.py / m9_bpy_render.py（参数化）→ 渲染 PNG
4. 快照回传复核        Read 渲染图 → 内容核验（贴图位置/颜色/非黑屏）→ 交付 RichMediaCard
5. 按反馈改参重渲      用户说改 → 改 --target/--base-color/--blend/--texture → 重渲 → 回图对比
6. 动画成片            --animate N → PNG 序列 → m9_make_gif.py 合成 GIF（无 ffmpeg 依赖）
```

## 脚本入口与参数契约

| 脚本 | 用途 | 关键参数 |
|---|---|---|
| `m0_bpy_minimal.py` | 最小建模渲染（基线） | 无参数 |
| `m1_collaboration.py` | 四角色评审出方案 | 无参数（本地 qwen2.5:3b） |
| `m1_bpy_texture.py` / `m1b_bpy_texture.py` | 贴图应用迭代版 | 无参数（贴图路径内置） |
| `m2_bpy_render.py` | 参数化渲染器（主入口·静帧） | `--target`（pedestal/body/ring/body_ring）、`--base-color`、`--texture`、`--out`、`--res` |
| `m9_bpy_render.py` | **3D 深化渲染器**（新形体+混合材质+动画） | `--target`（+gem/star/full）、`--blend`（0..1 贴图/底色混合）、`--animate`（帧数>0=动画序列）、`--out-dir` |
| `m9_make_gif.py` | 序列帧 → GIF 合成（系统 py，PIL/imageio） | `<帧目录> <输出gif> [--fps N]` |

调用方式（Blender 参数须放在自身 `--` 之后）：

```text
& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python m2_bpy_render.py -- --target ring --base-color "0.22,0.28,0.42" --out m2_dark.png
& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python m9_bpy_render.py -- --target gem --blend 0.35 --out m9_gem.png
& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python m9_bpy_render.py -- --target full --animate 12 --res "640,360" --out-dir m9_frames
py -3 m9_make_gif.py m9_frames m9_anim.gif --fps 12
```

## 指令 → 参数 映射表（用户话术翻译）

| 用户说 | 参数变化 | 例 |
|---|---|---|
| "贴图换到圆环 / 换到台座 / 锥体也贴上" | `--target` | ring / pedestal / body_ring |
| "做个宝石 / 星形 / 全装配摆件" | `--target` | gem / star / full |
| "颜色改深 / 换成蓝灰 / 台座改色" | `--base-color` | "0.22,0.28,0.42" |
| "贴图和底色混一点 / 半贴图半颜色" | `--blend` | 0.35（0=纯贴图，1=纯底色） |
| "让它转起来 / 做个动画" | `--animate` + `--out-dir` + m9_make_gif.py | 12 帧 @ fps 12 |
| "换一件衣服 / 用这张新贴图" | `--texture` | 新贴图路径（时装接驳点） |
| "出图清晰一点" | `--res` | "1280,720" |

## 验证要点（每次出图必做）

1. 渲染退出码为 0；静帧日志含 `[M9] still ... rendered -> <out>`，动画含 `[M9] anim frames=N`。
2. **Read 渲染图**，确认：贴图确在目标部件（看纹理位置）、未贴图部件为预期底色、画面非黑屏非空白。
3. 动画必须**逐帧核验**：PIL 直方图确认每帧非黑 + 帧 MD5 数量 == 帧数（避免"相机被误旋转导致全黑"类事故）。
4. 迭代时**前后图对比**（基准 vs 新版），向用户说明"改了什么参数 → 效果如何"。
5. 关键素材（贴图/脚本）落 m_studio 并入库，不依赖临时 URL。

## 已知限制 / 遗留（诚实披露）

- 宝石高光（Roughness 0.12 / Metallic 0.4）在 EEVEE 下视觉偏灰，真实宝石感需 Cycles 或更高 res。
- 脚本无**错误处理封装**（Blender 报错直接抛出）；UV 为默认展开，复杂部件需手动 UV。
- 动画为**绕 Z 旋转 + 上下漂浮**的固定运镜；关键帧/自定义路径动画未做。
- 时装 / 换装系统为**远期**：本卡证明"换贴图=换装"接驳，完整时装管理（部件库/组合/保存）未做。

## 复用记录

- M1（2026-10-17）：三路结合首次跑通，评审意见改变成品方向（M1_LOG.md）。
- M2（2026-10-17）：参数化渲染器 + 两指令闭环（ring/dark 对比图）。
- 换装接驳演示（M3，2026-10-17）：绯红金时装贴图经同一 `--texture` 参数换上，证明时装=换贴图。
- M9（2026-10-20）：3D 创作深化——新形体 gem/star/full、混合材质 `--blend`、`--animate` 序列帧 + GIF 合成；真实渲染验证（gem 台座构图、full 12 帧动画 12 帧全唯一）；修复"相机名误入旋转组导致全黑"缺陷。

