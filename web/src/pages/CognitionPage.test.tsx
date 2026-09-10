import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TestApp } from "../app/router";

const principal = {
  user_id: "11111111-1111-4111-8111-111111111111",
  tenant_id: "33333333-3333-4333-8333-333333333333",
  role: "super_admin",
};

function jsonResponse(payload: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

describe("CognitionPage", () => {
  const requests: Array<{ body: unknown; method: string; path: string }> = [];

  beforeEach(() => {
    requests.length = 0;
    window.sessionStorage.setItem("agent_hub_access_token", "owner-token");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        const method = init?.method ?? "GET";
        if (init?.body && typeof init.body === "string") {
          requests.push({ path, method, body: JSON.parse(init.body) });
        } else {
          requests.push({ path, method, body: null });
        }
        if (path === "/api/v1/auth/me") return jsonResponse(principal);
        if (path === "/api/v1/admin/cognition/episodes") {
          return jsonResponse([
            {
              id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
              tenant_id: principal.tenant_id,
              user_id: principal.user_id,
              source: "voice",
              conversation_id: "voice-session-1",
              run_id: null,
              started_at: "2026-09-10T08:00:00Z",
              ended_at: "2026-09-10T08:00:12Z",
              summary: "User corrected the voice robot to answer more briefly.",
              signals: ["user_corrected"],
              outcome: "failure",
              feedback: "太啰嗦",
              evidence_refs: [{ kind: "conversation", ref_id: "voice-session-1", summary: "voice correction" }],
              privacy_level: "normal",
              created_at: "2026-09-10T08:00:30Z",
            },
          ]);
        }
        if (path === "/api/v1/admin/cognition/experiences") {
          return jsonResponse([
            {
              id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
              tenant_id: principal.tenant_id,
              user_id: principal.user_id,
              kind: "voice_interaction",
              statement: "Use shorter voice replies.",
              applicability: "Wake-word voice chat with the owner.",
              recommended_action: "Answer with one concrete step first.",
              avoid_action: "Do not read long debug explanations aloud.",
              confidence: 0.82,
              evidence_refs: [{ kind: "conversation", ref_id: "voice-session-1", summary: "owner correction" }],
              contradictions: [],
              usage_count: 3,
              success_count: 2,
              failure_count: 1,
              last_used_at: "2026-09-10T08:10:00Z",
              last_verified_at: "2026-09-10T08:10:00Z",
              version: 2,
              status: "active",
              created_at: "2026-09-10T08:01:00Z",
              updated_at: "2026-09-10T08:11:00Z",
            },
          ]);
        }
        if (path === "/api/v1/admin/cognition/reflections") {
          return jsonResponse([
            {
              id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
              episode_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
              reflection_type: "counterfactual",
              trigger: "user_corrected",
              what_happened: "The robot answered too verbosely.",
              why_it_happened: "Debug detail was routed into spoken output.",
              better_next_time: "Keep voice replies short and move diagnostics to the web console.",
              candidate_experience_ids: ["bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"],
              candidate_belief_updates: [],
              candidate_skill_updates: [],
              confidence: 0.76,
              requires_approval: false,
              evidence_refs: [{ kind: "conversation", ref_id: "voice-session-1", summary: "voice correction" }],
              status: "candidate",
              version: 1,
              created_at: "2026-09-10T08:02:00Z",
            },
          ]);
        }
        if (path === "/api/v1/admin/cognition/beliefs") {
          return jsonResponse([
            {
              id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
              tenant_id: principal.tenant_id,
              user_id: principal.user_id,
              subject: "owner",
              predicate: "prefers",
              object: "concise voice answers",
              scope: "user",
              confidence: 0.7,
              evidence_refs: [{ kind: "conversation", ref_id: "voice-session-1", summary: "owner correction" }],
              contradictions: [],
              last_verified_at: "2026-09-10T08:10:00Z",
              verification_count: 2,
              status: "active",
              version: 1,
              created_at: "2026-09-10T08:02:00Z",
              updated_at: "2026-09-10T08:10:00Z",
            },
          ]);
        }
        if (path === "/api/v1/admin/cognition/relationship") {
          return jsonResponse([
            {
              tenant_id: principal.tenant_id,
              user_id: principal.user_id,
              familiarity: 0.34,
              trust: 0.62,
              rapport: 0.58,
              preferred_tone: "direct",
              preferred_depth: "concise",
              interaction_rhythm: "user_led",
              shared_history: ["Built a voice robot cognitive layer together."],
              stable_preferences: ["Keep important memory sparse."],
              recent_changes: ["Added cognitive debug endpoints."],
              boundaries: ["Do not auto-modify SOUL from reflection."],
              confidence: 0.68,
              status: "active",
              version: 1,
              evidence_refs: [{ kind: "project", ref_id: "task-9", summary: "cognitive API" }],
              last_updated_at: "2026-09-10T08:12:00Z",
            },
          ]);
        }
        if (path === "/api/v1/admin/cognition/world-state") {
          return jsonResponse([
            {
              id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
              tenant_id: principal.tenant_id,
              user_id: principal.user_id,
              entity_type: "project",
              name: "voice agent raspberry pi bridge",
              state: "server brain, raspberry pi playback tool",
              status: "active",
              starts_at: null,
              due_at: null,
              ended_at: null,
              participants: ["owner", "agent"],
              evidence_refs: [{ kind: "project", ref_id: "voice-agent", summary: "architecture decision" }],
              confidence: 0.9,
              version: 1,
              last_verified_at: "2026-09-10T08:10:00Z",
              created_at: "2026-09-10T08:02:00Z",
              updated_at: "2026-09-10T08:10:00Z",
            },
          ]);
        }
        if (path === "/api/v1/admin/cognition/router-preview" && method === "POST") {
          return jsonResponse({
            core_constraints: ["Do not auto-modify SOUL from reflection."],
            relationship_context: ["Owner prefers direct technical updates."],
            world_context: ["Raspberry Pi is playback only."],
            experience_context: ["Use shorter voice replies."],
            belief_context: ["Owner prefers concise voice answers."],
            skill_context: ["Use Hermes learning review before changing behavior."],
            reasons: ["Matched voice scene", "High-confidence owner preference"],
          });
        }
        return jsonResponse({ error: { code: "not_found", message: "not found" } }, { status: 404 });
      }),
    );
  });

  afterEach(() => {
    window.sessionStorage.clear();
    vi.unstubAllGlobals();
  });

  it("loads cognition page and renders sparse learning records", async () => {
    render(<TestApp initialPath="/cognition" />);

    expect(await screen.findByRole("heading", { name: "认知成长" })).not.toBeNull();
    expect(await screen.findByText("Use shorter voice replies.")).not.toBeNull();
    expect(screen.getByText("候选经验")).not.toBeNull();
    expect(screen.getByText("活跃世界项")).not.toBeNull();
    expect(requests.some((request) => request.path === "/api/v1/admin/cognition/experiences")).toBe(true);
    expect(requests.some((request) => request.path === "/api/v1/admin/cognition/world-state")).toBe(true);
  });

  it("shows router preview context groups and reasons after submit", async () => {
    const user = userEvent.setup();
    render(<TestApp initialPath="/cognition" />);

    await screen.findByRole("heading", { name: "认知成长" });
    await user.click(screen.getByRole("tab", { name: "Router Preview" }));
    await user.clear(screen.getByLabelText("场景"));
    await user.type(screen.getByLabelText("场景"), "voice");
    await user.clear(screen.getByLabelText("当前请求"));
    await user.type(screen.getByLabelText("当前请求"), "语音回复要短一点");
    await user.clear(screen.getByLabelText("召回上限"));
    await user.type(screen.getByLabelText("召回上限"), "4");
    await user.click(screen.getByRole("button", { name: "预览上下文" }));

    expect(await screen.findByText("Owner prefers direct technical updates.")).not.toBeNull();
    expect(screen.getByText("Use shorter voice replies.")).not.toBeNull();
    expect(screen.getByText("Matched voice scene")).not.toBeNull();
    await waitFor(() =>
      expect(requests.find((request) => request.path === "/api/v1/admin/cognition/router-preview")).toMatchObject({
        method: "POST",
        body: { scene: "voice", current_request: "语音回复要短一点", limit: 4 },
      }),
    );
  });

  it("renders relationship state returned as a scoped record list", async () => {
    const user = userEvent.setup();
    render(<TestApp initialPath="/cognition" />);

    await screen.findByRole("heading", { name: "认知成长" });
    await user.click(screen.getByRole("tab", { name: "Relationship" }));

    expect(await screen.findByText("Built a voice robot cognitive layer together.")).not.toBeNull();
    expect(screen.getByText("Keep important memory sparse.")).not.toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
