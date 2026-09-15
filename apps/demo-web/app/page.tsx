"use client";

import { FormEvent, KeyboardEvent, ReactNode, useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import {
  ArrowUp,
  Check,
  Copy,
  Ellipsis,
  Menu,
  PanelLeftClose,
  Search,
  Share2,
  Square,
  SquarePen,
  Trash2,
  X,
  type LucideIcon,
} from "lucide-react";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "../components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../components/ui/dropdown-menu";

import {
  CHAT_PATH,
  FALLBACK_MODEL,
  NEW_CHAT_TITLE,
  PRICING_URL,
  STATUS,
  conversationUsage,
  pickSuggestions,
  totalUsage,
  SUGGESTION_COUNT,
  SUGGESTION_POOL,
  applySseEvent,
  beginTurn,
  canSend,
  cancelTurn,
  chatRequestBody,
  completeIfStreaming,
  createThreadState,
  filtersFor,
  historyFor,
  TIME_RANGES,
  type TimeRange,
  decodeShare,
  deleteConversation,
  failHttp,
  failNetwork,
  formatSourceDate,
  getActive,
  groupConversations,
  importSharedConversation,
  isBusy,
  listedConversations,
  loadThreads,
  parseSseBuffer,
  saveThreads,
  selectConversation,
  shareLink,
  SHARE_HASH_PREFIX,
  startNewChat,
  type Conversation,
  type Message,
  type Source,
  type ThreadState,
} from "../lib/chat";
import { parseBlocks, plainText, type Inline } from "../lib/format";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/* Shared dialog button base (ghost / danger / primary differ only in paint). */
const BTN_BASE =
  "inline-flex min-h-[40px] items-center justify-center gap-[8px] rounded-full border px-[18px] text-[0.875rem] font-medium whitespace-nowrap transition-colors duration-150 ease-app [&_svg]:size-[15px]";
const BTN_GHOST = `${BTN_BASE} border-line-strong bg-transparent text-ink hover:bg-hover`;
const BTN_DANGER = `${BTN_BASE} border-transparent bg-danger text-white hover:opacity-[0.88]`;
const BTN_PRIMARY = `${BTN_BASE} border-transparent bg-btn text-btn-fg hover:opacity-[0.85]`;

/* ---------- Composer ---------- */

function Composer({
  busy,
  autoFocus,
  onSend,
  onStop,
  className = "mx-auto w-[min(var(--content-w),100%)]",
}: {
  busy: boolean;
  autoFocus?: boolean;
  onSend: (message: string) => boolean;
  onStop: () => void;
  className?: string;
}) {
  const ref = useRef<HTMLTextAreaElement | null>(null);
  const [hasText, setHasText] = useState(false);

  function resize() {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    const message = ref.current?.value.trim() ?? "";
    if (!message || busy) return;
    if (!onSend(message)) return;
    if (ref.current) {
      ref.current.value = "";
      resize();
      ref.current.focus();
    }
    setHasText(false);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!busy && ref.current?.value.trim()) e.currentTarget.form?.requestSubmit();
    }
  }

  return (
    <form className={className} onSubmit={submit}>
      <div className="flex items-end gap-[8px] rounded-[28px] border border-line bg-canvas py-[9px] pr-[9px] pl-[20px] shadow-composer transition-all duration-200 ease-app focus-within:border-line-strong focus-within:shadow-composer-focus max-[768px]:rounded-[24px] max-[768px]:py-[7px] max-[768px]:pr-[7px] max-[768px]:pl-[16px]">
        <textarea
          ref={ref}
          rows={1}
          maxLength={500}
          autoFocus={autoFocus}
          onInput={(e) => {
            setHasText(Boolean(e.currentTarget.value.trim()));
            resize();
          }}
          onKeyDown={onKeyDown}
          placeholder="Baza ikibazo"
          aria-label="Andika ikibazo cyawe"
          className="max-h-[200px] min-h-[38px] flex-1 resize-none border-0 bg-transparent px-0 py-[7px] text-[1rem] leading-[1.5] outline-none placeholder:text-ink-faint max-[768px]:min-h-[36px] max-[768px]:py-[6px] max-[768px]:text-[0.95rem]"
        />
        {busy ? (
          <button type="button" className="inline-flex size-[38px] shrink-0 items-center justify-center rounded-full border-0 bg-btn text-[0.72rem] text-btn-fg transition-all duration-150 ease-app hover:opacity-80 active:scale-95 disabled:cursor-default disabled:bg-btn-disabled max-[768px]:size-[36px]" onClick={onStop} aria-label="Hagarika">
            <Square fill="currentColor" aria-hidden="true" className="size-[12px]" />
          </button>
        ) : (
          <button type="submit" className="inline-flex size-[38px] shrink-0 items-center justify-center rounded-full border-0 bg-btn text-[0.95rem] text-btn-fg transition-all duration-150 ease-app hover:opacity-80 active:scale-95 disabled:cursor-default disabled:bg-btn-disabled max-[768px]:size-[36px]" disabled={!hasText} aria-label="Ohereza">
            <ArrowUp aria-hidden="true" className="size-[18px] shrink-0" />
          </button>
        )}
      </div>
    </form>
  );
}

