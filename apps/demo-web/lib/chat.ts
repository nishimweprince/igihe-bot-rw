export type Source = {
  n: number;
  wp_id: number;
  title: string;
  published_at: string;
  url: string;
};

export type Role = "user" | "assistant";

export type Message = {
  id: string;
  role: Role;
  content: string;
  sources: Source[];
  error?: boolean;
};

export type Conversation = {
  id: string;
  title: string;
  messages: Message[];
  createdAt: number;
};

export type ChatPhase = "idle" | "searching" | "streaming" | "done" | "error";

export type ThreadState = {
  conversations: Conversation[];
  activeId: string;
  phase: ChatPhase;
  status: string;
};

export type ParsedEvent = {
  event: string;
  data: unknown;
};

export const CHAT_PATH = "/v1/chat";

export const STATUS = {
  idle: "Baza ikibazo mu Kinyarwanda.",
  searching: "Ndashaka ibimenyetso...",
  streaming: "Ndasubiza...",
  done: "Igisubizo kirangiye.",
  http413: "Igisubizo: ubutumwa burarenze urugero. Bugufi.",
  http429: "Serivisi iruzuye, ongera ugerageze nyuma.",
  genericError: "Habaye ikosa. Ongera ugerageze.",
  networkError: "API ntibashije kuboneka. Menya ko serivisi iriho (port 8000).",
  streamErrorFallback: "Habaye ikosa.",
} as const;

