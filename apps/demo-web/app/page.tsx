"use client";

import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCircleQuestion,
  faComments,
  faFileLines,
  faHourglass,
  faLightbulb,
  faMessage,
  faNewspaper,
  faPaperPlane,
  faPenToSquare,
  faRectangleXmark,
} from "@fortawesome/free-regular-svg-icons";
import { faBars, faMagnifyingGlass } from "@fortawesome/free-solid-svg-icons";

import {
  CHAT_PATH,
  STATUS,
  applySseEvent,
  beginTurn,
  canSend,
  chatRequestBody,
  completeIfStreaming,
  createThreadState,
  failHttp,
  failNetwork,
  formatSourceDate,
  getActive,
  isBusy,
  listedConversations,
  parseSseBuffer,
  selectConversation,
  startNewChat,
  type ThreadState,
} from "../lib/chat";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function Composer({ busy, onSend }: { busy: boolean; onSend: (message: string) => boolean }) {
  const ref = useRef<HTMLTextAreaElement | null>(null);
  const [hasText, setHasText] = useState(false);

  function submit(e: FormEvent) {
    e.preventDefault();
    const message = ref.current?.value.trim() ?? "";
    if (!message || busy) return;
    if (!onSend(message)) return;
    if (ref.current) ref.current.value = "";
    setHasText(false);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!busy && ref.current?.value.trim()) {
        e.currentTarget.form?.requestSubmit();
      }
    }
  }

  return (
    <form className="composer" onSubmit={submit}>
      <div className="composer-pill">
        <textarea
          ref={ref}
          rows={1}
          maxLength={500}
          onInput={(e) => setHasText(Boolean(e.currentTarget.value.trim()))}
          onKeyDown={onKeyDown}
          placeholder="Urugero: Ni izihe nkuru ku mazi i Kigali?"
          aria-label="Ubutumwa"
        />
        <button type="submit" className="send" disabled={busy || !hasText} aria-label="Ohereza">
          <FontAwesomeIcon icon={faPaperPlane} aria-hidden="true" />
        </button>
      </div>
    </form>
  );
}