/* ---------- Answer rendering ---------- */

const CITE_CLASSES =
  "ml-[3px] inline-flex h-[17px] min-w-[17px] items-center justify-center rounded-full bg-chip px-[4px] align-[2px] text-[0.68rem] font-semibold leading-none text-ink-soft no-underline transition-colors duration-150 ease-app";

function Cite({ n, source }: { n: number; source?: Source }) {
  if (!source) {
    return (
      <span className={`${CITE_CLASSES} opacity-60`} aria-label={`Inkomoko ${n}`}>
        {n}
      </span>
    );
  }
  return (
    <a
      className={`${CITE_CLASSES} ml-[3px] hover:bg-brand-soft hover:text-brand focus-visible:bg-brand-soft focus-visible:text-brand focus-visible:outline-offset-[1px]`}
      href={source.url}
      target="_blank"
      rel="noreferrer"
      title={source.title}
    >
      {n}
    </a>
  );
}

function Inlines({ inlines, sources }: { inlines: Inline[]; sources: Map<number, Source> }) {
  return (
    <>
      {inlines.map((inline, i) => {
        switch (inline.kind) {
          case "text":
            return <span key={i}>{inline.text}</span>;
          case "strong":
            return <strong key={i}>{inline.text}</strong>;
          case "link":
            return (
              <a key={i} href={inline.url} target="_blank" rel="noreferrer">
                {inline.text}
              </a>
            );
          case "br":
            return <br key={i} />;
          case "cite":
            return <Cite key={i} n={inline.n} source={sources.get(inline.n)} />;
        }
      })}
    </>
  );
}

function Prose({ text, sources, streaming }: { text: string; sources: Source[]; streaming: boolean }) {
  const map = new Map(sources.map((s) => [s.n, s]));
  const blocks = parseBlocks(text);
  return (
    <div className="prose">
      {blocks.map((block, i) => {
        const last = i === blocks.length - 1;
        const cursor = streaming && last ? (
          <span className="ml-[6px] inline-block size-[10px] animate-throb rounded-full bg-ink align-[-1px]" aria-hidden="true" />
        ) : null;
        if (block.kind === "p") {
          return (
            <p key={i}>
              <Inlines inlines={block.inlines} sources={map} />
              {cursor}
            </p>
          );
        }
        const Tag = block.kind;
        return (
          <Tag key={i}>
            {block.items.map((item, j) => (
              <li key={j}>
                <Inlines inlines={item} sources={map} />
                {cursor && j === block.items.length - 1 ? cursor : null}
              </li>
            ))}
          </Tag>
        );
      })}
    </div>
  );
}

function StatusLine({ text }: { text: string }) {
  return (
    <div className="flex min-h-[27px] items-center gap-[10px] text-[1rem] leading-[1.7] max-[768px]:text-[0.95rem]" role="status">
      <span className="size-[10px] animate-throb rounded-full bg-ink" aria-hidden="true" />
      <span className="shimmer-text animate-shimmer bg-[linear-gradient(90deg,var(--color-ink-faint)_0%,var(--color-ink)_50%,var(--color-ink-faint)_100%)] bg-[length:200%_100%] bg-clip-text text-transparent text-ink-soft">{text}</span>
    </div>
  );
}

