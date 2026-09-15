import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  FALLBACK_MODEL,
  NEW_CHAT_TITLE,
  PRICING_URL,
  STATUS,
  STORAGE_KEY,
  SUGGESTION_COUNT,
  SUGGESTION_POOL,
  applySseEvent,
  attachSources,
  beginTurn,
  canSend,
  cancelTurn,
  chatRequestBody,
  completeIfStreaming,
  conversationUsage,
  countTokens,
  createThreadState,
  failHttp,
  failNetwork,
  getActive,
  groupConversations,
  isBusy,
  listedConversations,
  suggestionsFromData,
  decodeShare,
  deleteConversation,
  encodeShare,
  importSharedConversation,
  loadThreads,
  parseSseBuffer,
  pickSuggestions,
  saveThreads,
  shareLink,
  startNewChat,
  totalUsage,
  type ThreadState,
} from "../lib/chat.ts";

const SAMPLE_SSE = [
  "event: retrieval",
  'data: {"status": "searching"}',
  "",
  "event: token",
  'data: {"text":"Amazi meza"}',
  "",
  "event: token",
  'data: {"text":"i Kigali [1]."}',
  "",
  "event: sources",
  'data: [{"n":1,"wp_id":101,"title":"Amazi i Kigali","published_at":"2024-01-15T00:00:00Z","url":"https://igihe.com/amazi"}]',
  "",
  "event: done",
  'data: {"model":"fake-gen-v1","retrieval":"fake-hash"}',
  "",
  "",
].join("\n");

describe("parseSseBuffer", () => {
  it("yields token then sources then done from a representative SSE buffer", () => {
    const { events, remaining } = parseSseBuffer(SAMPLE_SSE);
    assert.equal(remaining, "");
    assert.deepEqual(
      events.map((e) => e.event),
      ["retrieval", "token", "token", "sources", "done"],
    );
    assert.equal((events[1]?.data as { text: string }).text, "Amazi meza");
    assert.equal((events[2]?.data as { text: string }).text, "i Kigali [1].");
    const sources = events[3]?.data as Array<{ title: string; url: string }>;
    assert.equal(sources[0]?.title, "Amazi i Kigali");
    assert.equal(sources[0]?.url, "https://igihe.com/amazi");
    assert.equal((events[4]?.data as { model: string }).model, "fake-gen-v1");
  });

  it("keeps an incomplete trailing chunk in remaining", () => {
    const { events, remaining } = parseSseBuffer('event: token\ndata: {"text":"Hi"}\n\nevent: tok');
    assert.equal(events.length, 1);
    assert.equal(events[0]?.event, "token");
    assert.equal(remaining, "event: tok");
  });
});

