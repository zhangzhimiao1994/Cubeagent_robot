import { useMutation, useQuery } from "@tanstack/react-query";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  api,
  ApiError,
  formatApiError,
  type CognitiveContextBundle,
  type CognitionBelief,
  type CognitionEpisode,
  type CognitionExperience,
  type CognitionReflection,
  type CognitionRelationshipRecord,
  type CognitionWorldState,
} from "../api/client";
import { useAuth } from "../auth/AuthProvider";

type CognitionTab = "episodes" | "experiences" | "reflections" | "beliefs" | "relationship" | "world" | "preview";

const TABS: Array<{ id: CognitionTab; label: string }> = [
  { id: "episodes", label: "Episodes" },
  { id: "experiences", label: "Experiences" },
  { id: "reflections", label: "Reflections" },
  { id: "beliefs", label: "Beliefs" },
  { id: "relationship", label: "Relationship" },
  { id: "world", label: "World State" },
  { id: "preview", label: "Router Preview" },
];

const CONTEXT_GROUPS: Array<{ field: keyof CognitiveContextBundle; label: string }> = [
  { field: "core_constraints", label: "Core Constraints" },
  { field: "relationship_context", label: "Relationship Context" },
  { field: "world_context", label: "World Context" },
  { field: "experience_context", label: "Experience Context" },
  { field: "belief_context", label: "Belief Context" },
  { field: "skill_context", label: "Skill Context" },
];

const VALID_TABS = new Set<CognitionTab>(TABS.map((tab) => tab.id));

function confidence(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "未知";
  return `${Math.round(value * 100)}%`;
}

function compactDate(value: string | null | undefined) {
  if (!value) return "未记录";
  return value.replace("T", " ").replace(/Z$/, "");
}

function evidenceCount(value: { evidence_refs?: unknown[] }) {
  return value.evidence_refs?.length ?? 0;
}

function statusCount<T extends { status: string }>(items: T[], status: string) {
  return items.filter((item) => item.status === status).length;
}

function queryError(queries: Array<{ error: unknown; isError: boolean }>) {
  return queries.find((query) => query.isError)?.error ?? null;
}

export function CognitionPage() {
  const auth = useAuth();
  if (auth.loading || !auth.user) return null;
  if (!auth.hasPermission("cognition:read")) return <p role="alert">没有查看认知记录的权限</p>;
  const scope = `${auth.user.tenant_id}:${auth.user.user_id}`;
  return <ScopedCognitionPage key={scope} scope={scope} />;
}

