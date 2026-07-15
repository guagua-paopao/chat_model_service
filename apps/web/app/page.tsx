"use client";

import { FormEvent, useEffect, useState } from "react";

type Health = { status: string; checks?: Record<string, string> };
type Identity = { display_name: string; tenant: { code: string }; roles: string[] };
type Model = { id: string; display_name: string; capabilities: string[] };
type StreamData = {
  message_id?: string;
  delta?: string;
  finish_reason?: string;
  code?: string;
  message?: string;
  input_tokens?: number;
  output_tokens?: number;
  amount?: string;
  currency?: string;
};

function csrfToken() {
  return document.cookie
    .split("; ")
    .find((entry) => entry.startsWith("qa_csrf="))
    ?.split("=", 2)[1];
}

export default function Home() {
  const [health, setHealth] = useState<Health>({ status: "checking" });
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [models, setModels] = useState<Model[]>([]);
  const [conversationId, setConversationId] = useState("");
  const [question, setQuestion] = useState("请用一句话介绍这个 S2 演示");
  const [answer, setAnswer] = useState("");
  const [assistantId, setAssistantId] = useState("");
  const [status, setStatus] = useState("idle");
  const [usage, setUsage] = useState("");

  useEffect(() => {
    fetch("/api/health", { cache: "no-store" })
      .then((response) => response.json())
      .then(setHealth)
      .catch(() => setHealth({ status: "unavailable" }));
    fetch("/api/qa/me", { cache: "no-store", credentials: "same-origin" }).then(
      async (response) => {
        if (response.ok) {
          setIdentity((await response.json()) as Identity);
          const modelResponse = await fetch("/api/qa/models", {
            cache: "no-store",
            credentials: "same-origin",
          });
          if (modelResponse.ok) {
            const body = (await modelResponse.json()) as { items: Model[] };
            setModels(body.items);
          }
        }
      },
    );
  }, []);

  async function createConversation() {
    const response = await fetch("/api/qa/conversations", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken() ?? "",
      },
      body: JSON.stringify({
        title: "S2 流式模型会话",
        channel: "web",
        knowledge_base_ids: [],
        metadata: { stage: "s2" },
      }),
    });
    const body = (await response.json()) as { id?: string; code?: string };
    if (!response.ok || !body.id) throw new Error(body.code ?? `HTTP_${response.status}`);
    setConversationId(body.id);
    return body.id;
  }

  function applyEvent(event: string, data: StreamData) {
    if (data.message_id) setAssistantId(data.message_id);
    if (event === "message.started") setStatus("streaming");
    if (event === "message.delta" && data.delta) setAnswer((current) => current + data.delta);
    if (event === "usage") {
      setUsage(
        `${data.input_tokens ?? 0} input / ${data.output_tokens ?? 0} output · ${data.amount ?? "0"} ${data.currency ?? ""}`,
      );
    }
    if (event === "message.completed") setStatus(data.finish_reason ?? "completed");
    if (event === "error") {
      setStatus("failed");
      setAnswer((current) => current || `${data.code ?? "MODEL_ERROR"}: ${data.message ?? "请求失败"}`);
    }
  }

  async function consumeStream(path: string, payload: object) {
    setAnswer("");
    setUsage("");
    setAssistantId("");
    setStatus("starting");
    const response = await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken() ?? "",
      },
      body: JSON.stringify(payload),
    });
    if (!response.ok || !response.body) {
      const problem = (await response.json()) as { code?: string; detail?: string };
      setStatus("failed");
      setAnswer(`${problem.code ?? response.status}: ${problem.detail ?? "请求失败"}`);
      return;
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() ?? "";
      for (const block of blocks) {
        const event = block
          .split("\n")
          .find((line) => line.startsWith("event: "))
          ?.slice(7);
        const dataLine = block
          .split("\n")
          .find((line) => line.startsWith("data: "))
          ?.slice(6);
        if (event && dataLine) applyEvent(event, JSON.parse(dataLine) as StreamData);
      }
      if (done) break;
    }
  }

  async function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const activeConversation = conversationId || (await createConversation());
      await consumeStream("/api/qa/chat/completions", {
        conversation_id: activeConversation,
        message: question,
        knowledge_base_ids: [],
        stream: true,
        model_policy: "balanced",
        response_mode: "general",
        client_context: { locale: "zh-CN" },
      });
    } catch (error) {
      setStatus("failed");
      setAnswer(error instanceof Error ? error.message : "请求失败");
    }
  }

  async function cancel() {
    if (!assistantId) return;
    const response = await fetch(`/api/qa/messages/${assistantId}/cancel`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRF-Token": csrfToken() ?? "" },
    });
    if (response.ok) setStatus("cancelling");
  }

  async function retry() {
    if (!assistantId) return;
    await consumeStream(`/api/qa/messages/${assistantId}/retry`, {
      stream: true,
      model_policy: "balanced",
    });
  }

  async function logout() {
    await fetch("/api/auth/logout", {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRF-Token": csrfToken() ?? "" },
    });
    setIdentity(null);
    setConversationId("");
    setAnswer("");
  }

  return (
    <main>
      <section className="card">
        <p className="eyebrow">S2 · Model Gateway / SSE / Usage</p>
        <h1>企业问答系统</h1>
        <p className="warning">通用模型回答，未使用企业知识；当前结果不得作为制度依据。</p>
        <div className="statusline">
          <span className={health.status === "ready" ? "dot ready" : "dot"} />
          API：{health.status} · 可用模型路由：{models.length}
        </div>
        {identity ? (
          <div className="session">
            <p>
              已登录：<strong>{identity.display_name}</strong> · {identity.tenant.code} ·{" "}
              {identity.roles.join(", ")}
            </p>
            <form className="chat-form" onSubmit={ask}>
              <textarea
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                maxLength={8000}
                aria-label="问题"
              />
              <div className="actions">
                <button type="submit" disabled={status === "streaming" || status === "starting"}>
                  流式提问
                </button>
                <button className="secondary" type="button" onClick={cancel} disabled={!assistantId}>
                  停止
                </button>
                <button className="secondary" type="button" onClick={retry} disabled={!assistantId}>
                  重试
                </button>
                <button className="ghost" type="button" onClick={() => void createConversation()}>
                  新会话
                </button>
              </div>
            </form>
            <article className="answer" aria-live="polite">
              <span className="answer-status">{status}</span>
              <p>{answer || "回答将在这里逐段出现。"}</p>
              {usage && <small>{usage}</small>}
            </article>
            <button className="ghost logout" type="button" onClick={logout}>
              退出
            </button>
          </div>
        ) : (
          <a className="login" href="/api/auth/login">
            使用开发 OIDC 登录
          </a>
        )}
      </section>
    </main>
  );
}
