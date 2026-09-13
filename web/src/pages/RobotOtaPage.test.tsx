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

type RobotDeviceFixture = {
  device_id: string;
  name: string;
  status: string;
  current_version: string | null;
  target_version: string | null;
  last_seen_at: string | null;
  config: {
    display_name: string;
    locale: string;
    voice_preset_id: string | null;
    volume: number;
    wake_word_required: boolean;
  };
  policy: {
    ota_channel: string;
    auto_update: boolean;
    maintenance_window: string;
    telemetry_enabled: boolean;
  };
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
  let devices: RobotDeviceFixture[];

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
    devices = [
      {
        device_id: "pi-living-room",
        name: "客厅树莓派",
        status: "online",
        current_version: "2026.09.13+1",
        target_version: null,
        last_seen_at: "2026-09-13T08:00:00Z",
        config: {
          display_name: "客厅陪伴机器人",
          locale: "zh-CN",
          voice_preset_id: "warm",
          volume: 72,
          wake_word_required: true,
        },
        policy: {
          ota_channel: "stable",
          auto_update: true,
          maintenance_window: "03:00-05:00",
          telemetry_enabled: true,
        },
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
        if (path === "/api/v1/admin/robot/devices" && method === "GET") {
          return jsonResponse(devices);
        }
        if (path === "/api/v1/admin/robot/devices/pi-living-room/config" && method === "PUT") {
          const body = JSON.parse(String(init?.body));
          requests.push({ path, method, body });
          devices = devices.map((device) =>
            device.device_id === "pi-living-room" ? { ...device, config: { ...device.config, ...body } } : device,
          );
          return jsonResponse(devices[0]);
        }
        if (path === "/api/v1/admin/robot/devices/pi-living-room/policy" && method === "PUT") {
          const body = JSON.parse(String(init?.body));
          requests.push({ path, method, body });
          devices = devices.map((device) =>
            device.device_id === "pi-living-room" ? { ...device, policy: { ...device.policy, ...body } } : device,
          );
          return jsonResponse(devices[0]);
        }
        if (path === "/api/v1/admin/robot/devices/pi-living-room/ota-target" && method === "POST") {
          const body = JSON.parse(String(init?.body));
          requests.push({ path, method, body });
          devices = devices.map((device) =>
            device.device_id === "pi-living-room" ? { ...device, target_version: body.version } : device,
          );
          return jsonResponse(devices[0]);
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

    expect(await screen.findByRole("heading", { name: "树莓派机器人管理" })).not.toBeNull();
    expect(await screen.findByRole("heading", { name: "设备列表" })).not.toBeNull();
    expect(screen.getAllByText("客厅树莓派").length).toBeGreaterThan(0);
    expect(screen.getAllByText("2026.09.13+1").length).toBeGreaterThan(0);
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

  it("updates Raspberry Pi robot device config, policy, and OTA target", async () => {
    const user = userEvent.setup();
    render(<TestApp initialPath="/robot-ota?section=devices" />);

    expect(await screen.findByRole("heading", { name: "树莓派机器人管理" })).not.toBeNull();
    await user.clear(screen.getByLabelText("显示名称"));
    await user.type(screen.getByLabelText("显示名称"), "卧室陪伴机器人");
    await user.clear(screen.getByLabelText("音量"));
    await user.type(screen.getByLabelText("音量"), "55");
    await user.click(screen.getByRole("button", { name: "保存设备配置" }));

    await user.selectOptions(screen.getByLabelText("OTA 通道"), "beta");
    await user.clear(screen.getByLabelText("维护窗口"));
    await user.type(screen.getByLabelText("维护窗口"), "02:00-04:00");
    await user.click(screen.getByRole("button", { name: "保存设备策略" }));

    await user.selectOptions(screen.getByLabelText("目标版本"), "2026.09.13+1");
    await user.click(screen.getByRole("button", { name: "设置目标版本" }));

    await waitFor(() => {
      expect(requests).toContainEqual({
        path: "/api/v1/admin/robot/devices/pi-living-room/config",
        method: "PUT",
        body: {
          display_name: "卧室陪伴机器人",
          locale: "zh-CN",
          voice_preset_id: "warm",
          volume: 55,
          wake_word_required: true,
        },
      });
      expect(requests).toContainEqual({
        path: "/api/v1/admin/robot/devices/pi-living-room/policy",
        method: "PUT",
        body: {
          ota_channel: "beta",
          auto_update: true,
          maintenance_window: "02:00-04:00",
          telemetry_enabled: true,
        },
      });
      expect(requests).toContainEqual({
        path: "/api/v1/admin/robot/devices/pi-living-room/ota-target",
        method: "POST",
        body: { version: "2026.09.13+1" },
      });
    });
  });
});
