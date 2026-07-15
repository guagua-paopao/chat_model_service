"use client";

import { FormEvent, useEffect, useState } from "react";

type Health = { status: string; checks?: Record<string, string> };
type Identity = { display_name: string; tenant: { code: string }; roles: string[] };

function csrfToken() {
  return document.cookie
    .split("; ")
    .find((entry) => entry.startsWith("qa_csrf="))
    ?.split("=", 2)[1];
}

export default function Home() {
  const [health, setHealth] = useState<Health>({ status: "checking" });
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [result, setResult] = useState("");

  useEffect(() => {
    fetch("/api/health", { cache: "no-store" })
      .then((response) => response.json())
      .then(setHealth)
      .catch(() => setHealth({ status: "unavailable" }));
    fetch("/api/qa/me", { cache: "no-store", credentials: "same-origin" }).then(
      async (response) => {
        if (response.ok) setIdentity((await response.json()) as Identity);
      },
    );
  }, []);

  async function createConversation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const title = new FormData(event.currentTarget).get("title")?.toString() ?? "新对话";
    const response = await fetch("/api/qa/conversations", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken() ?? "",
      },
      body: JSON.stringify({
        title,
        channel: "web",
        knowledge_base_ids: [],
        metadata: {},
      }),
    });
    const body = await response.json();
    setResult(response.ok ? `已创建会话 ${body.id}` : `创建失败：${body.code ?? response.status}`);
  }

  async function logout() {
    await fetch("/api/auth/logout", {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRF-Token": csrfToken() ?? "" },
    });
    setIdentity(null);
    setResult("");
  }

  return (
    <main>
      <section className="card">
        <p className="eyebrow">S1 · 工程骨架 / 身份 / 租户</p>
        <h1>企业知识问答</h1>
        <p className="lede">
          当前纵切已提供健康检查、OIDC PKCE、可信身份上下文和租户隔离的会话接口。
          浏览器只通过 HttpOnly 会话 Cookie 调用同源 BFF。
        </p>
        <div className="status">
          <span className={health.status === "ready" ? "dot ready" : "dot"} />
          API 状态：{health.status}
        </div>
        {identity ? (
          <div className="session">
            <p>
              已登录：<strong>{identity.display_name}</strong> · {identity.tenant.code} ·{" "}
              {identity.roles.join(", ")}
            </p>
            <form onSubmit={createConversation}>
              <input
                name="title"
                defaultValue="S1 浏览器会话"
                maxLength={300}
                aria-label="会话标题"
              />
              <button type="submit">创建空会话</button>
            </form>
            <button className="secondary" type="button" onClick={logout}>
              退出
            </button>
            {result && <p className="result">{result}</p>}
          </div>
        ) : (
          <a className="login" href="/api/auth/login">
            使用开发 OIDC 登录
          </a>
        )}
        <p className="hint">
          API 教学也可使用 README 中的短期开发令牌验证 <code>/me</code> 和会话接口；
          不要把令牌写入 localStorage 或提交到 Git。
        </p>
      </section>
    </main>
  );
}
