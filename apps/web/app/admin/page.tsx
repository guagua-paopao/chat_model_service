"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

type Identity = { display_name: string; tenant: { code: string }; permissions: string[] };
type User = { id: string; display_name: string; status: string; roles: string[]; groups: string[] };
type Group = { id: string; code: string; status: string; member_count: number };
type RagConfig = { id: string; version: number; status: string; prompt_version: string; checksum: string; evaluation_status: string };
type Quota = { requests_per_minute: number; concurrent_requests: number; daily_token_limit: number; monthly_cost_limit: string; currency: string };
type Usage = { requests: number; input_tokens: number; output_tokens: number; amount: string };
type Quality = { retrieval_runs: number; abstention_rate: number; citations: number; negative_feedback: number };
type Audit = { sequence_no: number; action: string; result: string; resource_type: string; occurred_at: string };
type Incident = { id: string; title: string; severity: string; status: string };
type Evaluation = { id: string; gate_result: string; dataset_version_id: string; candidate_config_ids: string[]; completed_at?: string };
type Release = { id: string; release_version: string; status: string; current_stage: string; artifact_checksum: string; uat_results: unknown[]; signoffs: unknown[]; rollout_events: unknown[] };
type Operations = {
  scope: string;
  production_slo_evidence: boolean;
  request_window: { requests: number; server_error_rate: number; latency_ms: { p95?: number } };
  tenant_signals: { failed_model_invocations: number; queued_or_running_ingestion_jobs: number; open_security_incidents: number };
};

async function read<T>(path: string): Promise<T> {
  const response = await fetch(`/api/qa/${path}`, { cache: "no-store", credentials: "same-origin" });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { code?: string; detail?: string };
    throw new Error(`${body.code ?? response.status}: ${body.detail ?? "请求失败"}`);
  }
  return (await response.json()) as T;
}

