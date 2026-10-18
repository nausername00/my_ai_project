// Live2D 渲染模块（K3/K4）：基于 pixi.js + pixi-live2d-display 加载本地 Live2D 模型。
// 依赖（按顺序引入）：
//   vendor/live2dcubismcore.min.js  -> window.Live2DCubismCore
//   vendor/live2d-runtime.js        -> window.MOLING_LIVE2D = { PIXI, Live2DModel }
// 模型通过主进程自定义协议 moling:// 加载（仅 Character 目录内文件）。
"use strict";

(function () {
  const MODEL_URL = "moling://local/model/狐仙花嫁/狐仙花嫁/狐仙花嫁.model3.json";

  let app = null;
  let model = null;
  let blinkTimer = null;
  let blinkBusy = false;
  let mouthTimer = null;
  let currentExpressionIndex = -1;

  function randomBetween(min, max) {
    return min + Math.random() * (max - min);
  }

  // 把模型子资源（motions/expressions）的相对 File 路径改为基于 model3.json 的绝对 URL。
  function patchModelSubResourceURLs(modelUrl) {
    if (!model) return;
    const settings = model.internalModel && model.internalModel.settings;
    if (!settings) return;
    const base = new URL(modelUrl);
    const absolute = (rel) => new URL(rel, base).toString();
    if (settings.motions) {
      for (const group of Object.values(settings.motions)) {
        if (!Array.isArray(group)) continue;
        for (const m of group) {
          if (m && typeof m.File === "string") m.File = absolute(m.File);
        }
      }
    }
    if (settings.expressions) {
      for (const e of settings.expressions) {
        if (e && typeof e.File === "string") e.File = absolute(e.File);
      }
    }
  }

  // 模型适配容器：等比缩放 + 居中（锚点 0.5,0.5 保证中心对齐）
  function fitModel(container) {
    if (!model || !container) return;
    const cw = container.clientWidth || container.getBoundingClientRect().width || 300;
    const ch = container.clientHeight || container.getBoundingClientRect().height || 400;
    let bw = model.width || cw;
    let bh = model.height || ch;
    if (bw <= 0 || bh <= 0) {
      bw = cw;
      bh = ch;
    }
    const scale = Math.min(cw / bw, ch / bh) * 0.96;
    model.scale.set(scale);
    model.anchor.set(0.5, 0.5);
    model.x = cw / 2;
    model.y = ch / 2;
  }

  // 自动眨眼：随机间隔把两眼闭上 90-160ms 再睁开（不打断说话等表情）
  function startBlink() {
    stopBlink();
    const loop = async () => {
      if (!model) return;
      const delay = randomBetween(1800, 4200);
      blinkTimer = setTimeout(async () => {
        if (!model || blinkBusy) {
          blinkTimer = setTimeout(loop, 300);
          return;
        }
        blinkBusy = true;
        try {
          const core = model.internalModel.coreModel;
          core.setParameterValueById("ParamEyeLOpen", 0);
          core.setParameterValueById("ParamEyeROpen", 0);
          await new Promise((resolve) => setTimeout(resolve, randomBetween(90, 160)));
          core.setParameterValueById("ParamEyeLOpen", 1);
          core.setParameterValueById("ParamEyeROpen", 1);
        } catch {
          /* 参数不存在时静默 */
        }
        blinkBusy = false;
        blinkTimer = setTimeout(loop, 300);
      }, delay);
    };
    loop();
  }

  function stopBlink() {
    if (blinkTimer) {
      clearTimeout(blinkTimer);
      blinkTimer = null;
    }
  }

  function stopMouth() {
    if (mouthTimer) {
      clearInterval(mouthTimer);
      mouthTimer = null;
    }
    if (model) {
      try {
        model.internalModel.coreModel.setParameterValueById("ParamMouthOpenY", 0);
      } catch {
        /* 参数不存在时静默 */
      }
    }
  }

  async function init(container, options = {}) {
    const { PIXI, Live2DModel } = window.MOLING_LIVE2D;
    if (!container) throw new Error("缺少 Live2D 渲染容器");
    if (app) dispose();

    // 必须注册 Ticker，Live2DModel 才能随 pixi 主循环自动更新（呼吸/眨眼/动画）。
    if (!window.__molingLive2DTickerRegistered) {
      Live2DModel.registerTicker(PIXI.Ticker);
      window.__molingLive2DTickerRegistered = true;
    }

    // 固定输出尺寸（K6 演出舞台）：禁用 DPR 缩放与容器跟随，保证输出尺寸可控。
    const fixed = options.fixedSize;
    app = new PIXI.Application({
      backgroundAlpha: 0,
      antialias: true,
      autoStart: true,
      resizeTo: fixed ? undefined : container,
      resolution: fixed ? 1 : window.devicePixelRatio || 1,
      // 保留绘制缓冲：让窗口截图/录屏能稳定捕获 WebGL 内容（含 capturePage）
      preserveDrawingBuffer: true,
    });
    container.appendChild(app.view);
    app.view.style.width = "100%";
    app.view.style.height = "100%";
    app.view.style.display = "block";

    const modelUrl = options.modelUrl || MODEL_URL;
    model = await Live2DModel.from(modelUrl, {
      autoInteract: false,
      autoUpdate: true,
    });
    app.stage.addChild(model);

    // 修正子资源相对路径：pixi-live2d-display 的 XHR 以页面 base 解析相对 URL，
    // 表情/动作文件须基于 model3.json 的 URL 解析为绝对地址（settings 与
    // motionManager/expressionManager 的 definitions 为同一引用，patch 一次即生效）。
    patchModelSubResourceURLs(modelUrl);

    if (fixed && fixed.width > 0 && fixed.height > 0) {
      app.renderer.resize(Math.floor(fixed.width), Math.floor(fixed.height));
    } else {
      // 显式对齐画布与容器尺寸（resizeTo 在 display:none 容器上会得到 0，调用方应确保已显示）
      const cw = container.clientWidth || container.getBoundingClientRect().width || 300;
      const ch = container.clientHeight || container.getBoundingClientRect().height || 400;
      if (cw > 0 && ch > 0) {
        app.renderer.resize(Math.floor(cw), Math.floor(ch));
      }
    }

    fitModel(container);

    // 待机动画（模型自带）：definitions 是 { 组名: [动作...] } 的对象
    try {
      const motions = model.internalModel.motionManager.definitions;
      if (motions && typeof motions === "object") {
        const idleKey = Object.keys(motions).find((k) =>
          String(k).toLowerCase().includes("idle")
        );
        if (idleKey) {
          await model.internalModel.motionManager.startMotion(idleKey, 0);
        }
      }
    } catch {
      /* 无待机动作时静默 */
    }
    startBlink();
    return true;
  }

  // 切换表情：支持索引或名称。ExpressionManager.setExpression 内部按
  // definitions（model3.json Expressions，字段 Name/File 大写）查找名称。
  // 注：pixi-live2d-display 0.4 的表情管理器挂在 motionManager.expressionManager 上。
  async function setExpression(nameOrIndex) {
    if (!model || !model.internalModel || !model.internalModel.motionManager) return false;
    const em = model.internalModel.motionManager.expressionManager;
    if (!em) return false;
    const defs = em.definitions || [];
    const resolvedIndex =
      typeof nameOrIndex === "number"
        ? nameOrIndex
        : defs.findIndex((d) => d && d.Name === nameOrIndex);
    // 幂等：当前已是目标表情时直接视为成功（避免重复切换被 manager 抑制而误报失败）
    if (
      resolvedIndex >= 0 &&
      em.expressions &&
      em.expressions.indexOf(em.currentExpression) === resolvedIndex
    ) {
      currentExpressionIndex = resolvedIndex;
      return true;
    }
    currentExpressionIndex = resolvedIndex;
    const ok = await em.setExpression(nameOrIndex);
    return ok === true;
  }

  // 播放动作：group = "Idle" | "Sleep" | 数字索引，index = 组内序号
  async function setMotion(groupOrIndex, index = 0) {
    if (!model) return false;
    try {
      await model.internalModel.motionManager.startMotion(groupOrIndex, index);
      return true;
    } catch {
      return false;
    }
  }

  // 口型：open01 ∈ [0,1]，0=闭嘴 1=张大；随时间抖动模拟说话（K5 将接真实音频音量）
  function setMouth(open01) {
    if (!model) return;
    try {
      model.internalModel.coreModel.setParameterValueById(
        "ParamMouthOpenY",
        Math.max(0, Math.min(1, open01))
      );
    } catch {
      /* 参数不存在时静默 */
    }
  }

  // 说话动画：按 80-140ms 间隔随机抖动嘴型（无音频时的近似口型）
  function startTalking() {
    stopMouth();
    mouthTimer = setInterval(() => {
      if (!model) return;
      const v = Math.random() > 0.35 ? randomBetween(0.15, 0.7) : 0;
      setMouth(v);
    }, randomBetween(80, 140));
  }

  function stopTalking() {
    stopMouth();
  }

  // 任意参数设置（参数名来自 cdi3 参数表）
  function setParam(id, value) {
    if (!model) return;
    try {
      model.internalModel.coreModel.setParameterValueById(id, value);
    } catch {
      /* 参数不存在时静默 */
    }
  }

  function resetExpression() {
    if (!model || !model.internalModel || !model.internalModel.motionManager) return false;
    const em = model.internalModel.motionManager.expressionManager;
    if (!em) return false;
    currentExpressionIndex = -1;
    em.resetExpression();
    return true;
  }

  // K4：情绪键 -> 模型表情名映射（可被外部覆盖调整；null = 回中性无表情）
  const MOOD_EXPRESSION_MAP = {
    calm: null, // 平静 -> 中性
    happy: "心心眼",
    curious: "心心眼",
    surprised: "星星眼",
    worried: "流泪",
    shy: "脸红",
    warm: "心心眼",
    caring: "星星眼",
  };

  // K4：按情绪键切换表情（情绪系统 mood key，见 renderer simulatedEmotions）
  async function setExpressionByMood(moodKey) {
    if (!model) return false;
    const name = MOOD_EXPRESSION_MAP[moodKey] || null;
    if (!name) {
      return resetExpression();
    }
    const ok = await setExpression(name);
    if (ok) return true;
    // 目标表情不可用时回退中性，避免停留在旧表情
    await resetExpression();
    return false;
  }

  function dispose() {
    stopBlink();
    stopMouth();
    if (model) {
      try {
        model.destroy();
      } catch {
        /* 忽略销毁异常 */
      }
      model = null;
    }
    if (app) {
      try {
        app.destroy(true);
      } catch {
        /* 忽略销毁异常 */
      }
      app = null;
    }
  }

  // 调试：返回已注册的表情定义（model3.json Expressions，字段 Name/File）
  function getExpressionDefinitions() {
    if (!model) return [];
    const settings = model.internalModel && model.internalModel.settings;
    return (settings && settings.expressions) || [];
  }

  // 调试：表情加载中间状态
  async function _debugExpressionState() {
    const out = { hasModel: Boolean(model) };
    if (!model || !model.internalModel) return out;
    const internal = model.internalModel;
    out.hasMotionManager = Boolean(internal.motionManager);
    if (!internal.motionManager) return out;
    out.hasEm = Boolean(internal.motionManager.expressionManager);
    out.settingsExprLen = internal.settings && internal.settings.expressions
      ? internal.settings.expressions.length
      : -1;
    const em = internal.motionManager.expressionManager;
    if (!em) return out;
    const defs = em.definitions || [];
    const idx = defs.findIndex((d) => d && d.Name === "星星眼");
    const target = defs[idx];
    out.starIndex = idx;
    out.starFile = target ? target.File : null;
    let fetchState = "n/a";
    if (target && target.File) {
      try {
        const r = await fetch(target.File);
        fetchState = r.status;
      } catch (e) {
        fetchState = "ERR:" + e.message;
      }
    }
    out.fetchState = fetchState;
    let loaded = "n/a";
    try {
      const res = await em.loadExpression(idx);
      loaded = res ? "loaded" : "undefined";
    } catch (e) {
      loaded = "ERR:" + e.message;
    }
    out.loadResult = loaded;
    out.expressionsLen = em.expressions ? em.expressions.length : -1;
    return out;
  }

  // 调试：读回嘴部参数当前值（K5 口型联动验证用）
  function _debugMouth() {
    if (!model || !model.internalModel || !model.internalModel.coreModel) return null;
    try {
      return model.internalModel.coreModel.getParameterValueById("ParamMouthOpenY");
    } catch {
      return null;
    }
  }

  // K6：演出布局——人物靠左/居中/靠右（默认居中）。side: "left"|"center"|"right"
  // 注意：model.width/height 是含 scale 的显示 bounds，缩放计算必须用局部原始 bounds。
  // opts.heightRatio/widthRatio：角色占容器比例，用于为待机动画留出摆动余量（防出格）。
  function setCharacterSide(side, container, opts = {}) {
    if (!model || !container) return;
    const cw = container.clientWidth || container.getBoundingClientRect().width || 300;
    const ch = container.clientHeight || container.getBoundingClientRect().height || 400;
    let bw = 0;
    let bh = 0;
    try {
      const lb = model.getLocalBounds();
      bw = lb.width;
      bh = lb.height;
    } catch {
      /* ignore */
    }
    if (!bw || bw <= 0 || !bh || bh <= 0) {
      bw = model.width || cw;
      bh = model.height || ch;
    }
    // 演出目标：角色高度约占画面 heightRatio（留出字幕/舞台空间与待机摆动余量），宽度不超 widthRatio
    const targetH = ch * (opts.heightRatio || 0.58);
    const targetW = cw * (opts.widthRatio || 0.45);
    const scale = Math.min(targetH / bh, targetW / bw);
    if (!Number.isFinite(scale) || scale <= 0) return;
    model.scale.set(scale);
    model.anchor.set(0.5, 0.5);
    const cx = side === "left" ? cw * 0.3 : side === "right" ? cw * 0.7 : cw * 0.5;
    model.x = cx;
    model.y = ch * 0.52;
  }

  // K6：演出背景色（透明 PNG 序列请传 null 移除背景）。color 为 "#rrggbb"
  // 用 renderer.background（clear 颜色）控制，比 Graphics 层可靠且真正写入 alpha。
  function setBackground(color) {
    if (!app) return;
    const old = app.stage.getChildByName("k6-bg");
    if (old) {
      old.destroy();
    }
    if (!color) {
      try {
        app.renderer.background.alpha = 0;
      } catch {
        /* PIXI 版本差异兜底 */
      }
      return;
    }
    const intColor = parseInt(String(color).replace("#", ""), 16);
    try {
      app.renderer.background.color = intColor;
      app.renderer.background.alpha = 1;
    } catch {
      /* ignore */
    }
    const PIXI = window.MOLING_LIVE2D.PIXI;
    const g = new PIXI.Graphics();
    g.name = "k6-bg";
    g.beginFill(intColor, 1)
      .drawRect(0, 0, app.renderer.width, app.renderer.height)
      .endFill();
    app.stage.addChildAt(g, 0);
  }

  // K6：演出字幕（PIXI.Text 画进 canvas，透明/视频序列都包含字幕层）
  let captionText = null;
  function setCaption(text) {
    if (!app) return;
    if (!captionText) {
      const PIXI = window.MOLING_LIVE2D.PIXI;
      captionText = new PIXI.Text("", {
        fontFamily: "Microsoft YaHei, sans-serif",
        fontSize: 30,
        fill: "#ffffff",
        stroke: "#000000",
        strokeThickness: 4,
        wordWrap: true,
        wordWrapWidth: app.renderer.width * 0.9,
        align: "center",
      });
      captionText.name = "k6-caption";
      app.stage.addChild(captionText);
    }
    captionText.text = text || "";
    captionText.anchor.set(0.5, 0);
    captionText.x = app.renderer.width / 2;
    captionText.y = Math.max(8, app.renderer.height - captionText.height - 24);
  }

  // K6：演出时间线渲染。timeline = { fps, tracks:[{t,dur,expression,mouth,param,speech,text}] }
  // 逐帧：切换轨道状态（表情/口型/参数）-> 渲染 -> 回调 onFrame(dataURL, fileName)。
  // 说明：隐藏窗口的 rAF 会被节流，帧循环用 setTimeout 对齐帧率。
  async function renderTimeline(timeline, onFrame) {
    if (!model) throw new Error("Live2D 模型未加载");
    const fps = Math.max(1, Math.min(30, timeline.fps || 10));
    const tracks = (timeline.tracks || []).slice().sort((a, b) => a.t - b.t);
    const totalDur =
      tracks.reduce((m, t) => Math.max(m, t.t + (t.dur || 0)), 0) || 1;
    const frameCount = Math.max(1, Math.ceil(totalDur * fps));
    const frameMs = 1000 / fps;
    const findTrack = (t) =>
      tracks.find((tr) => t >= tr.t && t < tr.t + (tr.dur || 0));
    const applyTrack = async (tr) => {
      if (tr.expression) {
        await setExpression(tr.expression);
      } else {
        await resetExpression();
      }
      if (typeof tr.mouth === "number") setMouth(tr.mouth);
      if (tr.param) {
        for (const [k, v] of Object.entries(tr.param)) setParam(k, v);
      }
      setCaption(tr.text || "");
    };
    let active = null;
    // 首帧预热：Live2D 纹理/首帧渲染是异步的，先手动渲染 3 帧确保输出非空
    for (let w = 0; w < 3; w++) {
      app.renderer.render(app.stage);
      await new Promise((r) => setTimeout(r, 50));
    }
    for (let i = 0; i < frameCount; i++) {
      const t = i / fps;
      const tr = findTrack(t);
      if (tr !== active) {
        active = tr;
        if (tr) {
          await applyTrack(tr);
        } else {
          await resetExpression();
          setMouth(0);
        }
      }
      // 说话段口型微动（模拟语音起伏；真实音频音量驱动见 K5，视频版以波形占位）
      if (active && active.speech) {
        setMouth(0.3 + 0.35 * Math.abs(Math.sin(t * Math.PI * 3)));
      }
      let dataURL;
      try {
        dataURL = app.view.toDataURL("image/png");
      } catch (e) {
        dataURL = "";
      }
      if (onFrame && dataURL) {
        await onFrame(dataURL, `frame_${String(i).padStart(5, "0")}.png`);
      }
      if (i < frameCount - 1) {
        await new Promise((r) => setTimeout(r, frameMs));
      }
    }
    await resetExpression();
    setMouth(0);
    return { frameCount, totalDur, fps };
  }

  // 调试：读回模型与渲染器引用（K6 诊断用）
  function _debugModel() {
    return model;
  }
  function _debugApp() {
    return app;
  }

  window.MolingLive2D = {
    init,
    setExpression,
    setExpressionByMood,
    setMotion,
    setMouth,
    startTalking,
    stopTalking,
    setParam,
    resetExpression,
    setCharacterSide,
    setBackground,
    setCaption,
    renderTimeline,
    dispose,
    getExpressionDefinitions,
    _debugExpressionState,
    _debugMouth,
    _debugModel,
    _debugApp,
    get MOOD_EXPRESSION_MAP() {
      return MOOD_EXPRESSION_MAP;
    },
    get loaded() {
      return Boolean(model);
    },
  };
})();
