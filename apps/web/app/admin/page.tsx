"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

type Identity = { display_name: string; tenant: { code: string }; permissions: string[] };
type User = {
  id: string;
  display_name: string;
  subject: string;
  status: string;
  roles: string[];
  groups: string[];
  identity_synced_at?: string;
};
type Group = { id: string; code: string; status: string; member_count: number };
type RagConfig = {
  id: string;
  version: number;
  status: string;
  prompt_version: string;
  checksum: string;
  evaluation_status: string;
  approval_id?: string;
};
type Quota = {
  requests_per_minute: number;
  concurrent_requests: number;
  daily_token_limit: number;
  monthly_cost_limit: string;
  currency: string;
};
type Usage = { requests: number; input_tokens: number; output_tokens: number; amount: string };
type Quality = { retrieval_runs: number; abstention_rate: number; citations: number; negative_feedback: number };
type Audit = { sequence_no: number; action: string; result: string; resource_type: string; occurred_at: string };
type Incident = { id: string; title: string; severity: string; status: string };

async function read<T>(path: string): Promise<T> {
  const response = await fetch(`/api/qa/admin/${path}`, {
    cache: "no-store",
    credentials: "same-origin",
  });
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
  const [integrity, setIntegrity] = useState<string>("checking");
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      fetch("/api/qa/me", { cache: "no-store", credentials: "same-origin" }).then(async (r) => {
        if (!r.ok) throw new Error("AUTH_REQUIRED: 请先登录治理账号");
        return (await r.json()) as Identity;
      }),
      read<{ items: User[] }>("users"),
      read<{ items: Group[] }>("groups"),
      read<{ items: RagConfig[] }>("rag-configs"),
      read<Quota>("quota-policies/tenant"),
      read<Usage>("usage-summary"),
      read<Quality>("quality-summary"),
      read<{ items: Audit[] }>("audit-logs?limit=20"),
      read<{ valid: boolean; checked_events: number }>("audit-logs/integrity"),
      read<{ items: Incident[] }>("security-incidents"),
    ])
      .then(([me, userData, groupData, configData, quotaData, usageData, qualityData, auditData, auditIntegrity, incidentData]) => {
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
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "加载失败"));
  }, []);

  return (
    <main className="admin-main">
      <section className="card admin-card">
        <p className="eyebrow">S5 · Enterprise governance</p>
        <div className="admin-heading">
          <div>
            <h1>治理控制台</h1>
            <p>只展示安全摘要；写操作仍需 ETag、变更原因、审批号和独立权限。</p>
          </div>
          <Link className="login" href="/">返回问答</Link>
        </div>
        {error && <p className="warning">{error}</p>}
        {identity && <p className="statusline">{identity.display_name} · {identity.tenant.code}</p>}

        <section className="admin-grid">
          <article className="metric"><small>请求量（7 天）</small><strong>{usage?.requests ?? "—"}</strong><span>{usage ? `${usage.input_tokens + usage.output_tokens} tokens` : ""}</span></article>
          <article className="metric"><small>RAG 运行</small><strong>{quality?.retrieval_runs ?? "—"}</strong><span>{quality ? `${(quality.abstention_rate * 100).toFixed(1)}% abstention` : ""}</span></article>
          <article className="metric"><small>审计完整性</small><strong>{integrity}</strong><span>tenant hash chain</span></article>
          <article className="metric"><small>未关闭事件</small><strong>{incidents.filter((item) => item.status !== "closed").length}</strong><span>P0/P1 必须阻断 Gate</span></article>
        </section>

        <section className="panel">
          <h2>身份与组</h2>
          <div className="admin-columns">
            <div>{users.map((user) => <p className="row" key={user.id}><strong>{user.display_name}</strong><span>{user.status} · {user.roles.join(", ")} · {user.groups.join(", ")}</span></p>)}</div>
            <div>{groups.map((group) => <p className="row" key={group.id}><strong>{group.code}</strong><span>{group.status} · {group.member_count} members</span></p>)}</div>
          </div>
        </section>

        <section className="panel">
          <h2>RAG 配置版本</h2>
          {configs.map((config) => <p className="row" key={config.id}><strong>v{config.version} · {config.status}</strong><span>{config.prompt_version} · eval {config.evaluation_status} · {config.checksum.slice(0, 12)}</span></p>)}
        </section>

        <section className="admin-columns">
          <section className="panel">
            <h2>租户配额</h2>
            <p className="row"><strong>{quota?.requests_per_minute ?? "—"} req/min</strong><span>{quota?.concurrent_requests ?? "—"} concurrent · {quota?.daily_token_limit ?? "—"} tokens/day · {quota?.monthly_cost_limit ?? "—"} {quota?.currency}</span></p>
          </section>
          <section className="panel">
            <h2>安全事件</h2>
            {incidents.length === 0 && <p>当前无事件。</p>}
            {incidents.map((incident) => <p className="row" key={incident.id}><strong>{incident.severity} · {incident.title}</strong><span>{incident.status}</span></p>)}
          </section>
        </section>

        <section className="panel">
          <h2>最近治理审计</h2>
          {audits.map((audit) => <p className="row audit-row" key={audit.sequence_no}><strong>#{audit.sequence_no} · {audit.action}</strong><span>{audit.result} · {audit.resource_type} · {new Date(audit.occurred_at).toLocaleString("zh-CN")}</span></p>)}
        </section>
      </section>
    </main>
  );
}
