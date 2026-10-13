// Live2D 渲染模块（K3）：基于 pixi.js + pixi-live2d-display 加载本地 Live2D 模型。
// 依赖（按顺序引入）：
//   vendor/live2dcubismcore.min.js  -> window.Live2DCubismCore
//   vendor/live2d-runtime.js        -> window.MOLING_LIVE2D = { PIXI, Live2DModel }
// 模型通过主进程自定义协议 moling-model:// 加载（仅 Character 目录内文件）。
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
    const cw = container.clientWidth || 300;
    const ch = container.clientHeight || 400;
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

    fitModel(container);

    // 待机动画（模型自带）
    try {
      const motions = model.internalModel.motionManager.definitions;
      const idle = motions.findIndex((group) => String(group).toLowerCase().includes("idle"));
      if (idle >= 0) {
        await model.internalModel.motionManager.startMotion(idle, 0);
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
    currentExpressionIndex = typeof nameOrIndex === "number" ? nameOrIndex : -1;
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
    if (!model) return false;
    const em = model.internalModel.expressionManager;
    if (!em) return false;
    currentExpressionIndex = -1;
    em.resetExpression();
    return true;
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

  window.MolingLive2D = {
    init,
    setExpression,
    setMotion,
    setMouth,
    startTalking,
    stopTalking,
    setParam,
    resetExpression,
    dispose,
    getExpressionDefinitions,
    _debugExpressionState,
    get loaded() {
      return Boolean(model);
    },
  };
})();
