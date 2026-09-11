import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  STATUS,
  applySseEvent,
  attachSources,
  beginTurn,
  canSend,
  chatRequestBody,
  completeIfStreaming,
  createThreadState,
  failHttp,
  failNetwork,
  getActive,
  isBusy,
  listedConversations,
  parseSseBuffer,
  startNewChat,
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
    assert.equal(getActive(state).title, "New chat");
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