describe("thread updates", () => {
  it("appends a user turn then streams tokens into the last assistant message", () => {
    let state = createThreadState("c1");
    state = beginTurn(state, "Ni izihe nkuru ku mazi i Kigali?");
    const afterUser = getActive(state).messages;
    assert.equal(afterUser.length, 2);
    assert.equal(afterUser[0]?.role, "user");
    assert.equal(afterUser[0]?.content, "Ni izihe nkuru ku mazi i Kigali?");
    assert.equal(afterUser[1]?.role, "assistant");
    assert.equal(afterUser[1]?.content, "");
    assert.equal(state.phase, "searching");

    const { events } = parseSseBuffer(SAMPLE_SSE);
    for (const ev of events) {
      state = applySseEvent(state, ev);
    }
    const assistant = getActive(state).messages[1];
    assert.equal(assistant?.content, "Amazi meza i Kigali [1].");
    assert.equal(state.phase, "done");
    assert.equal(state.status, STATUS.done);
  });

  it("attaches sources to the assistant turn that produced them", () => {
    let state = createThreadState("c1");
    state = beginTurn(state, "Amazi i Kigali?");
    const { events } = parseSseBuffer(SAMPLE_SSE);
    for (const ev of events) {
      state = applySseEvent(state, ev);
    }
    const assistant = getActive(state).messages[1];
    assert.equal(assistant?.sources.length, 1);
    assert.equal(assistant?.sources[0]?.title, "Amazi i Kigali");
    assert.equal(assistant?.sources[0]?.url, "https://igihe.com/amazi");
    assert.equal(getActive(state).messages[0]?.sources.length, 0);
  });

  it("attaches server suggestions to the assistant turn that produced them", () => {
    let state = createThreadState("c1");
    state = beginTurn(state, "xyzzy?");
    state = applySseEvent(state, {
      event: "suggestions",
      data: { suggestions: ["Mbwira inkuru ziheruka."] },
    });
    const assistant = getActive(state).messages[1];
    assert.deepEqual(assistant?.suggestions, ["Mbwira inkuru ziheruka."]);
    assert.equal(getActive(state).messages[0]?.suggestions, undefined);
  });

  it("keeps the first turn intact after a second send", () => {
    let state = createThreadState("c1");
    state = beginTurn(state, "Ikibazo cya mbere");
    state = applySseEvent(state, { event: "token", data: { text: "Igisubizo cya mbere" } });
    state = applySseEvent(state, { event: "done", data: {} });
    const first = getActive(state).messages.map((m) => ({ role: m.role, content: m.content }));

    state = beginTurn(state, "Ikibazo cya kabiri");
    state = applySseEvent(state, { event: "token", data: { text: "Igisubizo cya kabiri" } });
    const msgs = getActive(state).messages;
    assert.equal(msgs.length, 4);
    assert.equal(msgs[0]?.content, first[0]?.content);
    assert.equal(msgs[1]?.content, first[1]?.content);
    assert.equal(msgs[2]?.content, "Ikibazo cya kabiri");
    assert.equal(msgs[3]?.content, "Igisubizo cya kabiri");
  });

  it("New chat yields an empty thread", () => {
    let state = createThreadState("c1");
    state = beginTurn(state, "Ikibazo");
    state = applySseEvent(state, { event: "token", data: { text: "Igisubizo" } });
    state = applySseEvent(state, { event: "done", data: {} });
    assert.equal(getActive(state).messages.length, 2);

    state = startNewChat(state, "c2");
    assert.equal(state.activeId, "c2");
    assert.equal(getActive(state).messages.length, 0);
    assert.equal(getActive(state).title, NEW_CHAT_TITLE);
    assert.equal(state.phase, "idle");
    assert.equal(listedConversations(state).length, 1);
    assert.equal(listedConversations(state)[0]?.id, "c1");
  });

  it("refuses a send while a reply is in flight", () => {
    assert.equal(canSend("idle", "hello"), true);
    assert.equal(canSend("done", "hello"), true);
    assert.equal(canSend("error", "hello"), true);
    assert.equal(canSend("searching", "hello"), false);
    assert.equal(canSend("streaming", "hello"), false);
    assert.equal(canSend("idle", "   "), false);
    assert.equal(isBusy("streaming"), true);

    let state = createThreadState("c1");
    state = beginTurn(state, "Ikibazo");
    const snapshot = getActive(state).messages.length;
    const blocked = beginTurn(state, "Ikibazo cy'ubusa");
    assert.equal(getActive(blocked).messages.length, snapshot);
    assert.equal(getActive(blocked).messages[0]?.content, "Ikibazo");
  });

  it("attachSources is a no-op on a user-only thread and maps HTTP/network errors onto the assistant turn", () => {
    let state = createThreadState("c1");
    state = attachSources(state, [{ n: 1, wp_id: 1, title: "x", published_at: "2024-01-01", url: "https://x" }]);
    assert.equal(getActive(state).messages.length, 0);

    state = beginTurn(state, "Long message");
    state = failHttp(state, 413);
    assert.equal(state.phase, "error");
    assert.equal(getActive(state).messages[1]?.content, STATUS.http413);
    assert.equal(getActive(state).messages[1]?.error, true);

    state = createThreadState("c2");
    state = beginTurn(state, "Rate");
    state = failHttp(state, 429);
    assert.equal(getActive(state).messages[1]?.content, STATUS.http429);

    state = createThreadState("c3");
    state = beginTurn(state, "Down");
    state = failNetwork(state);
    assert.equal(getActive(state).messages[1]?.content, STATUS.networkError);

    state = createThreadState("c4");
    state = beginTurn(state, "Other");
    state = failHttp(state, 500);
    assert.equal(getActive(state).messages[1]?.content, STATUS.genericError);
  });

  it("completeIfStreaming marks a hanging stream done", () => {
    let state = createThreadState("c1");
    state = beginTurn(state, "Q");
    state = applySseEvent(state, { event: "token", data: { text: "A" } });
    assert.equal(state.phase, "streaming");
    state = completeIfStreaming(state);
    assert.equal(state.phase, "done");
  });

  it("builds the /v1/chat POST body with session_id and message", () => {
    const body = chatRequestBody("demo-web", "Ni izihe nkuru ku mazi i Kigali?");
    assert.deepEqual(body, {
      session_id: "demo-web",
      message: "Ni izihe nkuru ku mazi i Kigali?",
    });
  });
});

