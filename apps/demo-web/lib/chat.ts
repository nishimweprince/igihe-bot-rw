import { decodeEntities } from "./format.ts";

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
  /** Sendable follow-up prompts attached by the server (e.g. after a refusal). */
  suggestions?: string[];
  error?: boolean;
  /** Placeholder text (e.g. a cancelled reply) rendered in a quiet style. */
  muted?: boolean;
};

export type Conversation = {
  id: string;
  title: string;
  messages: Message[];
  createdAt: number;
  /** Estimated token counts for this chat (client-side heuristic, see countTokens). */
  inputTokens?: number;
  outputTokens?: number;
  /** Model id last reported by the SSE `done` event for this chat. */
  model?: string;
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

/** Comparison link for billed OpenAI usage; local inference is not billed at these rates. */
export const PRICING_URL = "https://openai.com/api/pricing/";

/** Fallback model label when no SSE `done` event has reported one yet. */
export const FALLBACK_MODEL = "fake-gen-v1";

/**
 * Rough client-side token estimate: ~4 characters per token.
 * Labeled as an estimate in the UI; never exact billing.
 */
export function countTokens(text: string): number {
  const t = text.trim();
  if (!t) return 0;
  return Math.max(1, Math.ceil(t.length / 4));
}

export type ConversationUsage = {
  inputTokens: number;
  outputTokens: number;
  total: number;
  model?: string;
};

/** Normalized usage for one conversation; legacy blobs without fields read as zero. */
export function conversationUsage(conv: Conversation): ConversationUsage {
  const inputTokens = conv.inputTokens ?? 0;
  const outputTokens = conv.outputTokens ?? 0;
  return { inputTokens, outputTokens, total: inputTokens + outputTokens, model: conv.model };
}

/** Summed usage across every stored conversation. */
export function totalUsage(state: ThreadState): Omit<ConversationUsage, "model"> & { total: number } {
  let inputTokens = 0;
  let outputTokens = 0;
  for (const c of state.conversations) {
    inputTokens += c.inputTokens ?? 0;
    outputTokens += c.outputTokens ?? 0;
  }
  return { inputTokens, outputTokens, total: inputTokens + outputTokens };
}

export const STATUS = {
  idle: "Baza ikibazo mu Kinyarwanda.",
  searching: "Ndimo gushakisha mu nkuru za IGIHE",
  streaming: "Ndimo gusubiza",
  done: "Igisubizo cyarangiye.",
  cancelled: "Igisubizo cyahagaritswe.",
  http413: "Ubutumwa bwawe ni burebure cyane. Bugire bugufi hanyuma wongere ugerageze.",
  http429: "Serivisi irahuze ubu. Ongera ugerageze mu kanya gato.",
  genericError: "Habaye ikibazo. Ongera ugerageze.",
  networkError: "Ntibyakunze guhuza na serivisi. Reba niba API iri gukora (port 8000).",
  streamErrorFallback: "Habaye ikibazo.",
} as const;

export const NEW_CHAT_TITLE = "Ikiganiro gishya";

/** Pool of sample questions; a random few are shown on the empty thread. */
export const SUGGESTION_POOL = [
  "Perezida Kagame yavuze iki vuba?",
  "Habaye iki mu mupira w'amaguru iki cyumweru?",
  "Ni izihe nkuru ziheruka ku bukungu bw'u Rwanda?",
  "Ni izihe nkuru ku buhinzi bw'ikawa mu Rwanda?",
  "APR FC yagenze ite mu mukino uheruka?",
  "Tour du Rwanda igeze he?",
  "Ikirere kizaba kimeze kite i Kigali?",
  "Ni izihe nkuru zigezweho mu Rwanda?",
] as const;

export const SUGGESTION_COUNT = 3;

/** Fisher–Yates pick of `count` distinct suggestions. `rand` is injectable for tests. */
export function pickSuggestions(
  count: number = SUGGESTION_COUNT,
  rand: () => number = Math.random,
): string[] {
  const pool = [...SUGGESTION_POOL];
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [pool[i], pool[j]] = [pool[j], pool[i]];
  }
  return pool.slice(0, Math.max(0, Math.min(count, pool.length)));
}