export default function GovernanceConsole() {
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [configs, setConfigs] = useState<RagConfig[]>([]);
  const [quota, setQuota] = useState<Quota | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [quality, setQuality] = useState<Quality | null>(null);
  const [audits, setAudits] = useState<Audit[]>([]);
  const [integrity, setIntegrity] = useState("checking");
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [evaluations, setEvaluations] = useState<Evaluation[]>([]);
  const [operations, setOperations] = useState<Operations | null>(null);
  const [releases, setReleases] = useState<Release[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      read<Identity>("me"),
      read<{ items: User[] }>("admin/users"),
      read<{ items: Group[] }>("admin/groups"),
      read<{ items: RagConfig[] }>("admin/rag-configs"),
      read<Quota>("admin/quota-policies/tenant"),
      read<Usage>("admin/usage-summary"),
      read<Quality>("admin/quality-summary"),
      read<{ items: Audit[] }>("admin/audit-logs?limit=20"),
      read<{ valid: boolean; checked_events: number }>("admin/audit-logs/integrity"),
      read<{ items: Incident[] }>("admin/security-incidents"),
      read<{ items: Evaluation[] }>("evaluations/runs?limit=10"),
      read<Operations>("admin/operations/snapshot"),
      read<{ items: Release[] }>("admin/releases?limit=10"),
    ])
      .then(([me, userData, groupData, configData, quotaData, usageData, qualityData, auditData, auditIntegrity, incidentData, evaluationData, operationsData, releaseData]) => {
        setIdentity(me);
        setUsers(userData.items);
        setGroups(groupData.items);
        setConfigs(configData.items);
        setQuota(quotaData);
        setUsage(usageData);
        setQuality(qualityData);
        setAudits(auditData.items);
        setIntegrity(auditIntegrity.valid ? `valid · ${auditIntegrity.checked_events} events` : "invalid");
        setIncidents(incidentData.items);
        setEvaluations(evaluationData.items);
        setOperations(operationsData);
        setReleases(releaseData.items);
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "加载失败"));
  }, []);

  return (
    <main className="admin-main">
      <section className="card admin-card">
        <p className="eyebrow">S7 · UAT, rollout and operations handover</p>
        <div className="admin-heading">
          <div><h1>企业问答治理与可靠性控制台</h1><p>只读展示安全摘要；本页的进程窗口不是生产 SLO 证据。</p></div>
          <Link className="login" href="/">返回问答</Link>
        </div>
        {error && <p className="warning">{error}</p>}
        {identity && <p className="statusline">{identity.display_name} · {identity.tenant.code}</p>}

        <section className="admin-grid">
          <article className="metric"><small>请求量（7 天）</small><strong>{usage?.requests ?? "—"}</strong><span>{usage ? `${usage.input_tokens + usage.output_tokens} tokens` : ""}</span></article>
          <article className="metric"><small>进程窗口 P95</small><strong>{operations?.request_window.latency_ms.p95 ?? "—"}</strong><span>ms · 仅本实例最近 5 分钟</span></article>
          <article className="metric"><small>评测门禁失败</small><strong>{evaluations.filter((item) => item.gate_result === "failed").length}</strong><span>最近 {evaluations.length} 次运行</span></article>
          <article className="metric"><small>审计完整性</small><strong>{integrity}</strong><span>tenant hash chain</span></article>
        </section>

        <section className="panel">
          <h2>S7 发布候选与灰度证据</h2>
          {releases.length === 0 && <p>尚无发布候选。</p>}
          {releases.map((item) => <p className="row" key={item.id}><strong>{item.release_version} · {item.status}</strong><span>{item.current_stage} · UAT {item.uat_results.length}/5 · signoff {item.signoffs.length}/5 · events {item.rollout_events.length} · {item.artifact_checksum.slice(0, 12)}</span></p>)}
        </section>

        <section className="panel">
          <h2>S6 版本化质量评测</h2>
          {evaluations.length === 0 && <p>尚无评测运行。</p>}
          {evaluations.map((item) => <p className="row" key={item.id}><strong>{item.gate_result} · {item.dataset_version_id}</strong><span>{item.candidate_config_ids.length} candidates · {item.id.slice(0, 12)}</span></p>)}
        </section>

        <section className="admin-columns">
          <section className="panel"><h2>运行信号</h2><p className="row"><strong>{operations?.request_window.requests ?? "—"} requests</strong><span>{operations ? `${(operations.request_window.server_error_rate * 100).toFixed(2)}% server errors · ${operations.tenant_signals.queued_or_running_ingestion_jobs} ingestion jobs` : ""}</span></p></section>
          <section className="panel"><h2>质量与事件</h2><p className="row"><strong>{quality?.retrieval_runs ?? "—"} RAG runs</strong><span>{quality ? `${(quality.abstention_rate * 100).toFixed(1)}% abstention · ${incidents.filter((item) => item.status !== "closed").length} open incidents` : ""}</span></p></section>
        </section>

        <section className="panel"><h2>身份与组</h2><div className="admin-columns"><div>{users.map((user) => <p className="row" key={user.id}><strong>{user.display_name}</strong><span>{user.status} · {user.roles.join(", ")}</span></p>)}</div><div>{groups.map((group) => <p className="row" key={group.id}><strong>{group.code}</strong><span>{group.status} · {group.member_count} members</span></p>)}</div></div></section>
        <section className="panel"><h2>RAG 配置版本</h2>{configs.map((config) => <p className="row" key={config.id}><strong>v{config.version} · {config.status}</strong><span>{config.prompt_version} · eval {config.evaluation_status} · {config.checksum.slice(0, 12)}</span></p>)}</section>
        <section className="admin-columns"><section className="panel"><h2>租户配额</h2><p className="row"><strong>{quota?.requests_per_minute ?? "—"} req/min</strong><span>{quota?.concurrent_requests ?? "—"} concurrent · {quota?.daily_token_limit ?? "—"} tokens/day · {quota?.monthly_cost_limit ?? "—"} {quota?.currency}</span></p></section><section className="panel"><h2>安全事件</h2>{incidents.length === 0 && <p>当前无事件。</p>}{incidents.map((incident) => <p className="row" key={incident.id}><strong>{incident.severity} · {incident.title}</strong><span>{incident.status}</span></p>)}</section></section>
        <section className="panel"><h2>最近治理审计</h2>{audits.map((audit) => <p className="row audit-row" key={audit.sequence_no}><strong>#{audit.sequence_no} · {audit.action}</strong><span>{audit.result} · {audit.resource_type} · {new Date(audit.occurred_at).toLocaleString("zh-CN")}</span></p>)}</section>
      </section>
    </main>
  );
}
