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

/* ---------- Composer ---------- */

function Composer({
  busy,
  autoFocus,
  onSend,
  onStop,
}: {
  busy: boolean;
  autoFocus?: boolean;
  onSend: (message: string) => boolean;
  onStop: () => void;
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
    <form className="composer" onSubmit={submit}>
      <div className="composer-box">
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
        />
        {busy ? (
          <button type="button" className="composer-action stop" onClick={onStop} aria-label="Hagarika">
            <Square fill="currentColor" aria-hidden="true" />
          </button>
        ) : (
          <button type="submit" className="composer-action send" disabled={!hasText} aria-label="Ohereza">
            <ArrowUp aria-hidden="true" />
          </button>
        )}
      </div>
    </form>
  );
}

/* ---------- Answer rendering ---------- */

function Cite({ n, source }: { n: number; source?: Source }) {
  if (!source) {
    return (
      <span className="cite cite-pending" aria-label={`Inkomoko ${n}`}>
        {n}
      </span>
    );
  }
  return (
    <a className="cite" href={source.url} target="_blank" rel="noreferrer" title={source.title}>
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
        const cursor = streaming && last ? <span className="cursor" aria-hidden="true" /> : null;
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
    <div className="status-line" role="status">
      <span className="status-dot" aria-hidden="true" />
      <span className="status-text">{text}</span>
    </div>
  );
}