function Sources({ sources }: { sources: Source[] }) {
  return (
    <section className="mt-[16px]" aria-label="Inkomoko">
      <h3 className="m-0 mb-[8px] text-[0.8rem] font-semibold text-ink-soft">Inkomoko</h3>
      <ol className="m-0 flex list-none flex-wrap gap-[8px] p-0">
        {sources.map((s) => (
          <li key={s.n} className="max-w-full flex-[1_1_280px] max-[768px]:basis-full">
            <a className="group flex h-full items-start gap-[10px] rounded-[12px] border border-line bg-sidebar px-[12px] py-[10px] text-ink no-underline transition-colors duration-150 ease-app hover:border-line-strong hover:bg-hover" href={s.url} target="_blank" rel="noreferrer">
              <span className="mt-[1px] inline-flex size-[20px] shrink-0 items-center justify-center rounded-full bg-chip text-[0.68rem] font-semibold text-ink-soft group-hover:bg-brand-soft group-hover:text-brand" aria-hidden="true">
                {s.n}
              </span>
              <span className="flex min-w-0 flex-col gap-[2px]">
                <span className="line-clamp-2 text-[0.84rem] font-medium leading-[1.35]">{s.title}</span>
                <span className="text-[0.72rem] text-ink-faint">
                  igihe.com · {formatSourceDate(s.published_at)}
                </span>
              </span>
            </a>
          </li>
        ))}
      </ol>
    </section>
  );
}

function CopyButton({ message }: { message: Message }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    const lines = [plainText(message.content)];
    if (message.sources.length) {
      lines.push("", "Inkomoko:");
      for (const s of message.sources) lines.push(`[${s.n}] ${s.title} — ${s.url}`);
    }
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable: nothing to recover from */
    }
  }
  return (
    <button type="button" className="inline-flex size-[30px] items-center justify-center rounded-[8px] border-0 bg-transparent p-0 text-[0.82rem] text-ink-soft transition-colors duration-150 ease-app hover:bg-hover hover:text-ink" onClick={copy} aria-label={copied ? "Byakoporowe" : "Koporora"}>
      {copied ? <Check aria-hidden="true" className="size-[18px] shrink-0" /> : <Copy aria-hidden="true" className="size-[18px] shrink-0" />}
    </button>
  );
}