function ScopedCognitionPage({ scope }: { scope: string }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<CognitionTab>(tabFromParam(searchParams.get("tab")));
  const [scene, setScene] = useState("voice_chat");
  const [currentRequest, setCurrentRequest] = useState("语音回复要短一点，并且保留关键动作。");
  const [limit, setLimit] = useState("8");
  const [preview, setPreview] = useState<CognitiveContextBundle | null>(null);

  const episodesQuery = useQuery({ queryKey: ["cognition", scope, "episodes"], queryFn: () => api.cognitionEpisodes(), gcTime: 0 });
  const experiencesQuery = useQuery({ queryKey: ["cognition", scope, "experiences"], queryFn: () => api.cognitionExperiences(), gcTime: 0 });
  const reflectionsQuery = useQuery({ queryKey: ["cognition", scope, "reflections"], queryFn: () => api.cognitionReflections(), gcTime: 0 });
  const beliefsQuery = useQuery({ queryKey: ["cognition", scope, "beliefs"], queryFn: () => api.cognitionBeliefs(), gcTime: 0 });
  const relationshipQuery = useQuery({ queryKey: ["cognition", scope, "relationship"], queryFn: () => api.cognitionRelationship(), gcTime: 0 });
  const worldQuery = useQuery({ queryKey: ["cognition", scope, "world-state"], queryFn: () => api.cognitionWorldState(), gcTime: 0 });

  const previewMutation = useMutation({
    gcTime: 0,
    mutationFn: () =>
      api.cognitionRouterPreview({
        scene: scene.trim(),
        current_request: currentRequest.trim(),
        limit: Number(limit) || 1,
      }),
    onSuccess: (bundle) => setPreview(bundle),
    onMutate: () => setPreview(null),
  });

  const episodes = episodesQuery.data ?? [];
  const experiences = experiencesQuery.data ?? [];
  const reflections = reflectionsQuery.data ?? [];
  const beliefs = beliefsQuery.data ?? [];
  const relationship = relationshipQuery.data?.[0] ?? null;
  const worldState = worldQuery.data ?? [];
  const failedLoad = queryError([episodesQuery, experiencesQuery, reflectionsQuery, beliefsQuery, relationshipQuery, worldQuery]);
  const loading = [episodesQuery, experiencesQuery, reflectionsQuery, beliefsQuery, relationshipQuery, worldQuery].some(
    (query) => query.isLoading,
  );
  const contradictedBeliefs = beliefs.filter((belief) => belief.status === "contradicted" || belief.contradictions.length > 0).length;
  const activeWorldItems = statusCount(worldState, "active");
  const candidateExperiences = statusCount(experiences, "candidate");
  const activeExperiences = statusCount(experiences, "active");
  const tabs = useMemo(() => TABS, []);
  const tabParam = searchParams.get("tab");

  useEffect(() => {
    setActiveTab(tabFromParam(tabParam));
  }, [tabParam]);

  function selectTab(tab: CognitionTab) {
    setActiveTab(tab);
    setSearchParams(tab === "experiences" ? {} : { tab });
  }

  function submitPreview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!scene.trim() || !currentRequest.trim()) return;
    previewMutation.mutate();
  }

  if (failedLoad) return <p role="alert">{formatApiError(failedLoad, "认知记录加载失败")}</p>;
  if (previewMutation.error instanceof ApiError && [401, 403].includes(previewMutation.error.status)) {
    return <p role="alert">{formatApiError(previewMutation.error, "没有查看认知记录的权限")}</p>;
  }

  return (
    <section data-testid="cognition-page">
      <p className="eyebrow">Cognitive layer</p>
      <h2>认知成长</h2>

      <section className="status-grid" aria-label="认知指标">
        <article className="status-card">
          <span>候选经验</span>
          <p>{candidateExperiences}</p>
        </article>
        <article className="status-card">
          <span>活跃经验</span>
          <p>{activeExperiences}</p>
        </article>
        <article className="status-card">
          <span>冲突信念</span>
          <p>{contradictedBeliefs}</p>
        </article>
        <article className="status-card">
          <span>活跃世界项</span>
          <p>{activeWorldItems}</p>
        </article>
      </section>

      {loading ? <p>正在加载认知记录...</p> : null}
      {failedLoad ? <p role="alert">{formatApiError(failedLoad, "认知记录加载失败")}</p> : null}

      <div className="mode-entry-tabs" role="tablist" aria-label="认知调试分区">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            className={activeTab === tab.id ? "mode-entry-active" : undefined}
            onClick={() => selectTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "episodes" ? <EpisodesTable episodes={episodes} /> : null}
      {activeTab === "experiences" ? <ExperiencesTable experiences={experiences} /> : null}
      {activeTab === "reflections" ? <ReflectionsTable reflections={reflections} /> : null}
      {activeTab === "beliefs" ? <BeliefsTable beliefs={beliefs} /> : null}
      {activeTab === "relationship" ? <RelationshipPanel relationship={relationship} /> : null}
      {activeTab === "world" ? <WorldStateTable worldState={worldState} /> : null}
      {activeTab === "preview" ? (
        <section className="resource-card" aria-label="Router Preview">
          <h3>Router Preview</h3>
          <form className="stacked-form" onSubmit={submitPreview}>
            <div className="inline-fields">
              <label>
                场景
                <input value={scene} onChange={(event) => setScene(event.currentTarget.value)} required />
              </label>
              <label>
                召回上限
                <input
                  inputMode="numeric"
                  max="8"
                  min="1"
                  type="number"
                  value={limit}
                  onChange={(event) => setLimit(event.currentTarget.value)}
                  required
                />
              </label>
            </div>
            <label>
              当前请求
              <textarea value={currentRequest} onChange={(event) => setCurrentRequest(event.currentTarget.value)} required />
            </label>
            <button type="submit" disabled={previewMutation.isPending || !scene.trim() || !currentRequest.trim()}>
              {previewMutation.isPending ? "预览中..." : "预览上下文"}
            </button>
          </form>
          {previewMutation.isError ? <p role="alert">{formatApiError(previewMutation.error, "Router Preview 失败")}</p> : null}
          {preview ? <RouterPreviewResult preview={preview} /> : null}
        </section>
      ) : null}
    </section>
  );
}