function Sources({ sources }: { sources: Source[] }) {
  return (
    <section className="sources" aria-label="Inkomoko">
      <h3 className="sources-title">Inkomoko</h3>
      <ol className="sources-list">
        {sources.map((s) => (
          <li key={s.n}>
            <a className="source-card" href={s.url} target="_blank" rel="noreferrer">
              <span className="source-n" aria-hidden="true">
                {s.n}
              </span>
              <span className="source-body">
                <span className="source-title">{s.title}</span>
                <span className="source-meta">
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
    <button type="button" className="icon-btn action" onClick={copy} aria-label={copied ? "Byakoporowe" : "Koporora"}>
      {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
    </button>
  );
}

function SuggestionList({
  items, label, onPick, className = "",
}: { items: string[]; label?: string; onPick: (q: string) => void; className?: string }) {
  if (!items.length) return null;
  return (
    <div className={`suggestion-group ${className}`}>
      {label ? <p className="suggestions-label">{label}</p> : null}
      <ul className={`suggestions`} aria-label="Ingero z'ibibazo">
        {items.map((q, i) => (
          <li key={q} style={{ "--i": i } as CSSProperties}>
            <button type="button" className="suggestion" onClick={() => onPick(q)}>
              <Search className="suggestion-icon" aria-hidden="true" />
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
  const tone = message.error ? " error" : message.muted ? " muted" : "";
  return (
    <article className={`turn assistant${tone}`}>
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
        <div className="turn-actions">
          <CopyButton message={message} />
        </div>
      ) : null}
    </article>
  );
}

/* ---------- Page ---------- */

function IconButton({
  label,
  icon: Icon,
  onClick,
  className = "",
}: {
  label: string;
  icon: LucideIcon;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button type="button" className={`icon-btn ${className}`} aria-label={label} title={label} onClick={onClick}>
      <Icon aria-hidden="true" />
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

  async function streamReply(conversationId: string, message: string) {
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const resp = await fetch(`${API_URL}${CHAT_PATH}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(chatRequestBody(conversationId, message)),
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
    setState((s) => beginTurn(s, message));
    stickToBottom.current = true;
    void streamReply(conversationId, message);
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

  const composer = (props: { autoFocus?: boolean }) => (
    <Composer busy={busy} onSend={send} onStop={stop} autoFocus={props.autoFocus} />
  );

  const footnote: ReactNode = (
    <p className="footnote">Umufasha ashobora kwibeshya. Genzura amakuru mu nkuru za IGIHE.</p>
  );

  return (
    <div className={`shell${collapsed ? " collapsed" : ""}`}>
      {drawerOpen ? (
        <button type="button" className="backdrop" aria-label="Funga urutonde rw'ibiganiro" onClick={() => setDrawerOpen(false)} />
      ) : null}

      <aside className={`sidebar${drawerOpen ? " open" : ""}`} aria-label="Ibiganiro">
        <div className="sidebar-inner">
          <div className="sidebar-head">
            <span className="brand">
              IGIHE<span className="brand-dot" aria-hidden="true" />
            </span>
            <IconButton label="Hisha urutonde rw'ibiganiro" icon={PanelLeftClose} className="only-desktop" onClick={() => setCollapsed(true)} />
            <IconButton label="Funga" icon={X} className="only-mobile" onClick={() => setDrawerOpen(false)} />
          </div>

          <button type="button" className="sidebar-row new-chat" onClick={onNewChat}>
            <SquarePen aria-hidden="true" />
            <span>{NEW_CHAT_TITLE}</span>
          </button>

          <nav className="history">
            {groups.length === 0 ? (
              <p className="history-empty">Ibiganiro byawe bizagaragara hano.</p>
            ) : (
              groups.map((g) => (
                <div className="history-group" key={g.label}>
                  <h2 className="history-label">{g.label}</h2>
                  {g.items.map((c) => (
                    <div className="history-item-row" key={c.id}>
                      <button
                        type="button"
                        className={`sidebar-row history-item${c.id === state.activeId ? " active" : ""}`}
                        aria-current={c.id === state.activeId ? "page" : undefined}
                        onClick={() => onSelect(c.id)}
                      >
                        <span className="history-title">{c.title}</span>
                      </button>
                      <div className="history-actions">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <button
                              type="button"
                              className="icon-btn"
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
                            <DropdownMenuItem onSelect={() => openDelete(c.id)} className="danger">
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

          <div className="sidebar-foot">
            Inkuru za IGIHE · demo
            <br />
            Ibiganiro bibikwa kuri iki gikoresho gusa
            <br />
            <button
              type="button"
              className="foot-link"
              onClick={() => setModal({ type: "usage", id: state.activeId })}
              aria-label="Reba ikoreshwa rya tokens"
            >
              Reba ikoreshwa rya tokens
            </button>
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <IconButton label="Fungura urutonde rw'ibiganiro" icon={Menu} className="only-mobile" onClick={() => setDrawerOpen(true)} />
          <IconButton
            label="Erekana urutonde rw'ibiganiro"
            icon={Menu}
            className="only-desktop topbar-expand"
            onClick={() => setCollapsed(false)}
          />
          <span className="topbar-title">
            IGIHE News Assistant
            <span className="badge">Demo</span>
          </span>
          <IconButton label={NEW_CHAT_TITLE} icon={SquarePen} className="topbar-new" onClick={onNewChat} />
        </header>

        {empty ? (
          <div className="welcome">
            <div className="welcome-inner">
              <h1 className="welcome-title">Nagufasha iki uyu munsi?</h1>
              <p className="welcome-sub">Baza mu Kinyarwanda ikibazo cyose ku nkuru za IGIHE.</p>
              {composer({ autoFocus: true })}
              <SuggestionList items={suggestions} onPick={send} />
            </div>
            {footnote}
          </div>
        ) : (
          <>
            <div className="thread" ref={threadRef} onScroll={onThreadScroll}>
              <div className="thread-inner" role="log" aria-live="polite">
                {messages.map((m, i) => {
                  const streamingThis = m.role === "assistant" && busy && i === messages.length - 1;
                  return m.role === "user" ? (
                    <article key={m.id} className="turn user">
                      <div className="user-bubble">{m.content}</div>
                    </article>
                  ) : (
                    <AssistantTurn key={m.id} message={m} streaming={streamingThis} status={state.status} onSuggest={send} />
                  );
                })}
              </div>
            </div>
            <div className="dock">
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
              <button type="button" className="btn-ghost">
                Reka
              </button>
            </DialogClose>
            <button type="button" className="btn-danger" onClick={confirmDelete} autoFocus>
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
          <div className="share-link-row">
            <input
              className="share-link-input"
              readOnly
              value={modal?.link ?? ""}
              aria-label="Ihuza ryo gusangiza"
              onFocus={(e) => e.currentTarget.select()}
            />
            <button type="button" className="btn-primary" onClick={copyShareLink}>
              {linkCopied ? (
                <>
                  <Check aria-hidden="true" /> Ryakoporowe
                </>
              ) : (
                "Koporora ihuza"
              )}
            </button>
          </div>
          <DialogFooter>
            <DialogClose asChild>
              <button type="button" className="btn-ghost">
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
          <div className="usage">
            <p className="usage-model">
              Model: <span className="usage-model-name">{usageModel}</span>
            </p>
            <table className="usage-table">
              <caption className="usage-caption">Iki kiganiro</caption>
              <tbody>
                <tr>
                  <th scope="row">Ibyoherejwe (injyana)</th>
                  <td>~{usageActive?.inputTokens ?? 0}</td>
                </tr>
                <tr>
                  <th scope="row">Ibyakiriwe (insubizo)</th>
                  <td>~{usageActive?.outputTokens ?? 0}</td>
                </tr>
                <tr className="usage-total-row">
                  <th scope="row">Igiteranyo</th>
                  <td>~{usageActive?.total ?? 0}</td>
                </tr>
              </tbody>
            </table>
            <table className="usage-table">
              <caption className="usage-caption">Ibiganiro byose</caption>
              <tbody>
                <tr>
                  <th scope="row">Ibyoherejwe (injyana)</th>
                  <td>~{usageTotal.inputTokens}</td>
                </tr>
                <tr>
                  <th scope="row">Ibyakiriwe (insubizo)</th>
                  <td>~{usageTotal.outputTokens}</td>
                </tr>
                <tr className="usage-total-row">
                  <th scope="row">Igiteranyo</th>
                  <td>~{usageTotal.total}</td>
                </tr>
              </tbody>
            </table>
            <a className="pricing-link" href={PRICING_URL} target="_blank" rel="noreferrer">
              Gereranya ibiciro bya OpenAI ({usageModel}) ↗
            </a>
          </div>
          <DialogFooter>
            <DialogClose asChild>
              <button type="button" className="btn-ghost">
                Funga
              </button>
            </DialogClose>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
