/**
 * 墨灵 - 聊天视图组件（TypeScript 参考实现）
 *
 * 与 app.tsx 相同：当前运行时为 vanilla JS（renderer.js），本文件是
 * TypeScript 迁移参考，需引入构建链后才会参与打包。
 */

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  ts: number;
}

export interface ChatViewProps {
  messages: ChatMessage[];
  onSend: (text: string) => void;
  disabled?: boolean;
}

/** 简单时间戳格式化（本地时间） */
export function formatTime(ts: number): string {
  const date = new Date(ts);
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/**
 * 消息气泡渲染：user 右对齐、assistant 左对齐。
 * 参考实现——样式细节以 renderer.js 对应的 style.css 为准。
 */
export function ChatView(props: ChatViewProps) {
  const { messages, onSend, disabled } = props;
  return (
    <div className="moling-chat">
      <div className="moling-chat__list">
        {messages.map((message) => (
          <div key={message.ts} className={`moling-msg moling-msg--${message.role}`}>
            <div className="moling-msg__bubble">{message.content}</div>
            <div className="moling-msg__time">{formatTime(message.ts)}</div>
          </div>
        ))}
      </div>
      <form
        className="moling-chat__input"
        onSubmit={(event) => {
          event.preventDefault();
          const form = event.currentTarget;
          const input = form.elements.namedItem("text") as HTMLInputElement;
          const text = input.value.trim();
          if (text) {
            onSend(text);
            input.value = "";
          }
        }}
      >
        <input name="text" placeholder="输入消息…" disabled={disabled} />
        <button type="submit" disabled={disabled}>发送</button>
      </form>
    </div>
  );
}