export function newId(): string {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `t-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function chatRequestBody(sessionId: string, message: string): { session_id: string; message: string } {
  return { session_id: sessionId, message };
}

export function isBusy(phase: ChatPhase): boolean {
  return phase === "searching" || phase === "streaming";
}

export function canSend(phase: ChatPhase, text: string): boolean {
  return Boolean(text.trim()) && !isBusy(phase);
}

export function joinToken(existing: string, chunk: string): string {
  if (!chunk) return existing;
  if (!existing) return chunk;
  return `${existing} ${chunk}`;
}

export function titleFromMessage(text: string): string {
  const t = text.trim().replace(/\s+/g, " ");
  if (!t) return "New chat";
  return t.length > 40 ? `${t.slice(0, 37)}...` : t;
}

export function formatSourceDate(publishedAt: string): string {
  return publishedAt.slice(0, 10);
}

export function createConversation(id: string = newId()): Conversation {
  return { id, title: "New chat", messages: [], createdAt: Date.now() };
}

export function createThreadState(id: string = newId()): ThreadState {
  const conv = createConversation(id);
  return {
    conversations: [conv],
    activeId: conv.id,
    phase: "idle",
    status: STATUS.idle,
  };
}

export function getActive(state: ThreadState): Conversation {
  return state.conversations.find((c) => c.id === state.activeId) ?? state.conversations[0];
}

function mapConversation(
  state: ThreadState,
  conversationId: string,
  fn: (c: Conversation) => Conversation,
): ThreadState {
  return {
    ...state,
    conversations: state.conversations.map((c) => (c.id === conversationId ? fn(c) : c)),
  };
}

function lastAssistant(conv: Conversation): Message | undefined {
  const last = conv.messages[conv.messages.length - 1];
  return last?.role === "assistant" ? last : undefined;
}

export function beginTurn(state: ThreadState, userText: string): ThreadState {
  const text = userText.trim();
  if (!canSend(state.phase, text)) return state;
  const conv = getActive(state);
  const user: Message = { id: newId(), role: "user", content: text, sources: [] };
  const assistant: Message = { id: newId(), role: "assistant", content: "", sources: [] };
  const title = conv.messages.length === 0 ? titleFromMessage(text) : conv.title;
  return mapConversation(
    { ...state, phase: "searching", status: STATUS.searching },
    conv.id,
    (c) => ({ ...c, title, messages: [...c.messages, user, assistant] }),
  );
}

export function appendToken(
  state: ThreadState,
  chunk: string,
  conversationId: string = state.activeId,
): ThreadState {
  if (!chunk) return state;
  return mapConversation(state, conversationId, (c) => {
    const last = lastAssistant(c);
    if (!last) return c;
    const messages = c.messages.slice();
    messages[messages.length - 1] = { ...last, content: joinToken(last.content, chunk) };
    return { ...c, messages };
  });
}

export function attachSources(
  state: ThreadState,
  sources: Source[],
  conversationId: string = state.activeId,
): ThreadState {
  return mapConversation(state, conversationId, (c) => {
    const last = lastAssistant(c);
    if (!last) return c;
    const messages = c.messages.slice();
    messages[messages.length - 1] = { ...last, sources };
    return { ...c, messages };
  });
}

export function startNewChat(state: ThreadState, id: string = newId()): ThreadState {
  const active = getActive(state);
  if (active && active.messages.length === 0) {
    return { ...state, phase: "idle", status: STATUS.idle };
  }
  const conv = createConversation(id);
  return {
    conversations: [conv, ...state.conversations],
    activeId: conv.id,
    phase: "idle",
    status: STATUS.idle,
  };
}

export function selectConversation(state: ThreadState, id: string): ThreadState {
  if (!state.conversations.some((c) => c.id === id)) return state;
  return { ...state, activeId: id };
}

export function completeIfStreaming(state: ThreadState): ThreadState {
  if (state.phase === "streaming") {
    return { ...state, phase: "done", status: STATUS.done };
  }
  return state;
}

export function failAssistant(
  state: ThreadState,
  message: string,
  conversationId: string = state.activeId,
): ThreadState {
  const next = mapConversation(state, conversationId, (c) => {
    const last = lastAssistant(c);
    if (!last) return c;
    const messages = c.messages.slice();
    messages[messages.length - 1] = { ...last, content: message, error: true };
    return { ...c, messages };
  });
  return { ...next, phase: "error", status: message };
}

export function failHttp(
  state: ThreadState,
  statusCode: number,
  conversationId: string = state.activeId,
): ThreadState {
  if (statusCode === 413) return failAssistant(state, STATUS.http413, conversationId);
  if (statusCode === 429) return failAssistant(state, STATUS.http429, conversationId);
  return failAssistant(state, STATUS.genericError, conversationId);
}

export function failNetwork(state: ThreadState, conversationId: string = state.activeId): ThreadState {
  return failAssistant(state, STATUS.networkError, conversationId);
}

export function sourcesFromData(data: unknown): Source[] {
  if (!Array.isArray(data)) return [];
  const out: Source[] = [];
  for (const item of data) {
    if (!item || typeof item !== "object") continue;
    const rec = item as Record<string, unknown>;
    const title = String(rec.title ?? "");
    const url = String(rec.url ?? "");
    if (!title || !url) continue;
    out.push({
      n: Number(rec.n) || out.length + 1,
      wp_id: Number(rec.wp_id) || 0,
      title,
      published_at: String(rec.published_at ?? ""),
      url,
    });
  }
  return out;
}

export function parseSseBuffer(buffer: string): { events: ParsedEvent[]; remaining: string } {
  const events: ParsedEvent[] = [];
  const parts = buffer.split("\n\n");
  const remaining = parts.pop() ?? "";
  for (const part of parts) {
    if (!part.trim()) continue;
    const lines = part.split("\n");
    const event = lines.find((l) => l.startsWith("event: "))?.slice(7) ?? "";
    const dataRaw = lines.find((l) => l.startsWith("data: "))?.slice(6) ?? "{}";
    let data: unknown = {};
    try {
      data = JSON.parse(dataRaw);
    } catch {
      continue;
    }
    if (!event) continue;
    events.push({ event, data });
  }
  return { events, remaining };
}

export function applySseEvent(
  state: ThreadState,
  parsed: ParsedEvent,
  conversationId: string = state.activeId,
): ThreadState {
  const { event, data } = parsed;
  if (event === "retrieval") {
    return { ...state, phase: "searching", status: STATUS.searching };
  }
  if (event === "token") {
    const rec = data && typeof data === "object" ? (data as Record<string, unknown>) : {};
    const chunk = String(rec.text ?? "");
    const next = appendToken({ ...state, phase: "streaming", status: STATUS.streaming }, chunk, conversationId);
    return { ...next, phase: "streaming", status: STATUS.streaming };
  }
  if (event === "sources") {
    return attachSources(state, sourcesFromData(data), conversationId);
  }
  if (event === "done") {
    return { ...state, phase: "done", status: STATUS.done };
  }
  if (event === "error") {
    const rec = data && typeof data === "object" ? (data as Record<string, unknown>) : {};
    const message = String(rec.message ?? STATUS.streamErrorFallback);
    return failAssistant(state, message, conversationId);
  }
  return state;
}

export function listedConversations(state: ThreadState): Conversation[] {
  return state.conversations.filter((c) => c.messages.length > 0);
}
