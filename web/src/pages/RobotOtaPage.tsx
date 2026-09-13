import { type ChangeEvent, type FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, formatApiError, type RobotOtaRelease } from "../api/client";
import { useNavSection } from "../app/navSections";

const DEFAULT_DRAFT = {
  version: "",
  channel: "stable",
  min_protocol_version: "1",
  activate: true,
  rollback_version: "",
};

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function activeRelease(releases: RobotOtaRelease[]): RobotOtaRelease | null {
  return releases.find((release) => release.active) ?? null;
}

export function RobotOtaPage() {
  const queryClient = useQueryClient();
  const { navTargetProps } = useNavSection();
  const releasesQuery = useQuery({
    queryKey: ["robot-ota-releases"],
    queryFn: () => api.robotOtaReleases(),
  });

  const [draft, setDraft] = useState(DEFAULT_DRAFT);
  const [artifact, setArtifact] = useState<File | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  const releases = releasesQuery.data ?? [];
  const currentActive = useMemo(() => activeRelease(releases), [releases]);

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

  function updateArtifact(event: ChangeEvent<HTMLInputElement>) {
    setArtifact(event.target.files?.[0] ?? null);
  }

  function submitUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLocalError(null);
    uploadRelease.mutate();
  }

  if (releasesQuery.isLoading) return <p>正在加载机器人 OTA 发布...</p>;
  if (releasesQuery.isError) {
    return <p role="alert">{formatApiError(releasesQuery.error, "机器人 OTA 发布加载失败")}</p>;
  }

  return (
    <section>
      <p className="eyebrow">Robot OTA</p>
      <h2>机器人 OTA</h2>
      <p>上传树莓派运行时包并激活版本。设备端会通过 OTA manifest 获取当前稳定版本，再下载并校验 artifact。</p>

      <div className="status-grid" aria-label="机器人 OTA 状态">
        <article className="status-card">
          <span>当前激活版本</span>
          <p>{currentActive?.version ?? "未发布"}</p>
        </article>
        <article className="status-card">
          <span>发布数量</span>
          <p>{releases.length} 个版本</p>
        </article>
        <article className="status-card">
          <span>通道</span>
          <p>{currentActive?.channel ?? "stable"}</p>
        </article>
      </div>

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
    </section>
  );
}