export default function Home() {
  const [state, setState] = useState<ThreadState>(() => createThreadState("demo-web"));
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const threadEndRef = useRef<HTMLDivElement | null>(null);

  const active = getActive(state);
  const messages = active?.messages ?? [];
  const empty = messages.length === 0;
  const busy = isBusy(state.phase);
  const prior = listedConversations(state);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ block: "end" });
  }, [messages, state.phase]);

  async function streamReply(conversationId: string, message: string) {
    try {
      const resp = await fetch(`${API_URL}${CHAT_PATH}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(chatRequestBody(conversationId, message)),
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
    } catch {
      setState((s) => failNetwork(s, conversationId));
    }
  }

  function send(message: string): boolean {
    if (!canSend(state.phase, message)) return false;
    const conversationId = state.activeId;
    let started = false;
    setState((s) => {
      if (!canSend(s.phase, message)) return s;
      started = true;
      return beginTurn(s, message);
    });
    if (!started) return false;
    void streamReply(conversationId, message);
    return true;
  }

  function onNewChat() {
    setState((s) => startNewChat(s));
    setSidebarOpen(false);
  }

  function onSelect(id: string) {
    setState((s) => selectConversation(s, id));
    setSidebarOpen(false);
  }

  const composer = <Composer busy={busy} onSend={send} />;

  return (
    <div className="chatgpt-shell">
      {sidebarOpen ? (
        <button type="button" className="backdrop" aria-label="Funga urutonde" onClick={() => setSidebarOpen(false)} />
      ) : null}

      <aside className={`sidebar${sidebarOpen ? " open" : ""}`}>
        <div className="sidebar-top">
          <span className="sidebar-brand">IGIHE</span>
          <button type="button" className="sidebar-close" aria-label="Funga" onClick={() => setSidebarOpen(false)}>
            <FontAwesomeIcon icon={faRectangleXmark} aria-hidden="true" />
          </button>
        </div>
        <button type="button" className="new-chat" onClick={onNewChat}>
          <FontAwesomeIcon icon={faPenToSquare} className="new-chat-icon" aria-hidden="true" />
          New chat
        </button>
        <nav className="conversation-list" aria-label="Ibiganiro">
          {prior.map((c) => (
            <button
              key={c.id}
              type="button"
              className={`conversation-item${c.id === state.activeId ? " active" : ""}`}
              onClick={() => onSelect(c.id)}
            >
              <FontAwesomeIcon icon={faMessage} className="conversation-icon" aria-hidden="true" />
              <span className="conversation-title">{c.title}</span>
            </button>
          ))}
        </nav>
      </aside>

      <section className="main-column">
        <header className="topbar">
          <button type="button" className="menu" aria-label="Ibiganiro" onClick={() => setSidebarOpen(true)}>
            <FontAwesomeIcon icon={faBars} aria-hidden="true" />
          </button>
          <span className="topbar-title">IGIHE News Assistant</span>
          <span className="topbar-status" aria-live="polite">
            {busy ? (
              <>
                <FontAwesomeIcon icon={faMagnifyingGlass} className="spin-soft" aria-hidden="true" />
                <span>{state.status}</span>
              </>
            ) : null}
          </span>
        </header>

        {empty ? (
          <div className="empty-state">
            <span className="empty-state-icon" aria-hidden="true">
              <FontAwesomeIcon icon={faComments} />
            </span>
            <h1 className="empty-state-greeting">Baza ikibazo mu Kinyarwanda.</h1>
            <p className="empty-state-hint">
              <FontAwesomeIcon icon={faLightbulb} aria-hidden="true" /> Ibisubizo bishingiye ku nkuru za IGIHE.
            </p>
            <div className="empty-composer">{composer}</div>
          </div>
        ) : (
          <>
            <div className="thread" role="log" aria-live="polite">
              {messages.map((m, i) => {
                const streamingThis = m.role === "assistant" && busy && i === messages.length - 1;
                return (
                  <article key={m.id} className={`message ${m.role}`}>
                    {m.role === "user" ? (
                      <div className="user-bubble">{m.content}</div>
                    ) : (
                      <div className={`assistant-turn${m.error ? " error" : ""}`}>
                        <div className="assistant-avatar" aria-hidden="true">
                          <FontAwesomeIcon icon={faNewspaper} />
                        </div>
                        <div className="assistant-body">
                          <div className="assistant-prose">
                            {m.content}
                            {streamingThis && !m.content ? (
                              <span className="thinking">
                                <FontAwesomeIcon icon={faHourglass} className="pulse-soft" aria-hidden="true" />{" "}
                                {STATUS.searching}
                              </span>
                            ) : null}
                            {streamingThis && m.content ? <span className="cursor" /> : null}
                          </div>
                          {m.sources.length > 0 ? (
                            <div className="sources-wrap">
                              <p className="sources-heading">
                                <FontAwesomeIcon icon={faFileLines} aria-hidden="true" /> Inkomoko
                              </p>
                              <ol className="sources">
                                {m.sources.map((s) => (
                                  <li key={`${m.id}-${s.n}`}>
                                    <a href={s.url} target="_blank" rel="noreferrer">
                                      {s.title}
                                    </a>{" "}
                                    ({formatSourceDate(s.published_at)})
                                  </li>
                                ))}
                              </ol>
                            </div>
                          ) : null}
                        </div>
                      </div>
                    )}
                  </article>
                );
              })}
              <div ref={threadEndRef} />
            </div>
            <div className="composer-dock">
              {composer}
              <p className="composer-footnote">
                <FontAwesomeIcon icon={faCircleQuestion} aria-hidden="true" /> Ibisubizo bishingiye ku nkuru za
                IGIHE.
              </p>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
