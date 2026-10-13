// Live2D 运行时打包入口：把 pixi.js + pixi-live2d-display(cubism4) 打成浏览器 iife 单文件。
// 注意：必须使用 cubism4 子入口（模型为 .moc3 / Cubism 4）；默认入口是 Cubism 2。
// CSP 环境（无 unsafe-eval）：必须 install @pixi/unsafe-eval，否则 PixiJS 6 抛错。
// 打包命令（esbuild）：
//   esbuild live2d-entry.js --bundle --format=iife --global-name=MOLING_LIVE2D
//     --outfile=vendor/live2d-runtime.js
import { install } from "@pixi/unsafe-eval";
import * as PIXI from "pixi.js";
// CSP 环境（无 unsafe-eval）：install 必须在创建 Renderer 前应用补丁。
install(PIXI);
import { Live2DModel } from "pixi-live2d-display/cubism4";

export { PIXI, Live2DModel };