function SuggestionList({
  items, label, onPick, className = "",
}: { items: string[]; label?: string; onPick: (q: string) => void; className?: string }) {
  if (!items.length) return null;
  // The labelled in-turn group sits under the refusal with left-aligned,
  // staggered chips; the welcome group stays centered without a label.
  const inTurn = className.includes("in-turn");
  return (
    <div className={className}>
      {label ? <p className="m-0 mb-[8px] text-[0.7rem] font-semibold tracking-[0.08em] text-ink-faint uppercase">{label}</p> : null}
      <ul className={`m-0 flex list-none flex-wrap gap-[8px] p-0 ${inTurn ? "items-start justify-start" : "mt-[18px] justify-center"}`} aria-label="Ingero z'ibibazo">
        {items.map((q, i) => (
          <li key={q} style={{ "--i": i } as CSSProperties} className={inTurn ? "animate-rise-chip [animation-delay:calc(var(--i,0)*60ms)]" : undefined}>
            <button type="button" className="group inline-flex max-w-[min(100%,44ch)] items-center gap-[7px] rounded-full border border-line bg-transparent px-[14px] py-[8px] text-left text-[0.84rem] leading-[1.3] text-ink-soft transition-colors duration-150 ease-app hover:border-hover hover:bg-hover hover:text-ink focus-visible:border-hover" onClick={() => onPick(q)}>
              <Search className="size-[14px] shrink-0 text-ink-faint transition-colors duration-150 ease-app group-hover:text-brand group-focus-visible:text-brand" aria-hidden="true" />
              <span>{q}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function AssistantTurn({
  message,
  streaming,
  status,
  onSuggest,
}: {
  message: Message;
  streaming: boolean;
  status: string;
  onSuggest: (question: string) => void;
}) {
  const waiting = streaming && !message.content;
  // Error/muted tones inherit into the prose, which sets no color of its own.
  const tone = message.error ? "text-danger" : message.muted ? "text-ink-faint italic" : "";
  return (
    <article className={`group mb-[28px] animate-rise py-[2px] ${tone} max-[768px]:mb-[22px]`}>
      {waiting ? (
        <StatusLine text={status} />
      ) : (
        <Prose text={message.content} sources={message.sources} streaming={streaming} />
      )}
      {message.sources.length > 0 ? <Sources sources={message.sources} /> : null}
      {!streaming && message.suggestions?.length ? (
        <SuggestionList items={message.suggestions ?? []} label="Gerageza kimwe muri ibi" onPick={onSuggest} className="in-turn mt-[14px]" />
      ) : null}
      {!streaming && message.content && !message.error && !message.muted ? (
        <div className="mt-[6px] ml-[-8px] flex gap-[2px] opacity-0 transition-opacity duration-150 ease-app group-hover:opacity-100 group-focus-within:opacity-100 max-[768px]:opacity-100">
          <CopyButton message={message} />
        </div>
      ) : null}
    </article>
  );
}

/* Token usage ledger: newsroom-ruled table, tabular numerals. */
function UsageTable({ caption, rows }: { caption: string; rows: [string, string][] }) {
  const last = rows.length - 1;
  return (
    <table className="mb-[16px] w-full border-collapse tabular-nums">
      <caption className="pb-[6px] text-left text-[0.78rem] font-semibold text-ink">{caption}</caption>
      <tbody>
        {rows.map(([label, value], i) => (
          <tr
            key={label}
            className={
              i === last
                ? "font-semibold text-ink [&_td]:border-t [&_td]:border-line-strong [&_td]:border-b-2 [&_td]:border-b-brand [&_th]:border-t [&_th]:border-line-strong [&_th]:border-b-2 [&_th]:border-b-brand"
                : "[&_td]:border-t [&_td]:border-line [&_th]:border-t [&_th]:border-line"
            }
          >
            <th scope="row" className={`px-[2px] py-[7px] text-left text-[0.85rem] text-ink-soft${i === last ? " font-semibold" : " font-normal"}`}>
              {label}
            </th>
            <td className="px-[2px] py-[7px] text-right text-[0.85rem] text-ink">{value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/* ---------- Page ---------- */

function IconButton({
  label,
  icon: Icon,
  onClick,
  className = "",
  buttonClassName = "size-[36px] rounded-[8px]",
  iconClassName = "size-[18px] shrink-0",
}: {
  label: string;
  icon: LucideIcon;
  onClick: () => void;
  className?: string;
  buttonClassName?: string;
  iconClassName?: string;
}) {
  return (
    <button type="button" className={`inline-flex shrink-0 items-center justify-center border-0 bg-transparent p-0 text-ink-soft transition-colors duration-150 ease-app hover:bg-hover hover:text-ink ${buttonClassName} ${className}`} aria-label={label} title={label} onClick={onClick}>
      <Icon aria-hidden="true" className={iconClassName} />
    </button>
  );
}

export default function Home() {
  // Server and first client render must match, so the initial state never
  // touches localStorage or Math.random; saved chats are restored on mount.
  const [state, setState] = useState<ThreadState>(() => createThreadState("demo-web"));
  const [hydrated, setHydrated] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>(() => SUGGESTION_POOL.slice(0, SUGGESTION_COUNT));
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [modal, setModal] = useState<{ type: "share" | "delete" | "usage"; id?: string; link?: string } | null>(
    null,
  );
  const [linkCopied, setLinkCopied] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [timeRange, setTimeRange] = useState<TimeRange>("all");
  const threadRef = useRef<HTMLDivElement | null>(null);
  const stickToBottom = useRef(true);
  const abortRef = useRef<AbortController | null>(null);
  const inFlight = useRef(false);

  const active = getActive(state);
  const messages = active?.messages ?? [];
  const empty = messages.length === 0;
  const busy = isBusy(state.phase);
  const groups = groupConversations(listedConversations(state));
  const usageActive = active ? conversationUsage(active) : null;
  const usageTotal = totalUsage(state);
  const usageModel = usageActive?.model ?? FALLBACK_MODEL;

  // Follow the stream only while the reader is already at the bottom.
  const onThreadScroll = useCallback(() => {
    const el = threadRef.current;
    if (!el) return;
    stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 96;
  }, []);

  useEffect(() => {
    const el = threadRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [messages, state.phase]);

  useEffect(() => {
    stickToBottom.current = true;
  }, [state.activeId]);

  async function streamReply(conversationId: string, message: string, history: ReturnType<typeof historyFor>) {
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const resp = await fetch(`${API_URL}${CHAT_PATH}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(chatRequestBody(conversationId, message, history, filtersFor(timeRange))),
        signal: controller.signal,
      });
      if (resp.status === 413 || resp.status === 429 || !resp.ok || !resp.body) {
        setState((s) => failHttp(s, resp.status, conversationId));
        return;
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const parsed = parseSseBuffer(buf);
        buf = parsed.remaining;
        for (const ev of parsed.events) {
          setState((s) => applySseEvent(s, ev, conversationId));
        }
      }
      setState((s) => completeIfStreaming(s));
    } catch (err) {
      if (controller.signal.aborted) {
        setState((s) => cancelTurn(s, conversationId));
      } else {
        setState((s) => failNetwork(s, conversationId));
      }
    } finally {
      inFlight.current = false;
      if (abortRef.current === controller) abortRef.current = null;
    }
  }

  // Guards against a double send between the click and React committing the
  // "searching" phase; state updaters are not guaranteed to run synchronously.
  function send(message: string): boolean {
    if (inFlight.current || !canSend(state.phase, message)) return false;
    inFlight.current = true;
    const conversationId = state.activeId;
    // Prior turns travel with the question so one-word follow-ups keep their topic.
    const history = historyFor(state.conversations.find((c) => c.id === conversationId));
    setState((s) => beginTurn(s, message));
    stickToBottom.current = true;
    void streamReply(conversationId, message, history);
    return true;
  }

  function stop() {
    abortRef.current?.abort();
  }

  function onNewChat() {
    setState((s) => startNewChat(s));
    setSuggestions(pickSuggestions());
    setDrawerOpen(false);
  }

  function onSelect(id: string) {
    setState((s) => selectConversation(s, id));
    setDrawerOpen(false);
  }

  function openShare(conv: Conversation) {
    const base = `${window.location.origin}${window.location.pathname}`;
    setLinkCopied(false);
    setModal({ type: "share", id: conv.id, link: shareLink(conv, base) });
  }

  async function copyShareLink() {
    if (!modal?.link) return;
    try {
      await navigator.clipboard.writeText(modal.link);
      setLinkCopied(true);
    } catch {
      /* clipboard unavailable: the link stays selectable above */
    }
  }

  function openDelete(id: string) {
    setModal({ type: "delete", id });
  }

  function confirmDelete() {
    if (!modal || modal.type !== "delete" || !modal.id) return;
    const id = modal.id;
    setModal(null);
    stop();
    setState((s) => deleteConversation(s, id));
  }

  // Restore chats saved on this device, then persist every change. Saving
  // waits for the restore so an empty first render never overwrites storage;
  // failures (private mode, quota) keep the demo memory-only.
  useEffect(() => {
    const saved = loadThreads();
    if (saved) setState(saved);
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (hydrated) saveThreads(state);
  }, [state, hydrated]);

  // Open a shared conversation link exactly once per load. The ref guard
  // keeps StrictMode's double-mount (dev) from importing it twice.
  const sharedImportDone = useRef(false);
  useEffect(() => {
    if (sharedImportDone.current) return;
    sharedImportDone.current = true;
    const hash = window.location.hash;
    if (!hash.startsWith(SHARE_HASH_PREFIX)) return;
    const conv = decodeShare(hash.slice(SHARE_HASH_PREFIX.length));
    if (conv) {
      setState((s) => importSharedConversation(s, conv));
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const composer = (props: { autoFocus?: boolean; className?: string }) => (
    <Composer busy={busy} onSend={send} onStop={stop} autoFocus={props.autoFocus} className={props.className} />
  );

  const footnote: ReactNode = (
    <div className="mx-auto mt-[10px] flex w-[min(var(--content-w),100%)] flex-wrap items-center justify-center gap-x-[14px] gap-y-[4px] text-[0.72rem] leading-[1.4] text-ink-faint">
      <label className="inline-flex items-center gap-[6px]">
        <span>Igihe:</span>
        <select
          aria-label="Hitamo igihe cy'inkuru"
          className="rounded-full border border-line bg-canvas px-[10px] py-[3px] text-[0.72rem] text-ink focus:outline-none focus:border-line-strong"
          value={timeRange}
          onChange={(e) => setTimeRange(e.target.value as TimeRange)}
        >
          {TIME_RANGES.map((r) => (
            <option key={r.value} value={r.value}>{r.label}</option>
          ))}
        </select>
      </label>
      <span>Umufasha ashobora kwibeshya. Genzura amakuru mu nkuru za IGIHE.</span>
    </div>
  );

  return (
    <div className="flex h-dvh overflow-hidden bg-canvas">
      {drawerOpen ? (
        <button type="button" className="fixed inset-0 z-20 animate-fade border-0 bg-black/40 p-0 min-[769px]:hidden" aria-label="Funga urutonde rw'ibiganiro" onClick={() => setDrawerOpen(false)} />
      ) : null}

      <aside
        className={`w-(--sidebar-w) shrink-0 overflow-hidden bg-sidebar transition-[width] duration-[250ms] ease-app max-[768px]:fixed max-[768px]:inset-y-0 max-[768px]:left-0 max-[768px]:z-30 max-[768px]:h-dvh max-[768px]:shadow-[0_0_40px_rgba(0,0,0,0.2)] max-[768px]:transition-transform ${collapsed ? "min-[769px]:w-0" : ""} ${drawerOpen ? "max-[768px]:translate-x-0" : "max-[768px]:-translate-x-full"}`}
        aria-label="Ibiganiro"
      >
        <div className="flex h-full w-(--sidebar-w) flex-col p-[8px]">
          <div className="mb-[4px] flex h-[44px] items-center justify-between pr-[4px] pl-[10px]">
            <span className="inline-flex items-baseline text-[0.8rem] font-bold tracking-[0.14em] text-ink">
              IGIHE<span className="ml-[2px] size-[6px] rounded-full bg-brand" aria-hidden="true" />
            </span>
            <IconButton label="Hisha urutonde rw'ibiganiro" icon={PanelLeftClose} className="max-[768px]:hidden" onClick={() => setCollapsed(true)} />
            <IconButton
              label="Funga"
              icon={X}
              className="max-[768px]:inline-flex min-[769px]:hidden"
              onClick={() => setDrawerOpen(false)}
            />
      
          </div>

          <button type="button" className="mb-[12px] flex min-h-[36px] w-full items-center gap-[10px] rounded-[10px] border-0 bg-transparent px-[10px] py-[8px] text-left text-[0.875rem] font-medium text-ink transition-colors duration-150 ease-app hover:bg-hover [&_svg]:size-[18px] [&_svg]:shrink-0 [&_svg]:text-ink-soft" onClick={onNewChat}>
            <SquarePen aria-hidden="true" />
            <span>{NEW_CHAT_TITLE}</span>
          </button>

          <nav className="min-h-0 flex-1 space-y-[12px] overflow-y-auto pb-[8px]">
            {groups.length === 0 ? (
              <p className="m-0 px-[10px] py-[8px] text-[0.8rem] leading-[1.5] text-ink-faint">Ibiganiro byawe bizagaragara hano.</p>
            ) : (
              groups.map((g) => (
                <div key={g.label}>
                  <h2 className="m-0 px-[10px] pt-[8px] pb-[4px] text-[0.72rem] font-semibold text-ink-faint">{g.label}</h2>
                  {g.items.map((c) => (
                    <div className="group/row relative flex w-full items-center rounded-[10px] transition-colors duration-150 ease-app has-[.active]:bg-active hover:bg-hover focus-within:bg-hover has-[[data-state=open]]:bg-hover" key={c.id}>
                      <button
                        type="button"
                        className={`min-w-0 flex-1 border-0 bg-transparent px-[10px] py-[8px] pr-[10px] text-left text-[0.875rem] text-ink transition-all duration-150 ease-app group-hover/row:pr-[32px] group-focus-within/row:pr-[32px] group-has-[[data-state=open]]/row:pr-[32px] max-[768px]:pr-[32px]${c.id === state.activeId ? " active" : ""}`}
                        aria-current={c.id === state.activeId ? "page" : undefined}
                        onClick={() => onSelect(c.id)}
                      >
                        <span className="block overflow-hidden whitespace-nowrap [-webkit-mask-image:linear-gradient(to_right,#000_calc(100%-24px),transparent)] [mask-image:linear-gradient(to_right,#000_calc(100%-24px),transparent)]">{c.title}</span>
                      </button>
                      <div className="absolute top-1/2 right-[6px] flex -translate-y-1/2 items-center opacity-0 transition-opacity duration-150 ease-app group-hover/row:opacity-100 group-focus-within/row:opacity-100 group-has-[[data-state=open]]/row:opacity-100 max-[768px]:opacity-100">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <button
                              type="button"
                              className="inline-flex size-[24px] shrink-0 items-center justify-center rounded-[6px] border-0 bg-transparent p-0 text-ink-soft transition-colors duration-150 ease-app hover:bg-transparent hover:text-ink [&_svg]:size-4 [&_svg]:shrink-0"
                              aria-label="Amahitamo y'ikiganiro"
                              title="Amahitamo"
                            >
                              <Ellipsis aria-hidden="true" />
                            </button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onSelect={() => openShare(c)}>
                              <Share2 aria-hidden="true" />
                              <span>Sangiza ikiganiro</span>
                            </DropdownMenuItem>
                            <DropdownMenuItem onSelect={() => openDelete(c.id)} className="text-danger data-[highlighted]:bg-danger-soft [&_svg]:text-danger">
                              <Trash2 aria-hidden="true" />
                              <span>Siba ikiganiro</span>
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </div>
                  ))}
                </div>
              ))
            )}
          </nav>

          <div className="border-t border-line px-[10px] pt-[12px] pb-[6px] text-center text-[0.72rem] text-ink-faint">
            Inkuru za IGIHE · demo
            <br />
            Ibiganiro bibikwa kuri iki gikoresho gusa
            <br />
            <button
              type="button"
              className="mt-[4px] border-0 bg-transparent p-0 text-[0.72rem] text-ink-soft underline underline-offset-[2px] hover:text-ink"
              onClick={() => setModal({ type: "usage", id: state.activeId })}
              aria-label="Reba ikoreshwa rya tokens"
            >
              Reba ikoreshwa rya tokens
            </button>
          </div>
        </div>
      </aside>

      <main className="relative flex min-w-0 flex-1 flex-col">
        <header className="flex h-(--topbar-h) shrink-0 items-center gap-[6px] px-[12px] max-[768px]:border-b max-[768px]:border-line max-[768px]:px-[8px]">
          <IconButton label="Fungura urutonde rw'ibiganiro" icon={Menu} className="min-[769px]:hidden" onClick={() => setDrawerOpen(true)} />
          <IconButton
            label="Erekana urutonde rw'ibiganiro"
            icon={Menu}
            className={`max-[768px]:hidden${collapsed ? "" : " min-[769px]:hidden"}`}
            onClick={() => setCollapsed(false)}
          />
          <span className="inline-flex items-center gap-[8px] truncate px-[6px] text-[0.95rem] font-semibold tracking-[-0.01em] text-ink max-[768px]:flex-1 max-[768px]:justify-center max-[768px]:text-[0.9rem]">
            IGIHE News Assistant
            <span className="rounded-full bg-chip px-[7px] py-[2px] text-[0.64rem] font-semibold tracking-[0.06em] text-ink-soft uppercase">Demo</span>
          </span>
          <IconButton label={NEW_CHAT_TITLE} icon={SquarePen} className={`ml-auto${collapsed ? "" : " min-[769px]:hidden"}`} onClick={onNewChat} />
        </header>

        {empty ? (
          <div className="flex min-h-0 flex-1 flex-col items-center overflow-y-auto px-[16px] pb-[12px]">
            <div className="my-auto flex w-[min(var(--content-w),100%)] animate-rise-slow flex-col items-center pb-[8vh] max-[768px]:pb-[4vh]">
              <h1 className="m-0 mb-[6px] text-center text-[clamp(1.5rem,3vw,1.85rem)] leading-[1.25] font-semibold tracking-[-0.02em]">Nagufasha iki uyu munsi?</h1>
              <p className="m-0 mb-[28px] text-center text-[0.95rem] text-ink-soft max-[768px]:mb-[20px]">Baza mu Kinyarwanda ikibazo cyose ku nkuru za IGIHE.</p>
              {composer({ autoFocus: true, className: "w-full" })}
              <SuggestionList items={suggestions} onPick={send} />
            </div>
            {footnote}
          </div>
        ) : (
          <>
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain" ref={threadRef} onScroll={onThreadScroll}>
              <div className="mx-auto w-[min(var(--content-w),100%)] px-[16px] pt-[16px] pb-[24px] max-[768px]:px-[14px] max-[768px]:pt-[12px] max-[768px]:pb-[20px]" role="log" aria-live="polite">
                {messages.map((m, i) => {
                  const streamingThis = m.role === "assistant" && busy && i === messages.length - 1;
                  return m.role === "user" ? (
                    <article key={m.id} className="group mb-[28px] flex animate-rise justify-end max-[768px]:mb-[22px]">
                      <div className="max-w-[70%] rounded-[18px] bg-bubble px-[16px] py-[10px] text-[1rem] leading-[1.6] whitespace-pre-wrap text-ink [overflow-wrap:anywhere] max-[768px]:max-w-[85%] max-[768px]:text-[0.95rem]">{m.content}</div>
                    </article>
                  ) : (
                    <AssistantTurn key={m.id} message={m} streaming={streamingThis} status={state.status} onSuggest={send} />
                  );
                })}
              </div>
            </div>
            <div className="shrink-0 bg-canvas px-[16px] pt-[6px] pb-[10px] max-[768px]:px-[12px] max-[768px]:pb-[8px]">
              {composer({ autoFocus: true })}
              {footnote}
            </div>
          </>
        )}
      </main>

      <Dialog open={modal?.type === "delete"} onOpenChange={(open) => { if (!open) setModal(null); }}>
        <DialogContent>
          <DialogTitle>Siba ikiganiro?</DialogTitle>
          <DialogDescription>
            {(() => {
              const conv = modal ? state.conversations.find((c) => c.id === modal.id) : undefined;
              return (
                <>
                  Ikiganiro {conv ? `“${conv.title}” ` : ""}kizasibwa burundu kuri iki gikoresho. Ntibishobora gusubizwaho.
                </>
              );
            })()}
          </DialogDescription>
          <DialogFooter>
            <DialogClose asChild>
              <button type="button" className={BTN_GHOST}>
                Reka
              </button>
            </DialogClose>
            <button type="button" className={BTN_DANGER} onClick={confirmDelete} autoFocus>
              Siba
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={modal?.type === "share"} onOpenChange={(open) => { if (!open) setModal(null); }}>
        <DialogContent>
          <DialogTitle>Sangiza ikiganiro</DialogTitle>
          <DialogDescription>
            Umuntu wese ufite iri huza ashobora kubona iki kiganiro.
          </DialogDescription>
          <div className="mb-[20px] flex gap-[8px]">
            <input
              className="min-h-[40px] min-w-0 flex-1 rounded-full border border-line-strong bg-sidebar px-[16px] text-[0.8rem] text-ink-soft text-ellipsis focus:border-ink-faint focus:text-ink focus:outline-none"
              readOnly
              value={modal?.link ?? ""}
              aria-label="Ihuza ryo gusangiza"
              onFocus={(e) => e.currentTarget.select()}
            />
            <button type="button" className={BTN_PRIMARY} onClick={copyShareLink}>
              {linkCopied ? (
                <>
                  <Check aria-hidden="true" className="size-[15px]" /> Ryakoporowe
                </>
              ) : (
                "Koporora ihuza"
              )}
            </button>
          </div>
          <DialogFooter>
            <DialogClose asChild>
              <button type="button" className={BTN_GHOST}>
                Funga
              </button>
            </DialogClose>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={modal?.type === "usage"} onOpenChange={(open) => { if (!open) setModal(null); }}>
        <DialogContent>
          <DialogTitle>Ikoreshwa rya tokens</DialogTitle>
          <DialogDescription>
            Ibibarwa ni igereranya (~), si fagitire. Bara inyuguti / 4 kuri buri butumwa.
          </DialogDescription>
          <div className="mb-[20px]">
            <p className="m-0 mb-[12px] text-[0.8rem] text-ink-soft">
              Model: <span className="break-all text-ink tabular-nums">{usageModel}</span>
            </p>
            <UsageTable
              caption="Iki kiganiro"
              rows={[
                ["Ibyoherejwe (injyana)", `~${usageActive?.inputTokens ?? 0}`],
                ["Ibyakiriwe (insubizo)", `~${usageActive?.outputTokens ?? 0}`],
                ["Igiteranyo", `~${usageActive?.total ?? 0}`],
              ]}
            />
            <UsageTable
              caption="Ibiganiro byose"
              rows={[
                ["Ibyoherejwe (injyana)", `~${usageTotal.inputTokens}`],
                ["Ibyakiriwe (insubizo)", `~${usageTotal.outputTokens}`],
                ["Igiteranyo", `~${usageTotal.total}`],
              ]}
            />
            <a className="text-[0.8rem] text-brand underline-offset-[2px]" href={PRICING_URL} target="_blank" rel="noreferrer">
              Gereranya ibiciro bya OpenAI ({usageModel}) ↗
            </a>
          </div>
          <DialogFooter>
            <DialogClose asChild>
              <button type="button" className={BTN_GHOST}>
                Funga
              </button>
            </DialogClose>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