function tabFromParam(value: string | null): CognitionTab {
  return value && VALID_TABS.has(value as CognitionTab) ? (value as CognitionTab) : "experiences";
}

function EmptyRecord({ children }: { children: string }) {
  return (
    <article>
      <h3>{children}</h3>
    </article>
  );
}

function EpisodesTable({ episodes }: { episodes: CognitionEpisode[] }) {
  if (episodes.length === 0) return <EmptyRecord>还没有 Episode</EmptyRecord>;
  return (
    <section aria-label="Episodes">
      <h3>Episodes</h3>
      <div className="table-shell">
        <table>
          <thead>
            <tr>
              <th>来源</th>
              <th>摘要</th>
              <th>结果</th>
              <th>信号</th>
              <th>证据</th>
              <th>开始</th>
              <th>创建</th>
            </tr>
          </thead>
          <tbody>
            {episodes.map((episode) => (
              <tr key={episode.id}>
                <td>{episode.source}</td>
                <td>{episode.summary}</td>
                <td>{episode.outcome}</td>
                <td>{episode.signals.join(", ") || "无"}</td>
                <td>{evidenceCount(episode)}</td>
                <td>{compactDate(episode.started_at)}</td>
                <td>{compactDate(episode.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ExperiencesTable({ experiences }: { experiences: CognitionExperience[] }) {
  if (experiences.length === 0) return <EmptyRecord>还没有 Experience</EmptyRecord>;
  return (
    <section aria-label="Experiences">
      <h3>Experiences</h3>
      <div className="table-shell">
        <table>
          <thead>
            <tr>
              <th>类型</th>
              <th>经验</th>
              <th>适用场景</th>
              <th>建议动作</th>
              <th>置信度</th>
              <th>证据</th>
              <th>使用</th>
              <th>成功/失败</th>
              <th>状态</th>
              <th>最后验证</th>
              <th>更新</th>
            </tr>
          </thead>
          <tbody>
            {experiences.map((experience) => (
              <tr key={experience.id}>
                <td>{experience.kind}</td>
                <td>{experience.statement}</td>
                <td>{experience.applicability}</td>
                <td>{experience.recommended_action || "未记录"}</td>
                <td>{confidence(experience.confidence)}</td>
                <td>{evidenceCount(experience)}</td>
                <td>{experience.usage_count}</td>
                <td>
                  {experience.success_count}/{experience.failure_count}
                </td>
                <td>{experience.status}</td>
                <td>{compactDate(experience.last_verified_at)}</td>
                <td>{compactDate(experience.updated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ReflectionsTable({ reflections }: { reflections: CognitionReflection[] }) {
  if (reflections.length === 0) return <EmptyRecord>还没有 Reflection</EmptyRecord>;
  return (
    <section aria-label="Reflections">
      <h3>Reflections</h3>
      <div className="table-shell">
        <table>
          <thead>
            <tr>
              <th>类型</th>
              <th>触发</th>
              <th>发生了什么</th>
              <th>原因</th>
              <th>下次做法</th>
              <th>置信度</th>
              <th>证据</th>
              <th>状态</th>
              <th>创建</th>
            </tr>
          </thead>
          <tbody>
            {reflections.map((reflection) => (
              <tr key={reflection.id}>
                <td>{reflection.reflection_type}</td>
                <td>{reflection.trigger}</td>
                <td>{reflection.what_happened}</td>
                <td>{reflection.why_it_happened}</td>
                <td>{reflection.better_next_time}</td>
                <td>{confidence(reflection.confidence)}</td>
                <td>{evidenceCount(reflection)}</td>
                <td>{reflection.status}</td>
                <td>{compactDate(reflection.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function BeliefsTable({ beliefs }: { beliefs: CognitionBelief[] }) {
  if (beliefs.length === 0) return <EmptyRecord>还没有 Belief</EmptyRecord>;
  return (
    <section aria-label="Beliefs">
      <h3>Beliefs</h3>
      <div className="table-shell">
        <table>
          <thead>
            <tr>
              <th>主体</th>
              <th>判断</th>
              <th>对象</th>
              <th>范围</th>
              <th>置信度</th>
              <th>证据</th>
              <th>冲突</th>
              <th>状态</th>
              <th>最后验证</th>
              <th>更新</th>
            </tr>
          </thead>
          <tbody>
            {beliefs.map((belief) => (
              <tr key={belief.id}>
                <td>{belief.subject}</td>
                <td>{belief.predicate}</td>
                <td>{belief.object}</td>
                <td>{belief.scope}</td>
                <td>{confidence(belief.confidence)}</td>
                <td>{evidenceCount(belief)}</td>
                <td>{belief.contradictions.length}</td>
                <td>{belief.status}</td>
                <td>{compactDate(belief.last_verified_at)}</td>
                <td>{compactDate(belief.updated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function RelationshipPanel({ relationship }: { relationship: CognitionRelationshipRecord | null }) {
  if (!relationship) return <EmptyRecord>还没有 Relationship State</EmptyRecord>;
  return (
    <section className="resource-card" aria-label="Relationship">
      <h3>Relationship</h3>
      <dl className="detail-list">
        <div>
          <dt>熟悉度</dt>
          <dd>{confidence(relationship.familiarity)}</dd>
        </div>
        <div>
          <dt>信任</dt>
          <dd>{confidence(relationship.trust)}</dd>
        </div>
        <div>
          <dt>默契</dt>
          <dd>{confidence(relationship.rapport)}</dd>
        </div>
        <div>
          <dt>语气</dt>
          <dd>{relationship.preferred_tone}</dd>
        </div>
        <div>
          <dt>深度</dt>
          <dd>{relationship.preferred_depth}</dd>
        </div>
        <div>
          <dt>节奏</dt>
          <dd>{relationship.interaction_rhythm}</dd>
        </div>
        <div>
          <dt>证据</dt>
          <dd>{evidenceCount(relationship)}</dd>
        </div>
        <div>
          <dt>更新</dt>
          <dd>{compactDate(relationship.last_updated_at)}</dd>
        </div>
      </dl>
      <CompactList title="共同经历" items={relationship.shared_history} />
      <CompactList title="稳定偏好" items={relationship.stable_preferences} />
      <CompactList title="边界" items={relationship.boundaries} />
    </section>
  );
}

function WorldStateTable({ worldState }: { worldState: CognitionWorldState[] }) {
  if (worldState.length === 0) return <EmptyRecord>还没有 World State</EmptyRecord>;
  return (
    <section aria-label="World State">
      <h3>World State</h3>
      <div className="table-shell">
        <table>
          <thead>
            <tr>
              <th>类型</th>
              <th>名称</th>
              <th>状态描述</th>
              <th>生命周期</th>
              <th>参与者</th>
              <th>置信度</th>
              <th>证据</th>
              <th>最后验证</th>
              <th>更新</th>
            </tr>
          </thead>
          <tbody>
            {worldState.map((item) => (
              <tr key={item.id}>
                <td>{item.entity_type}</td>
                <td>{item.name}</td>
                <td>{item.state}</td>
                <td>{item.status}</td>
                <td>{item.participants.join(", ") || "未记录"}</td>
                <td>{confidence(item.confidence)}</td>
                <td>{evidenceCount(item)}</td>
                <td>{compactDate(item.last_verified_at)}</td>
                <td>{compactDate(item.updated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function RouterPreviewResult({ preview }: { preview: CognitiveContextBundle }) {
  return (
    <section aria-label="Router Preview 结果">
      <h3>Preview Result</h3>
      <div className="detail-grid">
        {CONTEXT_GROUPS.map((group) => (
          <article key={group.field}>
            <span className="eyebrow">{group.label}</span>
            <CompactList title={group.label} items={preview[group.field]} hideTitle />
          </article>
        ))}
      </div>
      <CompactList title="Reasons" items={preview.reasons} />
    </section>
  );
}

function CompactList({ hideTitle = false, items, title }: { hideTitle?: boolean; items: string[]; title: string }) {
  return (
    <section aria-label={title}>
      {hideTitle ? null : <h4>{title}</h4>}
      {items.length === 0 ? (
        <p className="field-help">无</p>
      ) : (
        <ul>
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
