# K6 演出输出：k6-demo-greeting

演示演出时间线（墨灵讲解开场），2026-10-13 由 K6 渲染管线产出。

## 三件套

| 目录/文件 | 内容 |
|---|---|
| `timeline.json` | **工程文件（可重开）**：演出脚本（尺寸/帧率/背景/轨道：表情+口型+字幕+时长） |
| `with-bg/video.mp4` | 普通视频（1280×720，10fps，H.264，深色背景） |
| `with-bg/frames/` | 带背景的 PNG 序列（110 帧，可二次剪辑） |
| `transparent/frames/` | **透明素材 PNG 序列**（110 帧，无背景，可直接合成到任意场景） |

## 演出内容（timeline.json 轨道）

| 时间 | 表情 | 字幕 |
|---|---|---|
| 0.0–2.5s | 心心眼 + 说话口型 | 大家好，我是墨灵！今天由我来当讲解员。 |
| 2.5–5.5s | 星星眼 + 说话口型 | 我们聊聊一个有趣的概念——Live2D 演出。 |
| 5.5–8.5s | 中性 + 说话口型（提问段） | 提问时间：想知道它是怎么动起来的吗？ |
| 8.5–11s | 脸红 + 说话口型 | 感谢大家的陪伴，我们下次再见～ |

演出规则已内建：人物靠右（`layout.characterSide=right`）、说话段口型起伏、轨道切换即时生效、结束回中性。

## 版权与素材说明

- **角色模型**：Steam Workshop「狐仙花嫁」（作者：菜菜爱吃 等）。**画面内嵌作者防盗水印为模型自带内容，未做移除**；本地个人使用无问题，对外分发/商用需作者授权。
- 渲染引擎：项目内自研（Electron + PixiJS 6 + pixi-live2d-display + 自研时间线渲染），无外部网络依赖。
- 视频编码：ffmpeg-static（本地二进制，libx264）。

## 复现命令

```powershell
cd Frontend
.\node_modules\.bin\electron.cmd k6-render.cjs `
  --timeline "…\k6-demo-greeting\timeline.json" `
  --out "…\k6-demo-greeting\with-bg" --bg "#111318" --side right
# 透明版：--bg transparent（输出纯透明 PNG 序列，不合成视频）
```
