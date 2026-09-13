import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TestApp } from "../app/router";

const principal = {
  user_id: "11111111-1111-4111-8111-111111111111",
  tenant_id: "33333333-3333-4333-8333-333333333333",
  role: "super_admin",
};

type OtaReleaseFixture = {
  version: string;
  channel: string;
  min_protocol_version: string;
  artifact_url: string;
  artifact_sha256: string;
  artifact_size_bytes: number;
  signature: string;
  rollback_version: string | null;
  active: boolean;
  created_at: string;
};

function jsonResponse(payload: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

describe("RobotOtaPage", () => {
  const requests: Array<{ body: unknown; method: string; path: string }> = [];
  let releases: OtaReleaseFixture[];

  beforeEach(() => {
    requests.length = 0;
    releases = [
      {
        version: "2026.09.13+1",
        channel: "stable",
        min_protocol_version: "1",
        artifact_url: "https://testserver/api/v1/robot/ota/artifacts/{device_id}/2026.09.13+1/runtime.tgz",
        artifact_sha256: "a".repeat(64),
        artifact_size_bytes: 1024,
        signature: "sha256:" + "a".repeat(64),
        rollback_version: null,
        active: true,
        created_at: "2026-09-13T00:00:00Z",
      },
    ];
    window.sessionStorage.setItem("agent_hub_access_token", "owner-token");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        const method = init?.method ?? "GET";
        if (path === "/api/v1/auth/me") return jsonResponse(principal);
        if (path === "/api/v1/admin/robot/ota/releases" && method === "GET") {
          return jsonResponse(releases);
        }
        if (path === "/api/v1/admin/robot/ota/releases/upload" && method === "POST") {
          const form = init?.body as FormData;
          requests.push({
            path,
            method,
            body: {
              version: form.get("version"),
              channel: form.get("channel"),
              min_protocol_version: form.get("min_protocol_version"),
              activate: form.get("activate"),
              artifact_name: (form.get("artifact") as File).name,
            },
          });
          const release: OtaReleaseFixture = {
            version: String(form.get("version")),
            channel: String(form.get("channel")),
            min_protocol_version: String(form.get("min_protocol_version")),
            artifact_url: "https://testserver/api/v1/robot/ota/artifacts/{device_id}/2026.09.14+1/runtime.tgz",
            artifact_sha256: "b".repeat(64),
            artifact_size_bytes: 2048,
            signature: "sha256:" + "b".repeat(64),
            rollback_version: null,
            active: form.get("activate") === "true",
            created_at: "2026-09-14T00:00:00Z",
          };
          releases = [release, ...releases.map((item) => ({ ...item, active: false }))];
          return jsonResponse(release, { status: 201 });
        }
        return jsonResponse({ error: { code: "not_found", message: "not found" } }, { status: 404 });
      }),
    );
  });

  afterEach(() => {
    window.sessionStorage.clear();
    vi.unstubAllGlobals();
  });

  it("lists OTA releases and uploads an active runtime artifact", async () => {
    const user = userEvent.setup();
    render(<TestApp initialPath="/robot-ota" />);

    expect(await screen.findByRole("heading", { name: "机器人 OTA" })).not.toBeNull();
    expect((await screen.findAllByText("2026.09.13+1")).length).toBeGreaterThan(0);
    expect(screen.getByText("active")).not.toBeNull();

    await user.type(screen.getByLabelText("版本号"), "2026.09.14+1");
    await user.upload(
      screen.getByLabelText("运行时包"),
      new File(["runtime"], "cube-robot-runtime.tar.gz", { type: "application/gzip" }),
    );
    await user.click(screen.getByRole("button", { name: "上传并发布" }));

    await waitFor(() => {
      expect(requests).toContainEqual({
        path: "/api/v1/admin/robot/ota/releases/upload",
        method: "POST",
        body: {
          version: "2026.09.14+1",
          channel: "stable",
          min_protocol_version: "1",
          activate: "true",
          artifact_name: "cube-robot-runtime.tar.gz",
        },
      });
    });
    expect((await screen.findAllByText("2026.09.14+1")).length).toBeGreaterThan(0);
  });
});
