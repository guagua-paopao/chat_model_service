"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";

type Health = { status: string };
type Identity = {
  display_name: string;
  tenant: { code: string };
  roles: string[];
  permissions: string[];
};
type Model = { id: string; display_name: string };
type KnowledgeBase = { id: string; code: string; name: string; classification: string };
type UploadGrant = {
  document_id: string;
  version: { id: string; version_no: number };
  upload_url: string;
  upload_headers: Record<string, string>;
};
type IngestionJob = {
  id: string;
  status: string;
  stage: string;
  progress: number;
  error_code?: string;
  error_detail?: string;
};
type RetrievalHit = { document_title: string; score: number; content?: string };
type ResponseMode = "general" | "grounded_answer" | "search_only";
type Citation = {
  citation_id: string;
  ordinal: number;
  source_id: string;
  document_title: string;
  version: number;
  quote: string;
  page_from?: number;
  page_to?: number;
  relevance_score: number;
};
type CitationDetail = Citation & { access_checked_at: string; source_url: null };
type StreamData = Partial<Citation> & {
  message_id?: string;
  delta?: string;
  finish_reason?: string;
  abstention_reason?: string;
  retrieval_run_id?: string;
  status?: string;
  selected_sources?: number;
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

async function problem(response: Response) {
  const body = (await response.json().catch(() => ({}))) as { code?: string; detail?: string };
  return `${body.code ?? `HTTP_${response.status}`}: ${body.detail ?? "请求失败"}`;
}

function declaredMime(file: File) {
  const known = new Set([
    "text/plain",
    "text/markdown",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  ]);
  if (known.has(file.type)) return file.type;
  const extension = file.name.toLowerCase().split(".").pop();
  if (extension === "md") return "text/markdown";
  if (extension === "txt") return "text/plain";
  if (extension === "pdf") return "application/pdf";
  if (extension === "docx") {
    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  }
  throw new Error("仅支持 PDF、DOCX、TXT、MD 文件");
}

function outcomeLabel(status: string, abstentionReason: string) {
  if (status === "failed") return "系统失败";
  if (abstentionReason === "unsafe_query") return "安全策略拒绝";
  if (abstentionReason) return "证据不足，已拒答";
  if (status === "streaming") return "生成中";
  if (status === "starting") return "准备中";
  return status;
}

export default function Home() {
  const [health, setHealth] = useState<Health>({ status: "checking" });
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [models, setModels] = useState<Model[]>([]);
  const [conversationId, setConversationId] = useState("");
  const [question, setQuestion] = useState("差旅住宿费的报销标准是什么？");
  const [answer, setAnswer] = useState("");
  const [assistantId, setAssistantId] = useState("");
  const [status, setStatus] = useState("idle");
  const [abstentionReason, setAbstentionReason] = useState("");
  const [retrievalStatus, setRetrievalStatus] = useState("");
  const [usage, setUsage] = useState("");
  const [responseMode, setResponseMode] = useState<ResponseMode>("grounded_answer");
  const [citations, setCitations] = useState<Citation[]>([]);
  const [citationDetail, setCitationDetail] = useState<CitationDetail | null>(null);
  const [feedbackStatus, setFeedbackStatus] = useState("");
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedKb, setSelectedKb] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [job, setJob] = useState<IngestionJob | null>(null);
  const [ingestionStatus, setIngestionStatus] = useState("等待上传");
  const [searchQuery, setSearchQuery] = useState("差旅报销");
  const [searchHits, setSearchHits] = useState<RetrievalHit[]>([]);

  async function loadKnowledgeBases() {
    const response = await fetch("/api/qa/knowledge-bases", {
      cache: "no-store",
      credentials: "same-origin",
    });
    if (!response.ok) return;
    const body = (await response.json()) as { items: KnowledgeBase[] };
    setKnowledgeBases(body.items);
    setSelectedKb((current) => current || body.items[0]?.id || "");
  }

  useEffect(() => {
    fetch("/api/health", { cache: "no-store" })
      .then((response) => response.json())
      .then(setHealth)
      .catch(() => setHealth({ status: "unavailable" }));
    fetch("/api/qa/me", { cache: "no-store", credentials: "same-origin" }).then(
      async (response) => {
        if (!response.ok) return;
        setIdentity((await response.json()) as Identity);
        const modelResponse = await fetch("/api/qa/models", {
          cache: "no-store",
          credentials: "same-origin",
        });
        if (modelResponse.ok) {
          const body = (await modelResponse.json()) as { items: Model[] };
          setModels(body.items);
        }
        await loadKnowledgeBases();
      },
    );
  }, []);

  async function createConversation() {
    const response = await fetch("/api/qa/conversations", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() ?? "" },
      body: JSON.stringify({
        title: "S4 可溯源问答",
        channel: "web",
        knowledge_base_ids: responseMode === "general" || !selectedKb ? [] : [selectedKb],
        metadata: { stage: "s4", response_mode: responseMode },
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
    if (event === "retrieval.completed") {
      setRetrievalStatus(
        data.status === "abstained"
          ? `检索已结束：${data.abstention_reason ?? "证据不足"}`
          : `已完成授权检索，选中 ${data.selected_sources ?? 0} 条证据`,
      );
    }
    if (event === "message.delta" && data.delta) setAnswer((current) => current + data.delta);
    if (event === "citation" && data.citation_id) setCitations((current) => [...current, data as Citation]);
    if (event === "usage") {
      setUsage(
        `${data.input_tokens ?? 0} input / ${data.output_tokens ?? 0} output · ${data.amount ?? "0"} ${data.currency ?? ""}`,
      );
    }
    if (event === "message.completed") {
      setStatus(data.finish_reason ?? "completed");
      setAbstentionReason(data.abstention_reason ?? "");
    }
    if (event === "error") {
      setStatus("failed");
      setAnswer((current) => current || `${data.code ?? "SYSTEM_ERROR"}: ${data.message ?? "请求失败"}`);
    }
  }

  async function consumeStream(path: string, payload: object) {
    setAnswer("");
    setUsage("");
    setAssistantId("");
    setCitations([]);
    setCitationDetail(null);
    setFeedbackStatus("");
    setRetrievalStatus("");
    setAbstentionReason("");
    setStatus("starting");
    const response = await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() ?? "" },
      body: JSON.stringify(payload),
    });
    if (!response.ok || !response.body) {
      setStatus("failed");
      setAnswer(await problem(response));
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
        const event = block.split("\n").find((line) => line.startsWith("event: "))?.slice(7);
        const dataLine = block.split("\n").find((line) => line.startsWith("data: "))?.slice(6);
        if (event && dataLine) applyEvent(event, JSON.parse(dataLine) as StreamData);
      }
      if (done) break;
    }
  }

  async function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      if (responseMode !== "general" && !selectedKb) throw new Error("请先选择知识库");
      const activeConversation = conversationId || (await createConversation());
      await consumeStream("/api/qa/chat/completions", {
        conversation_id: activeConversation,
        message: question,
        knowledge_base_ids: responseMode === "general" ? [] : [selectedKb],
        stream: true,
        model_policy: "balanced",
        response_mode: responseMode,
        client_context: { locale: "zh-CN" },
      });
    } catch (error) {
      setStatus("failed");
      setAnswer(error instanceof Error ? error.message : "请求失败");
    }
  }

  async function showCitation(citation: Citation) {
    if (!assistantId) return;
    const response = await fetch(
      `/api/qa/messages/${assistantId}/citations/${citation.citation_id}`,
      { cache: "no-store", credentials: "same-origin" },
    );
    if (!response.ok) {
      setCitationDetail(null);
      setFeedbackStatus(await problem(response));
      return;
    }
    setCitationDetail((await response.json()) as CitationDetail);
  }

  async function sendFeedback(rating: -1 | 1) {
    if (!assistantId) return;
    const response = await fetch(`/api/qa/messages/${assistantId}/feedback`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() ?? "" },
      body: JSON.stringify({
        rating,
        reason_code: rating === 1 ? "helpful" : "factually_unsupported",
        comment: null,
      }),
    });
    setFeedbackStatus(response.ok ? "反馈已记录，并绑定本次检索与模型快照" : await problem(response));
  }

  async function createKnowledgeBase() {
    const response = await fetch("/api/qa/knowledge-bases", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() ?? "" },
      body: JSON.stringify({
        code: `demo_${Date.now().toString(36)}`,
        name: "S4 演示知识库",
        description: "仅存放合成、公开或已批准的非敏感演示资料",
        classification: "internal",
      }),
    });
    if (!response.ok) throw new Error(await problem(response));
    const body = (await response.json()) as KnowledgeBase;
    await loadKnowledgeBases();
    setSelectedKb(body.id);
  }

  async function pollJob(jobId: string) {
    for (let attempt = 0; attempt < 120; attempt += 1) {
      const response = await fetch(`/api/qa/ingestion-jobs/${jobId}`, {
        cache: "no-store",
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error(await problem(response));
      const current = (await response.json()) as IngestionJob;
      setJob(current);
      setIngestionStatus(`${current.stage} · ${current.progress}%`);
      if (["completed", "failed", "dead_letter"].includes(current.status)) return current;
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
    }
    throw new Error("轮询超时，请稍后通过任务 ID 查询");
  }

  async function uploadDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || !selectedKb) return;
    try {
      setJob(null);
      setIngestionStatus("计算 SHA-256");
      const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
      const sha256 = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
      const response = await fetch(`/api/qa/knowledge-bases/${selectedKb}/documents`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() ?? "" },
        body: JSON.stringify({
          title: file.name,
          filename: file.name,
          mime_type: declaredMime(file),
          size_bytes: file.size,
          sha256,
          classification: "internal",
          acl: [{ subject_type: "role", subject_id: "knowledge_admin", permission: "read" }],
          metadata: { source: "s4-web-demo" },
        }),
      });
      if (!response.ok) throw new Error(await problem(response));
      const upload = (await response.json()) as UploadGrant;
      setIngestionStatus("上传到隔离区");
      const uploadHeaders = new Headers(upload.upload_headers);
      const target = new URL(upload.upload_url, window.location.origin);
      const sameOrigin = target.origin === window.location.origin;
      if (sameOrigin) uploadHeaders.set("X-CSRF-Token", csrfToken() ?? "");
      const put = await fetch(target, {
        method: "PUT",
        headers: uploadHeaders,
        body: file,
        credentials: sameOrigin ? "same-origin" : "omit",
      });
      if (!put.ok) throw new Error(`UPLOAD_HTTP_${put.status}`);
      setIngestionStatus("创建异步处理任务");
      const complete = await fetch(`/api/qa/documents/${upload.document_id}/upload-complete`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() ?? "" },
        body: JSON.stringify({ version_id: upload.version.id, sha256 }),
      });
      if (!complete.ok) throw new Error(await problem(complete));
      const createdJob = (await complete.json()) as IngestionJob;
      setJob(createdJob);
      await pollJob(createdJob.id);
    } catch (error) {
      setIngestionStatus(error instanceof Error ? error.message : "上传失败");
    }
  }

  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedKb) return;
    const response = await fetch("/api/qa/retrieval/search", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() ?? "" },
      body: JSON.stringify({ query: searchQuery, kb_ids: [selectedKb], top_k: 5, include_content: true, filters: {} }),
    });
    if (!response.ok) {
      setIngestionStatus(await problem(response));
      return;
    }
    const body = (await response.json()) as { items: RetrievalHit[] };
    setSearchHits(body.items);
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
    await consumeStream(`/api/qa/messages/${assistantId}/retry`, { stream: true, model_policy: "balanced" });
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
        <p className="eyebrow">S4 · Grounded RAG / Hybrid retrieval / Citations</p>
        <h1>企业问答系统</h1>
        <p className="warning">
          知识问答只使用当前用户有权访问的已发布版本。证据不足时系统会明确拒答；引用详情在每次查看时重新鉴权。
        </p>
        <div className="statusline">
          <span className={health.status === "ready" ? "dot ready" : "dot"} />
          API：{health.status} · 可用模型路由：{models.length}
        </div>
        {identity ? (
          <div className="session">
            <p>已登录：<strong>{identity.display_name}</strong> · {identity.tenant.code} · {identity.roles.join(", ")}</p>
            {identity.permissions.includes("qa:admin:users:read") && (
              <Link className="login" href="/admin">打开 S5 治理控制台</Link>
            )}

            {identity.permissions.includes("qa:knowledge:write") && (
              <section className="panel">
                <h2>知识文档摄取</h2>
                <div className="actions">
                  <select value={selectedKb} onChange={(event) => { setSelectedKb(event.target.value); setConversationId(""); }}>
                    <option value="">选择知识库</option>
                    {knowledgeBases.map((kb) => (
                      <option key={kb.id} value={kb.id}>{kb.name} · {kb.classification}</option>
                    ))}
                  </select>
                  <button type="button" className="secondary" onClick={() => void createKnowledgeBase()}>新建演示知识库</button>
                </div>
                <form className="chat-form" onSubmit={uploadDocument}>
                  <input
                    type="file"
                    accept=".pdf,.docx,.txt,.md,text/plain,text/markdown,application/pdf"
                    onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                  />
                  <button type="submit" disabled={!file || !selectedKb}>上传并处理</button>
                </form>
                <div className="progress" aria-live="polite"><span style={{ width: `${job?.progress ?? 0}%` }} /></div>
                <p>{ingestionStatus}{job?.error_code ? ` · ${job.error_code}: ${job.error_detail}` : ""}</p>
                <form className="search-form" onSubmit={search}>
                  <input value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} />
                  <button type="submit" className="secondary" disabled={!selectedKb}>调试检索</button>
                </form>
                {searchHits.map((hit, index) => (
                  <article className="hit" key={`${hit.document_title}-${index}`}>
                    <strong>{hit.document_title}</strong> · {hit.score.toFixed(3)}
                    <p>{hit.content}</p>
                  </article>
                ))}
              </section>
            )}

            <section className="panel">
              <h2>可溯源问答</h2>
              <div className="mode-picker" role="group" aria-label="回答模式">
                {([
                  ["grounded_answer", "知识回答"],
                  ["search_only", "仅检索"],
                  ["general", "通用对话"],
                ] as const).map(([mode, label]) => (
                  <button
                    type="button"
                    key={mode}
                    className={responseMode === mode ? "mode active" : "mode"}
                    onClick={() => { setResponseMode(mode); setConversationId(""); }}
                  >{label}</button>
                ))}
              </div>
              <p className="mode-help">
                {responseMode === "grounded_answer" && "先检索授权证据，再生成并验证引用。"}
                {responseMode === "search_only" && "不调用大模型，仅返回排序后的授权证据。"}
                {responseMode === "general" && "不访问企业知识库，不提供企业引用。"}
              </p>
              <form className="chat-form" onSubmit={ask}>
                <textarea value={question} onChange={(event) => setQuestion(event.target.value)} maxLength={8000} aria-label="问题" />
                <div className="actions">
                  <button type="submit" disabled={status === "streaming" || status === "starting"}>流式提问</button>
                  <button className="secondary" type="button" onClick={cancel} disabled={!assistantId}>停止</button>
                  <button className="secondary" type="button" onClick={retry} disabled={!assistantId}>重试</button>
                  <button className="ghost" type="button" onClick={() => void createConversation()}>新会话</button>
                </div>
              </form>
              <article className={`answer ${abstentionReason ? "abstained" : ""}`} aria-live="polite">
                <span className={`answer-status ${status === "failed" ? "failed" : ""}`}>
                  {outcomeLabel(status, abstentionReason)}
                </span>
                {retrievalStatus && <p className="retrieval-state">{retrievalStatus}</p>}
                <p>{answer || "回答将在验证后显示在这里。"}</p>
                {usage && <small>{usage}</small>}
              </article>
              {citations.length > 0 && (
                <section className="citations" aria-label="引用证据">
                  <h3>授权证据</h3>
                  {citations.map((citation) => (
                    <button type="button" className="citation" key={citation.citation_id} onClick={() => void showCitation(citation)}>
                      <strong>[{citation.source_id}] {citation.document_title} · v{citation.version}</strong>
                      <span>{citation.quote}</span>
                      <small>相关度 {citation.relevance_score.toFixed(3)} · 点击重新鉴权查看</small>
                    </button>
                  ))}
                </section>
              )}
              {citationDetail && (
                <aside className="citation-detail">
                  <strong>受控证据预览：{citationDetail.document_title}</strong>
                  <p>{citationDetail.quote}</p>
                  <small>访问复核时间：{new Date(citationDetail.access_checked_at).toLocaleString("zh-CN")}</small>
                </aside>
              )}
              {assistantId && status !== "streaming" && status !== "starting" && status !== "failed" && (
                <div className="feedback">
                  <span>这次回答是否有帮助？</span>
                  <button type="button" className="secondary" onClick={() => void sendFeedback(1)}>有帮助</button>
                  <button type="button" className="secondary" onClick={() => void sendFeedback(-1)}>证据不足</button>
                  {feedbackStatus && <small>{feedbackStatus}</small>}
                </div>
              )}
            </section>
            <button className="ghost logout" type="button" onClick={logout}>退出</button>
          </div>
        ) : (
          <a className="login" href="/api/auth/login">使用开发 OIDC 登录</a>
        )}
      </section>
    </main>
  );
}
