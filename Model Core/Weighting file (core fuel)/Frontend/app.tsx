/**
 * 墨灵 - 应用入口组件（TypeScript 参考实现）
 *
 * 注意：当前桌面端的运行时实现是 vanilla JS（renderer.js + index.html +
 * style.css），本项目尚未引入 TypeScript 构建链（tsc / Vite / webpack）。
 * 本文件是 TypeScript + React 重构的参考实现，供后续迁移使用；
 * 在引入构建链（tsconfig.json + 打包器）之前不会被加载。
 */

export interface CharacterCard {
  nickname: string;
  gender?: string;
  selfReference?: string;
  coreValues?: string[];
  avatar?: string | null;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  ts: number;
}

export interface AppProps {
  /** 通过 preload 暴露的本地 API 基地址，例如 http://127.0.0.1:8000 */
  apiBase: string;
  /** 初始角色卡（可由 preload 注入） */
  card?: CharacterCard | null;
}

/**
 * 生成一条请求体：与后端 POST /v1/generate 契约保持一致。
 */
export function buildGeneratePayload(prompt: string, maxTokens = 128) {
  return { prompt, max_tokens: maxTokens };
}

/**
 * 本地 API 生成调用（fetch 封装，返回后端 JSON）。
 */
export async function generateText(apiBase: string, prompt: string, maxTokens = 128) {
  const response = await fetch(`${apiBase.replace(/\/+$/, "")}/v1/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildGeneratePayload(prompt, maxTokens)),
  });
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${await response.text()}`);
  }
  return response.json();
}

/**
 * 应用根组件：维护消息列表并调用本地生成 API。
 * 这是精简的参考实现——完整桌面 UI 仍以 renderer.js 为准。
 */
export function MolingApp(_props: AppProps) {
  // 参考实现（未挂载到真实 DOM）：迁移时在此渲染 <ChatView/>。
  return null;
}
