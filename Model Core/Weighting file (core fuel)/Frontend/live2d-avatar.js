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

    app = new PIXI.Application({
      backgroundAlpha: 0,
      antialias: true,
      autoStart: true,
      resizeTo: container,
      resolution: window.devicePixelRatio || 1,
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

    // 显式对齐画布与容器尺寸（resizeTo 在 display:none 容器上会得到 0，调用方应确保已显示）
    const cw = container.clientWidth || container.getBoundingClientRect().width || 300;
    const ch = container.clientHeight || container.getBoundingClientRect().height || 400;
    if (cw > 0 && ch > 0) {
      app.renderer.resize(Math.floor(cw), Math.floor(ch));
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
    dispose,
    getExpressionDefinitions,
    _debugExpressionState,
    _debugMouth,
    get MOOD_EXPRESSION_MAP() {
      return MOOD_EXPRESSION_MAP;
    },
    get loaded() {
      return Boolean(model);
    },
  };
})();