describe("suggestionsFromData", () => {
  it("keeps distinct non-empty prompts and caps the list", () => {
    assert.deepEqual(
      suggestionsFromData({ suggestions: ["Mbwira inkuru ziheruka.", "  ", 7, "Mbwira inkuru ziheruka."] }),
      ["Mbwira inkuru ziheruka."],
    );
  });

  it("returns nothing for missing or malformed payloads", () => {
    assert.deepEqual(suggestionsFromData({}), []);
    assert.deepEqual(suggestionsFromData({ suggestions: "Mbwira" }), []);
    assert.deepEqual(suggestionsFromData(null), []);
  });

  it("decodes HTML entities carried by headlines", () => {
    assert.deepEqual(
      suggestionsFromData({ suggestions: ["Ibiciro bya&#8217;lisansi"] }),
      ["Ibiciro bya’lisansi"],
    );
  });
});

describe("cancelTurn", () => {
  it("keeps streamed text and finishes the turn", () => {
    let state = beginTurn(createThreadState("t"), "Kagame?");
    state = applySseEvent(state, { event: "token", data: { text: "Yavuze [1]." } });
    state = cancelTurn(state);
    assert.equal(state.phase, "done");
    const last = getActive(state).messages.at(-1);
    assert.equal(last?.content, "Yavuze [1].");
    assert.equal(last?.muted, undefined);
  });

  it("marks an empty reply as cancelled", () => {
    let state = beginTurn(createThreadState("t"), "Kagame?");
    state = cancelTurn(state);
    const last = getActive(state).messages.at(-1);
    assert.equal(last?.content, STATUS.cancelled);
    assert.equal(last?.muted, true);
    assert.equal(isBusy(state.phase), false);
  });

  it("is a no-op when idle", () => {
    const state = createThreadState("t");
    assert.equal(cancelTurn(state), state);
  });
});

describe("groupConversations", () => {
  it("buckets by day relative to now and drops empty buckets", () => {
    const now = new Date(2026, 8, 14, 12).getTime();
    const day = 24 * 60 * 60 * 1000;
    const mk = (id: string, createdAt: number) => ({ id, title: id, messages: [], createdAt });
    const groups = groupConversations(
      [mk("today", now - 1000), mk("yesterday", now - day), mk("week", now - 5 * day), mk("old", now - 30 * day)],
      now,
    );
    assert.deepEqual(
      groups.map((g) => [g.label, g.items.map((c) => c.id)]),
      [
        ["Uyu munsi", ["today"]],
        ["Ejo hashize", ["yesterday"]],
        ["Iminsi 7 ishize", ["week"]],
        ["Mbere y'aho", ["old"]],
      ],
    );
    assert.deepEqual(groupConversations([], now), []);
  });
});

describe("pickSuggestions", () => {
  it("returns distinct pool members, default count", () => {
    const picked = pickSuggestions();
    assert.equal(picked.length, SUGGESTION_COUNT);
    assert.equal(new Set(picked).size, picked.length);
    for (const q of picked) assert.ok(SUGGESTION_POOL.includes(q));
  });

  it("is deterministic with a stubbed rand", () => {
    const zeros = pickSuggestions(3, () => 0);
    assert.deepEqual(zeros, pickSuggestions(3, () => 0));
    assert.equal(new Set(zeros).size, 3);
  });

  it("clamps counts outside the pool range", () => {
    assert.deepEqual(pickSuggestions(0), []);
    assert.equal(pickSuggestions(99).length, SUGGESTION_POOL.length);
  });
});

