"use client";

import { useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Source = {
  n: number;
  wp_id: number;
  title: string;
  published_at: string;
  url: string;
};

type ChatState = "idle" | "searching" | "streaming" | "done" | "error";

export default function Home() {
  const [question, setQuestion] = useState("");
  const [text, setText] = useState("");
  const [sources, setSources] = useState<Source[]>([]);
  const [state, setState] = useState<ChatState>("idle");
  const [status, setStatus] = useState("Baza ikibazo mu Kinyarwanda.");

  async function ask(e: React.FormEvent) {
    e.preventDefault();
    const message = question.trim();
    if (!message || state === "searching" || state === "streaming") return;
    setText("");
    setSources([]);
    setState("searching");
    setStatus("Ndashaka ibimenyetso...");
    try {
      const resp = await fetch(`${API_URL}/v1/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: "demo-web", message }),
      });
      if (resp.status === 413) {
        setState("error");
        setStatus("Igisubizo: ubutumwa burarenze urugero. Bugufi.");
        return;
      }
      if (resp.status === 429) {
        setState("error");
        setStatus("Serivisi iruzuye, ongera ugerageze nyuma.");
        return;
      }
      if (!resp.ok || !resp.body) {
        setState("error");
        setStatus("Habaye ikosa. Ongera ugerageze.");
        return;
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      let answer = "";
      setState("streaming");
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop() ?? "";
        for (const part of parts) {
          const lines = part.split("\n");
          const event = lines.find((l) => l.startsWith("event: "))?.slice(7);
          const dataRaw = lines.find((l) => l.startsWith("data: "))?.slice(6) ?? "{}";
          let data: Record<string, unknown> = {};
          try {
            data = JSON.parse(dataRaw) as Record<string, unknown>;
          } catch {
            continue;
          }
          if (event === "retrieval") {
            setStatus("Ndashaka ibimenyetso...");
          } else if (event === "token") {
            const chunk = String(data.text ?? "");
            answer += (answer ? " " : "") + chunk;
            setText(answer);
            setStatus("Ndasubiza...");
          } else if (event === "sources") {
            setSources(data as unknown as Source[]);
          } else if (event === "done") {
            setState("done");
            setStatus("Igisubizo kirangiye.");
          } else if (event === "error") {
            setState("error");
            setStatus(String(data.message ?? "Habaye ikosa."));
          }
        }
      }
      setState((s) => (s === "streaming" ? "done" : s));
    } catch {
      setState("error");
      setStatus("API ntibashije kuboneka. Menya ko serivisi iriho (port 8000).");
    }
  }

  return (
    <main>
      <h1>IGIHE News Assistant (demo)</h1>
      <p className="hint">Baza ikibazo mu Kinyarwanda. Ibisubizo bishingiye ku nkuru za IGIHE.</p>
      <form className="row" onSubmit={ask}>
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Urugero: Ni izihe nkuru ku mazi i Kigali?"
          maxLength={500}
        />
        <button type="submit" disabled={state === "searching" || state === "streaming"}>
          Ohereza
        </button>
      </form>
      <p className={`status${state === "error" ? " error" : ""}`}>{status}</p>
      {text && <div className="answer">{text}</div>}
      {sources.length > 0 && (
        <ol className="sources">
          {sources.map((s) => (
            <li key={s.n}>
              <a href={s.url} target="_blank" rel="noreferrer">
                {s.title}
              </a>{" "}
              ({s.published_at.slice(0, 10)})
            </li>
          ))}
        </ol>
      )}
    </main>
  );
}