export function newId(): string {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `t-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export type HistoryTurn = { role: Role; content: string };

export type ChatFilters = { published_after?: string };

export type ChatRequestBody = {
  session_id: string;
  message: string;
  history?: HistoryTurn[];
  filters?: ChatFilters;
};

/** Last `turns` completed messages of a conversation, as the server expects them. */
export function historyFor(conv: Conversation | undefined, turns: number = HISTORY_TURNS): HistoryTurn[] {
  if (!conv) return [];
  const usable = conv.messages.filter((m) => m.content.trim() && !m.error && !m.muted);
  return usable.slice(-turns).map((m) => ({ role: m.role, content: m.content }));
}

export function chatRequestBody(
  sessionId: string,
  message: string,
  history: HistoryTurn[] = [],
  filters?: ChatFilters,
): ChatRequestBody {
  const body: ChatRequestBody = { session_id: sessionId, message };
  if (history.length) body.history = history;
  if (filters && Object.keys(filters).length) body.filters = filters;
  return body;
}

/** How many prior messages travel with each question (server keeps the last HISTORY_TURNS). */
export const HISTORY_TURNS = 6;

export type TimeRange = "all" | "7d" | "30d" | "year";

export const TIME_RANGES: { value: TimeRange; label: string }[] = [
  { value: "all", label: "Igihe cyose" },
  { value: "7d", label: "Iminsi 7" },
  { value: "30d", label: "Iminsi 30" },
  { value: "year", label: "Uyu mwaka" },
];

/** ISO `published_after` for a range, or undefined for "all". */
export function publishedAfterFor(range: TimeRange, now: number = Date.now()): string | undefined {
  if (range === "all") return undefined;
  const d = new Date(now);
  if (range === "7d") d.setDate(d.getDate() - 7);
  else if (range === "30d") d.setDate(d.getDate() - 30);
  else {
    d.setMonth(0, 1);
    d.setHours(0, 0, 0, 0);
  }
  // Local wall-clock ISO (article dates are WordPress local time, not UTC).
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export function filtersFor(range: TimeRange, now: number = Date.now()): ChatFilters | undefined {
  const after = publishedAfterFor(range, now);
  return after ? { published_after: after } : undefined;
}

export function isBusy(phase: ChatPhase): boolean {
  return phase === "searching" || phase === "streaming";
}

export function canSend(phase: ChatPhase, text: string): boolean {
  return Boolean(text.trim()) && !isBusy(phase);
}

/** Streamed pieces carry their own whitespace (real tokens), so join is plain concat. */
export function joinToken(existing: string, chunk: string): string {
  if (!chunk) return existing;
  return existing + chunk;
}

export function titleFromMessage(text: string): string {
  const t = text.trim().replace(/\s+/g, " ");
  if (!t) return NEW_CHAT_TITLE;
  return t.length > 40 ? `${t.slice(0, 37)}...` : t;
}

export function formatSourceDate(publishedAt: string): string {
  return publishedAt.slice(0, 10);
}

export function createConversation(id: string = newId()): Conversation {
  return { id, title: NEW_CHAT_TITLE, messages: [], createdAt: Date.now(), inputTokens: 0, outputTokens: 0 };
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
    (c) => ({
      ...c,
      title,
      messages: [...c.messages, user, assistant],
      inputTokens: (c.inputTokens ?? 0) + countTokens(text),
    }),
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
    return { ...c, messages, outputTokens: (c.outputTokens ?? 0) + countTokens(chunk) };
  });
}

/** Server-side validation rejected the streamed text: swap it for the replacement. */
export function replaceAnswer(
  state: ThreadState,
  text: string,
  conversationId: string = state.activeId,
): ThreadState {
  return mapConversation(state, conversationId, (c) => {
    const last = lastAssistant(c);
    if (!last) return c;
    const messages = c.messages.slice();
    const previous = countTokens(last.content);
    messages[messages.length - 1] = { ...last, content: text, muted: false };
    return { ...c, messages, outputTokens: Math.max(0, (c.outputTokens ?? 0) - previous) + countTokens(text) };
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

export function attachSuggestions(
  state: ThreadState,
  suggestions: string[],
  conversationId: string = state.activeId,
): ThreadState {
  return mapConversation(state, conversationId, (c) => {
    const last = lastAssistant(c);
    if (!last) return c;
    const messages = c.messages.slice();
    messages[messages.length - 1] = { ...last, suggestions };
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

/** Stop a turn early. Keeps whatever streamed so far; an empty reply reads as cancelled. */
export function cancelTurn(state: ThreadState, conversationId: string = state.activeId): ThreadState {
  if (!isBusy(state.phase)) return state;
  const next = mapConversation(state, conversationId, (c) => {
    const last = lastAssistant(c);
    if (!last || last.content) return c;
    const messages = c.messages.slice();
    messages[messages.length - 1] = { ...last, content: STATUS.cancelled, muted: true };
    return { ...c, messages };
  });
  return { ...next, phase: "done", status: STATUS.done };
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
    const title = decodeEntities(String(rec.title ?? "")).trim();
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

export function suggestionsFromData(data: unknown): string[] {
  const rec = (data && typeof data === "object" ? data : {}) as Record<string, unknown>;
  const raw = Array.isArray(rec.suggestions) ? rec.suggestions : [];
  const out: string[] = [];
  for (const item of raw) {
    if (typeof item !== "string") continue;
    const q = decodeEntities(item).trim();
    if (q && !out.includes(q)) out.push(q);
    if (out.length >= 3) break;
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
  if (event === "replace") {
    const rec = data && typeof data === "object" ? (data as Record<string, unknown>) : {};
    const text = String(rec.text ?? "");
    return text ? replaceAnswer(state, text, conversationId) : state;
  }
  if (event === "sources") {
    return attachSources(state, sourcesFromData(data), conversationId);
  }
  if (event === "suggestions") {
    return attachSuggestions(state, suggestionsFromData(data), conversationId);
  }
  if (event === "done") {
    const rec = data && typeof data === "object" ? (data as Record<string, unknown>) : {};
    const model = typeof rec.model === "string" && rec.model ? rec.model : undefined;
    if (!model) return { ...state, phase: "done", status: STATUS.done };
    return mapConversation({ ...state, phase: "done", status: STATUS.done }, conversationId, (c) => ({
      ...c,
      model,
    }));
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

export type ConversationGroup = { label: string; items: Conversation[] };

const DAY_MS = 24 * 60 * 60 * 1000;

function startOfDay(ts: number): number {
  const d = new Date(ts);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

/** Bucket conversations the way ChatGPT's sidebar does: today, yesterday, last 7 days, older. */
export function groupConversations(conversations: Conversation[], now: number = Date.now()): ConversationGroup[] {
  const today = startOfDay(now);
  const buckets: ConversationGroup[] = [
    { label: "Uyu munsi", items: [] },
    { label: "Ejo hashize", items: [] },
    { label: "Iminsi 7 ishize", items: [] },
    { label: "Mbere y'aho", items: [] },
  ];
  for (const c of conversations) {
    const day = startOfDay(c.createdAt);
    const idx = day >= today ? 0 : day >= today - DAY_MS ? 1 : day >= today - 7 * DAY_MS ? 2 : 3;
    buckets[idx].items.push(c);
  }
  return buckets.filter((b) => b.items.length > 0);
}

/* ---------- Persistence (this device only) ---------- */

export const STORAGE_KEY = "igihe-demo-threads-v1";
export const SHARE_HASH_PREFIX = "#s=";

export type StorageLike = {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
};

function defaultStorage(): StorageLike | null {
  try {
    if (typeof globalThis.localStorage !== "undefined") return globalThis.localStorage;
  } catch {
    /* storage blocked: demo keeps running memory-only */
  }
  return null;
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

function isConversation(v: unknown): v is Conversation {
  return (
    isRecord(v) &&
    typeof v.id === "string" &&
    typeof v.title === "string" &&
    Array.isArray(v.messages) &&
    typeof v.createdAt === "number"
  );
}

export function saveThreads(
  state: ThreadState,
  storage: StorageLike | null = defaultStorage(),
): void {
  if (!storage) return;
  try {
    storage.setItem(
      STORAGE_KEY,
      JSON.stringify({ v: 1, activeId: state.activeId, conversations: state.conversations }),
    );
  } catch {
    /* quota/private mode: demo keeps running memory-only */
  }
}

export function loadThreads(
  storage: StorageLike | null = defaultStorage(),
): ThreadState | null {
  if (!storage) return null;
  try {
    const raw = storage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const data: unknown = JSON.parse(raw);
    if (!isRecord(data) || !Array.isArray(data.conversations)) return null;
    const conversations = (data.conversations as unknown[]).filter(isConversation);
    if (conversations.length === 0) return null;
    const activeId =
      typeof data.activeId === "string" &&
      conversations.some((c) => c.id === data.activeId)
        ? data.activeId
        : conversations[0].id;
    // Never restore a mid-stream phase; a reload strands it with no reader.
    return { conversations, activeId, phase: "idle", status: STATUS.idle };
  } catch {
    return null;
  }
}

export function deleteConversation(state: ThreadState, id: string): ThreadState {
  if (!state.conversations.some((c) => c.id === id)) return state;
  const conversations = state.conversations.filter((c) => c.id !== id);
  if (conversations.length === 0) {
    const conv = createConversation();
    return { conversations: [conv], activeId: conv.id, phase: "idle", status: STATUS.idle };
  }
  if (state.activeId !== id) return { ...state, conversations };
  return { ...state, conversations, activeId: conversations[0].id, phase: "idle", status: STATUS.idle };
}

/* ---------- Share links (encoded in the URL hash, no server) ---------- */

function toB64Url(json: string): string {
  const bytes = new TextEncoder().encode(json);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function fromB64Url(payload: string): string {
  const bin = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
  return new TextDecoder().decode(Uint8Array.from(bin, (ch) => ch.charCodeAt(0)));
}

function isShareMessage(v: unknown): v is { role: Role; content: string; sources: Source[] } {
  if (!isRecord(v) || (v.role !== "user" && v.role !== "assistant")) return false;
  if (typeof v.content !== "string" || !Array.isArray(v.sources)) return false;
  return (v.sources as unknown[]).every(
    (s) =>
      isRecord(s) &&
      typeof s.n === "number" &&
      typeof s.wp_id === "number" &&
      typeof s.title === "string" &&
      typeof s.published_at === "string" &&
      typeof s.url === "string",
  );
}

export function encodeShare(conv: Conversation): string {
  return toB64Url(
    JSON.stringify({
      v: 1,
      title: conv.title,
      messages: conv.messages.map((m) => ({ role: m.role, content: m.content, sources: m.sources })),
    }),
  );
}

export function decodeShare(payload: string): Conversation | null {
  try {
    const data: unknown = JSON.parse(fromB64Url(payload));
    if (!isRecord(data) || data.v !== 1 || typeof data.title !== "string") return null;
    if (!Array.isArray(data.messages) || !(data.messages as unknown[]).every(isShareMessage)) {
      return null;
    }
    const messages: Message[] = (data.messages as { role: Role; content: string; sources: Source[] }[]).map(
      (m) => ({ id: newId(), role: m.role, content: m.content, sources: m.sources }),
    );
    return { id: newId(), title: data.title as string, messages, createdAt: Date.now() };
  } catch {
    return null;
  }
}

/** Absolute share URL for a conversation; `base` keeps this DOM-free for tests. */
export function shareLink(conv: Conversation, base: string): string {
  return `${base}${SHARE_HASH_PREFIX}${encodeShare(conv)}`;
}

export function importSharedConversation(state: ThreadState, conv: Conversation): ThreadState {
  return {
    ...state,
    conversations: [conv, ...state.conversations],
    activeId: conv.id,
    phase: "idle",
    status: STATUS.idle,
  };
}