describe("thread persistence", () => {
  function memStore() {
    const map = new Map<string, string>();
    return {
      getItem: (k: string) => map.get(k) ?? null,
      setItem: (k: string, v: string) => void map.set(k, v),
    };
  }

  function twoChatState(): ThreadState {
    let s = createThreadState("a");
    s = beginTurn(s, "hi");
    return startNewChat(s, "b");
  }

  it("round-trips conversations and the active id", () => {
    const store = memStore();
    const state = twoChatState();
    saveThreads(state, store);
    assert.ok(store.getItem(STORAGE_KEY)?.includes('"v":1'));
    const loaded = loadThreads(store);
    assert.deepEqual(
      loaded?.conversations.map((c) => c.id),
      ["b", "a"],
    );
    assert.equal(loaded?.activeId, "b");
  });

  it("resets a stranded streaming phase on load", () => {
    const store = memStore();
    const state = twoChatState();
    saveThreads({ ...state, phase: "streaming" }, store);
    assert.equal(loadThreads(store)?.phase, "idle");
  });

  it("returns null for missing, corrupt, or shapeless payloads", () => {
    assert.equal(loadThreads(memStore()), null);
    assert.equal(loadThreads(null), null);
    const bad = memStore();
    bad.setItem(STORAGE_KEY, "not-json{{{");
    assert.equal(loadThreads(bad), null);
    const shapeless = memStore();
    shapeless.setItem(STORAGE_KEY, JSON.stringify({ v: 1, conversations: [{ nope: true }] }));
    assert.equal(loadThreads(shapeless), null);
  });

  it("save is a no-op without storage", () => {
    saveThreads(createThreadState("a"), null);
  });
});

describe("deleteConversation", () => {
  function threeChatState(): ThreadState {
    let s = createThreadState("a");
    s = beginTurn(s, "one");
    s = startNewChat(s, "b");
    s = beginTurn(s, "two");
    return startNewChat(s, "c");
  }

  it("removes a non-active chat and keeps the active one", () => {
    const next = deleteConversation(threeChatState(), "b");
    assert.deepEqual(next.conversations.map((c) => c.id), ["c", "a"]);
    assert.equal(next.activeId, "c");
  });

  it("moves to the newest remaining chat when the active one is deleted", () => {
    const next = deleteConversation(threeChatState(), "c");
    assert.deepEqual(next.conversations.map((c) => c.id), ["b", "a"]);
    assert.equal(next.activeId, "b");
    assert.equal(next.phase, "idle");
  });

  it("starts a fresh chat when the last one is deleted", () => {
    const next = deleteConversation(createThreadState("only"), "only");
    assert.equal(next.conversations.length, 1);
    assert.equal(next.activeId, next.conversations[0].id);
  });

  it("ignores unknown ids", () => {
    const state = threeChatState();
    assert.equal(deleteConversation(state, "nope"), state);
  });
});

