import { type ChangeEvent, type FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  api,
  ApiError,
  formatApiError,
  type RobotDevice,
  type RobotDeviceConfig,
  type RobotDevicePolicy,
  type RobotOtaRelease,
} from "../api/client";
import { useNavSection } from "../app/navSections";

const DEFAULT_DRAFT = {
  version: "",
  channel: "stable",
  min_protocol_version: "1",
  activate: true,
  rollback_version: "",
};

const DEFAULT_CONFIG: RobotDeviceConfig = {
  display_name: "",
  locale: "zh-CN",
  voice_preset_id: null,
  volume: 70,
  wake_word_required: true,
};

const DEFAULT_POLICY: RobotDevicePolicy = {
  ota_channel: "stable",
  auto_update: true,
  maintenance_window: "03:00-05:00",
  telemetry_enabled: true,
};

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function activeRelease(releases: RobotOtaRelease[]): RobotOtaRelease | null {
  return releases.find((release) => release.active) ?? null;
}

function latestDevice(devices: RobotDevice[]): string {
  return devices.find((device) => device.status === "online")?.device_id ?? devices[0]?.device_id ?? "";
}

export function RobotOtaPage() {
  const queryClient = useQueryClient();
  const { navTargetProps } = useNavSection();
  const releasesQuery = useQuery({
    queryKey: ["robot-ota-releases"],
    queryFn: () => api.robotOtaReleases(),
  });
  const devicesQuery = useQuery({
    queryKey: ["robot-devices"],
    queryFn: () => api.robotDevices(),
  });

  const [draft, setDraft] = useState(DEFAULT_DRAFT);
  const [artifact, setArtifact] = useState<File | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [selectedDeviceId, setSelectedDeviceId] = useState("");
  const [configDraft, setConfigDraft] = useState<RobotDeviceConfig>(DEFAULT_CONFIG);
  const [policyDraft, setPolicyDraft] = useState<RobotDevicePolicy>(DEFAULT_POLICY);
  const [targetVersion, setTargetVersion] = useState("");

  const releases = releasesQuery.data ?? [];
  const devices = devicesQuery.data ?? [];
  const currentActive = useMemo(() => activeRelease(releases), [releases]);
  const selectedDevice = devices.find((device) => device.device_id === selectedDeviceId) ?? devices[0] ?? null;

  useEffect(() => {
    if (!selectedDeviceId && devices.length > 0) setSelectedDeviceId(latestDevice(devices));
  }, [devices, selectedDeviceId]);

  useEffect(() => {
    if (!selectedDevice) return;
    setConfigDraft(selectedDevice.config);
    setPolicyDraft(selectedDevice.policy);
    setTargetVersion(selectedDevice.target_version ?? "");
  }, [selectedDevice]);

  const uploadRelease = useMutation({
    mutationFn: async () => {
      if (!artifact) throw new Error("请选择运行时包");
      const version = draft.version.trim();
      if (!version) throw new Error("请填写版本号");
      setLocalError(null);
      return api.uploadRobotOtaRelease({
        version,
        channel: draft.channel.trim() || "stable",
        min_protocol_version: draft.min_protocol_version.trim() || "1",
        activate: draft.activate,
        rollback_version: draft.rollback_version.trim() || null,
        artifact,
      });
    },
    onSuccess: async () => {
      setDraft(DEFAULT_DRAFT);
      setArtifact(null);
      await queryClient.invalidateQueries({ queryKey: ["robot-ota-releases"] });
    },
    onError: (error) => {
      if (error instanceof Error && !(error instanceof ApiError)) setLocalError(error.message);
    },
  });

  const activateRelease = useMutation({
    mutationFn: (version: string) => api.activateRobotOtaRelease(version),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["robot-ota-releases"] });
    },
  });

  const saveConfig = useMutation({
    mutationFn: () => {
      if (!selectedDevice) throw new Error("请选择设备");
      return api.updateRobotDeviceConfig(selectedDevice.device_id, configDraft);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["robot-devices"] });
    },
  });

  const savePolicy = useMutation({
    mutationFn: () => {
      if (!selectedDevice) throw new Error("请选择设备");
      return api.updateRobotDevicePolicy(selectedDevice.device_id, policyDraft);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["robot-devices"] });
    },
  });

  const saveTarget = useMutation({
    mutationFn: () => {
      if (!selectedDevice) throw new Error("请选择设备");
      return api.updateRobotDeviceOtaTarget(selectedDevice.device_id, {
        version: targetVersion.trim() || null,
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["robot-devices"] });
    },
  });

  function updateArtifact(event: ChangeEvent<HTMLInputElement>) {
    setArtifact(event.target.files?.[0] ?? null);
  }

  function submitUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLocalError(null);
    uploadRelease.mutate();
  }

  function submitConfig(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    saveConfig.mutate();
  }

  function submitPolicy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    savePolicy.mutate();
  }

  function submitTarget(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    saveTarget.mutate();
  }

  if (releasesQuery.isLoading || devicesQuery.isLoading) return <p>正在加载机器人管理数据...</p>;
  if (releasesQuery.isError) {
    return <p role="alert">{formatApiError(releasesQuery.error, "机器人 OTA 发布加载失败")}</p>;
  }
  if (devicesQuery.isError) {
    return <p role="alert">{formatApiError(devicesQuery.error, "机器人设备加载失败")}</p>;
  }

  return (
    <section>
      <p className="eyebrow">Raspberry Pi Robot</p>
      <h2>树莓派机器人管理</h2>
      <p>管理树莓派机器人设备、运行配置、更新策略和 OTA 发布。设备端会读取配置与 OTA target，再下载并校验运行时包。</p>

      <div className="status-grid" aria-label="机器人管理状态">
        <article className="status-card">
          <span>在线设备</span>
          <p>{devices.filter((device) => device.status === "online").length} 台</p>
        </article>
        <article className="status-card">
          <span>当前激活版本</span>
          <p>{currentActive?.version ?? "未发布"}</p>
        </article>
        <article className="status-card">
          <span>发布数量</span>
          <p>{releases.length} 个版本</p>
        </article>
      </div>

      <section aria-label="机器人设备列表" {...navTargetProps("devices")}>
        <h3>设备列表</h3>
        {devices.length === 0 ? (
          <p className="field-help">还没有注册的树莓派机器人设备。设备首次上线后会出现在这里。</p>
        ) : (
          <table aria-label="机器人设备">
            <thead>
              <tr>
                <th>设备</th>
                <th>状态</th>
                <th>当前版本</th>
                <th>目标版本</th>
                <th>OTA 通道</th>
                <th>最后在线</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {devices.map((device) => (
                <tr key={device.device_id}>
                  <td>{device.name || device.device_id}</td>
                  <td>{device.status}</td>
                  <td>{device.current_version ?? "未知"}</td>
                  <td>{device.target_version ?? "跟随策略"}</td>
                  <td>{device.policy.ota_channel}</td>
                  <td>{device.last_seen_at ?? "从未在线"}</td>
                  <td className="table-actions">
                    <button type="button" onClick={() => setSelectedDeviceId(device.device_id)}>
                      管理
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {selectedDevice ? (
        <>
          <form onSubmit={submitConfig} aria-label="机器人设备配置" {...navTargetProps("config", "settings-form")}>
            <fieldset>
              <legend>设备配置</legend>
              <div className="form-grid">
                <label htmlFor="robot-device-select">
                  选择设备
                  <select id="robot-device-select" value={selectedDevice.device_id} onChange={(event) => setSelectedDeviceId(event.target.value)}>
                    {devices.map((device) => (
                      <option key={device.device_id} value={device.device_id}>
                        {device.name || device.device_id}
                      </option>
                    ))}
                  </select>
                </label>
                <label htmlFor="robot-device-display-name">
                  显示名称
                  <input
                    id="robot-device-display-name"
                    value={configDraft.display_name}
                    onChange={(event) => setConfigDraft((current) => ({ ...current, display_name: event.target.value }))}
                  />
                </label>
                <label htmlFor="robot-device-locale">
                  语言区域
                  <input
                    id="robot-device-locale"
                    value={configDraft.locale}
                    onChange={(event) => setConfigDraft((current) => ({ ...current, locale: event.target.value }))}
                  />
                </label>
                <label htmlFor="robot-device-voice">
                  音色 ID
                  <input
                    id="robot-device-voice"
                    value={configDraft.voice_preset_id ?? ""}
                    onChange={(event) =>
                      setConfigDraft((current) => ({ ...current, voice_preset_id: event.target.value.trim() || null }))
                    }
                  />
                </label>
                <label htmlFor="robot-device-volume">
                  音量
                  <input
                    id="robot-device-volume"
                    type="number"
                    min="0"
                    max="100"
                    value={configDraft.volume}
                    onChange={(event) => setConfigDraft((current) => ({ ...current, volume: Number(event.target.value) }))}
                  />
                </label>
              </div>
              <label className="inline-check">
                <input
                  type="checkbox"
                  checked={configDraft.wake_word_required}
                  onChange={(event) => setConfigDraft((current) => ({ ...current, wake_word_required: event.target.checked }))}
                />
                需要唤醒词
              </label>
              <button type="submit" disabled={saveConfig.isPending}>
                {saveConfig.isPending ? "正在保存..." : "保存设备配置"}
              </button>
              {saveConfig.isSuccess ? <p role="status">设备配置已保存</p> : null}
            </fieldset>
          </form>

          <form onSubmit={submitPolicy} aria-label="机器人设备策略" {...navTargetProps("policy", "settings-form")}>
            <fieldset>
              <legend>设备策略</legend>
              <div className="form-grid">
                <label htmlFor="robot-device-ota-channel">
                  OTA 通道
                  <select
                    id="robot-device-ota-channel"
                    value={policyDraft.ota_channel}
                    onChange={(event) => setPolicyDraft((current) => ({ ...current, ota_channel: event.target.value }))}
                  >
                    <option value="stable">stable</option>
                    <option value="beta">beta</option>
                  </select>
                </label>
                <label htmlFor="robot-device-maintenance">
                  维护窗口
                  <input
                    id="robot-device-maintenance"
                    value={policyDraft.maintenance_window}
                    onChange={(event) => setPolicyDraft((current) => ({ ...current, maintenance_window: event.target.value }))}
                  />
                </label>
              </div>
              <label className="inline-check">
                <input
                  type="checkbox"
                  checked={policyDraft.auto_update}
                  onChange={(event) => setPolicyDraft((current) => ({ ...current, auto_update: event.target.checked }))}
                />
                自动更新
              </label>
              <label className="inline-check">
                <input
                  type="checkbox"
                  checked={policyDraft.telemetry_enabled}
                  onChange={(event) => setPolicyDraft((current) => ({ ...current, telemetry_enabled: event.target.checked }))}
                />
                上报遥测
              </label>
              <button type="submit" disabled={savePolicy.isPending}>
                {savePolicy.isPending ? "正在保存..." : "保存设备策略"}
              </button>
              {savePolicy.isSuccess ? <p role="status">设备策略已保存</p> : null}
            </fieldset>
          </form>

          <form onSubmit={submitTarget} aria-label="机器人 OTA 目标版本" {...navTargetProps("ota-target", "settings-form")}>
            <fieldset>
              <legend>OTA 目标版本</legend>
              <div className="form-grid">
                <label htmlFor="robot-device-target-version">
                  目标版本
                  <select id="robot-device-target-version" value={targetVersion} onChange={(event) => setTargetVersion(event.target.value)}>
                    <option value="">跟随设备策略</option>
                    {releases.map((release) => (
                      <option key={release.version} value={release.version}>
                        {release.version}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <button type="submit" disabled={saveTarget.isPending}>
                {saveTarget.isPending ? "正在保存..." : "设置目标版本"}
              </button>
              {saveTarget.isSuccess ? <p role="status">OTA 目标版本已保存</p> : null}
            </fieldset>
          </form>
        </>
      ) : null}

      <form onSubmit={submitUpload} aria-label="上传机器人 OTA 发布" {...navTargetProps("upload", "settings-form")}>
        <fieldset>
          <legend>上传发布</legend>
          <div className="form-grid">
            <label htmlFor="robot-ota-version">
              版本号
              <input
                id="robot-ota-version"
                placeholder="2026.09.14+1"
                value={draft.version}
                onChange={(event) => setDraft((current) => ({ ...current, version: event.target.value }))}
              />
            </label>
            <label htmlFor="robot-ota-channel">
              通道
              <select
                id="robot-ota-channel"
                value={draft.channel}
                onChange={(event) => setDraft((current) => ({ ...current, channel: event.target.value }))}
              >
                <option value="stable">stable</option>
                <option value="beta">beta</option>
              </select>
            </label>
            <label htmlFor="robot-ota-protocol">
              最小协议版本
              <input
                id="robot-ota-protocol"
                value={draft.min_protocol_version}
                onChange={(event) =>
                  setDraft((current) => ({ ...current, min_protocol_version: event.target.value }))
                }
              />
            </label>
            <label htmlFor="robot-ota-rollback">
              回滚版本
              <input
                id="robot-ota-rollback"
                value={draft.rollback_version}
                onChange={(event) => setDraft((current) => ({ ...current, rollback_version: event.target.value }))}
              />
            </label>
            <label htmlFor="robot-ota-artifact">
              运行时包
              <input id="robot-ota-artifact" type="file" accept=".tar.gz,.tgz,application/gzip" onChange={updateArtifact} />
            </label>
          </div>
          <label className="inline-check">
            <input
              type="checkbox"
              checked={draft.activate}
              onChange={(event) => setDraft((current) => ({ ...current, activate: event.target.checked }))}
            />
            上传后立即激活
          </label>
          <button type="submit" disabled={uploadRelease.isPending}>
            {uploadRelease.isPending ? "正在上传..." : "上传并发布"}
          </button>
          {uploadRelease.isSuccess ? <p role="status">OTA 发布已保存</p> : null}
        </fieldset>
      </form>

      <section aria-label="机器人 OTA 版本列表" {...navTargetProps("releases")}>
        <h3>版本列表</h3>
        {releases.length === 0 ? (
          <p className="field-help">还没有 OTA 发布。上传树莓派运行时包后，设备 manifest 会返回激活版本。</p>
        ) : (
          <table aria-label="机器人 OTA releases">
            <thead>
              <tr>
                <th>版本</th>
                <th>状态</th>
                <th>通道</th>
                <th>协议</th>
                <th>大小</th>
                <th>SHA256</th>
                <th>Artifact URL</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {releases.map((release) => (
                <tr key={release.version}>
                  <td>{release.version}</td>
                  <td>{release.active ? "active" : "inactive"}</td>
                  <td>{release.channel}</td>
                  <td>{release.min_protocol_version}</td>
                  <td>{formatBytes(release.artifact_size_bytes)}</td>
                  <td>{release.artifact_sha256.slice(0, 12)}...</td>
                  <td>{release.artifact_url}</td>
                  <td className="table-actions">
                    <button
                      type="button"
                      disabled={release.active || activateRelease.isPending}
                      onClick={() => activateRelease.mutate(release.version)}
                    >
                      激活
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {localError ? <p role="alert">{localError}</p> : null}
      {uploadRelease.isError ? <p role="alert">{formatApiError(uploadRelease.error, "OTA 发布上传失败")}</p> : null}
      {activateRelease.isError ? <p role="alert">{formatApiError(activateRelease.error, "OTA 发布激活失败")}</p> : null}
      {saveConfig.isError ? <p role="alert">{formatApiError(saveConfig.error, "设备配置保存失败")}</p> : null}
      {savePolicy.isError ? <p role="alert">{formatApiError(savePolicy.error, "设备策略保存失败")}</p> : null}
      {saveTarget.isError ? <p role="alert">{formatApiError(saveTarget.error, "OTA 目标版本保存失败")}</p> : null}
    </section>
  );
}