describe("share links", () => {
  function sharedState(): ThreadState {
    const s = createThreadState("a");
    return {
      ...s,
      conversations: [
        {
          id: "a",
          title: "Amazi",
          createdAt: 1,
          messages: [
            { id: "m1", role: "user", content: "Amazi?", sources: [] },
            {
              id: "m2",
              role: "assistant",
              content: "Yego [1].",
              sources: [{ n: 1, wp_id: 101, title: "T", published_at: "2024-01-01", url: "https://x" }],
            },
          ],
        },
      ],
    };
  }

  it("round-trips title, messages, and sources with fresh ids", () => {
    const conv = sharedState().conversations[0];
    const back = decodeShare(encodeShare(conv));
    assert.equal(back?.title, "Amazi");
    assert.deepEqual(
      back?.messages.map((m) => [m.role, m.content]),
      [
        ["user", "Amazi?"],
        ["assistant", "Yego [1]."],
      ],
    );
    assert.equal(back?.messages[1].sources[0].wp_id, 101);
    assert.notEqual(back?.id, conv.id);
    const link = shareLink(conv, "https://demo.test/");
    assert.ok(link.startsWith("https://demo.test/#s="));
    assert.deepEqual(decodeShare(link.split("#s=")[1])?.title, "Amazi");
  });

  it("rejects garbage and wrong-shaped payloads", () => {
    assert.equal(decodeShare("!!!not-base64!!!"), null);
    assert.equal(decodeShare("e30"), null); // "{}"
  });

  it("imports a shared conversation as active", () => {
    const state = createThreadState("mine");
    const conv = decodeShare(encodeShare(sharedState().conversations[0]));
    assert.ok(conv);
    const next = importSharedConversation(state, conv!);
    assert.equal(next.activeId, conv!.id);
    assert.equal(next.conversations.length, 2);
  });
});

describe("token usage", () => {
  it("estimates tokens at ~4 chars, empty as zero", () => {
    assert.equal(countTokens(""), 0);
    assert.equal(countTokens("   "), 0);
    assert.equal(countTokens("hi"), 1);
    assert.equal(countTokens("12345678"), 2);
    assert.ok(PRICING_URL.startsWith("https://openai.com/"));
    assert.equal(FALLBACK_MODEL, "fake-gen-v1");
  });

  it("accrues input on send and output on streamed tokens, stamps model on done", () => {
    let state = createThreadState("c1");
    const question = "Ni izihe nkuru ku mazi i Kigali?";
    state = beginTurn(state, question);
    assert.equal(getActive(state).inputTokens, countTokens(question));

    state = applySseEvent(state, { event: "token", data: { text: "Amazi meza" } });
    state = applySseEvent(state, { event: "token", data: { text: "i Kigali [1]." } });
    assert.equal(
      getActive(state).outputTokens,
      countTokens("Amazi meza") + countTokens("i Kigali [1]."),
    );

    state = applySseEvent(state, { event: "done", data: { model: "gpt-xyz", retrieval: "fake-hash" } });
    const usage = conversationUsage(getActive(state));
    assert.equal(usage.model, "gpt-xyz");
    assert.equal(usage.total, usage.inputTokens + usage.outputTokens);
  });

  it("keeps prior model when done carries none, and totals across chats", () => {
    let state = createThreadState("a");
    state = beginTurn(state, "one");
    state = applySseEvent(state, { event: "token", data: { text: "uno" } });
    state = applySseEvent(state, { event: "done", data: { model: "m1", retrieval: "r" } });
    state = startNewChat(state, "b");
    state = beginTurn(state, "two");
    state = applySseEvent(state, { event: "token", data: { text: "dos" } });
    state = applySseEvent(state, { event: "done", data: {} });
    const total = totalUsage(state);
    assert.equal(total.inputTokens, countTokens("one") + countTokens("two"));
    assert.equal(total.outputTokens, countTokens("uno") + countTokens("dos"));
    assert.equal(total.total, total.inputTokens + total.outputTokens);
  });

  it("reads legacy conversations without usage fields as zero and round-trips usage", () => {
    const legacy = { id: "old", title: "old", messages: [], createdAt: 1 };
    assert.deepEqual(conversationUsage(legacy), {
      inputTokens: 0,
      outputTokens: 0,
      total: 0,
      model: undefined,
    });

    const map = new Map<string, string>();
    const store = {
      getItem: (k: string) => map.get(k) ?? null,
      setItem: (k: string, v: string) => void map.set(k, v),
    };
    let state = createThreadState("a");
    state = beginTurn(state, "hi there");
    state = applySseEvent(state, { event: "token", data: { text: "hello back" } });
    state = applySseEvent(state, { event: "done", data: { model: "m9", retrieval: "r" } });
    saveThreads(state, store);
    const loaded = loadThreads(store);
    assert.equal(conversationUsage(loaded!.conversations[0]).total, totalUsage(state).total);
    assert.equal(loaded!.conversations[0].model, "m9");
  });
});
