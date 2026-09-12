import { type ChangeEvent, type FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  api,
  ApiError,
  formatApiError,
  type RobotVoiceCloneJob,
  type RobotVoicePreset,
  type RobotVoiceSettings,
} from "../api/client";

const EMPTY_PRESET = {
  id: "",
  name: "",
  description: "",
};

const EMPTY_CLONE = {
  voice_id: "",
  voice_name: "",
  authorization_confirmed: false,
};

function cloneSettings(settings: RobotVoiceSettings): RobotVoiceSettings {
  return {
    ...settings,
    voices: [...settings.voices],
    clone_jobs: [...settings.clone_jobs],
  };
}

function voiceOptionLabel(voice: RobotVoicePreset): string {
  return `${voice.name} - ${voice.voice_id}`;
}

export function VoiceModelsPage() {
  const queryClient = useQueryClient();
  const settingsQuery = useQuery({
    queryKey: ["robot-voice-settings"],
    queryFn: () => api.robotVoiceSettings(),
  });
  const jobsQuery = useQuery({
    queryKey: ["robot-voice-clone-jobs"],
    queryFn: () => api.robotVoiceCloneJobs(),
  });

  const [settings, setSettings] = useState<RobotVoiceSettings | null>(null);
  const [presetDraft, setPresetDraft] = useState(EMPTY_PRESET);
  const [cloneDraft, setCloneDraft] = useState(EMPTY_CLONE);
  const [sourceAudio, setSourceAudio] = useState<File | null>(null);
  const [promptAudio, setPromptAudio] = useState<File | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    if (settingsQuery.data) setSettings(cloneSettings(settingsQuery.data));
  }, [settingsQuery.data]);

  const saveSettings = useMutation({
    mutationFn: async () => {
      if (!settings) throw new Error("语音模型配置尚未加载完成");
      setLocalError(null);
      return api.updateRobotVoiceSettings(settings);
    },
    onSuccess: async (saved) => {
      setSettings(cloneSettings(saved));
      await queryClient.invalidateQueries({ queryKey: ["robot-voice-settings"] });
    },
    onError: (error) => {
      if (error instanceof Error && !(error instanceof ApiError)) setLocalError(error.message);
    },
  });

  const createPreset = useMutation({
    mutationFn: async () => {
      const id = presetDraft.id.trim();
      const name = presetDraft.name.trim();
      if (!id || !name) throw new Error("请填写音色 ID 和音色名称");
      return api.createRobotVoicePreset({
        id,
        name,
        provider: "minimax",
        voice_id: id,
        description: presetDraft.description.trim() || null,
        enabled: true,
        cloned: false,
        builtin: false,
        created_at: null,
        updated_at: null,
      });
    },
    onSuccess: async (saved) => {
      setSettings(cloneSettings(saved));
      setPresetDraft(EMPTY_PRESET);
      await queryClient.invalidateQueries({ queryKey: ["robot-voice-settings"] });
    },
    onError: (error) => {
      if (error instanceof Error && !(error instanceof ApiError)) setLocalError(error.message);
    },
  });

  const deletePreset = useMutation({
    mutationFn: (id: string) => api.deleteRobotVoicePreset(id),
    onSuccess: async (saved) => {
      setSettings(cloneSettings(saved));
      await queryClient.invalidateQueries({ queryKey: ["robot-voice-settings"] });
    },
  });

  const createClone = useMutation({
    mutationFn: async () => {
      if (!sourceAudio) throw new Error("请先选择源声音样本");
      const voiceId = cloneDraft.voice_id.trim();
      const voiceName = cloneDraft.voice_name.trim();
      if (!voiceId || !voiceName) throw new Error("请填写克隆 voice_id 和音色名称");
      return api.createRobotVoiceClone({
        voice_id: voiceId,
        voice_name: voiceName,
        authorization_confirmed: cloneDraft.authorization_confirmed,
        source_audio: sourceAudio,
        prompt_audio: promptAudio,
      });
    },
    onSuccess: async () => {
      setCloneDraft(EMPTY_CLONE);
      setSourceAudio(null);
      setPromptAudio(null);
      await queryClient.invalidateQueries({ queryKey: ["robot-voice-settings"] });
      await queryClient.invalidateQueries({ queryKey: ["robot-voice-clone-jobs"] });
      const refreshed = await api.robotVoiceSettings();
      setSettings(cloneSettings(refreshed));
    },
    onError: (error) => {
      if (error instanceof Error && !(error instanceof ApiError)) setLocalError(error.message);
    },
  });

  if (settingsQuery.isLoading || jobsQuery.isLoading) return <p>正在加载语音模型配置...</p>;
  if (settingsQuery.isError) return <p role="alert">{formatApiError(settingsQuery.error, "语音模型配置加载失败")}</p>;
  if (jobsQuery.isError) return <p role="alert">{formatApiError(jobsQuery.error, "声音克隆任务加载失败")}</p>;
  if (!settings) return <p role="alert">语音模型配置加载失败：后端没有返回设置内容。</p>;

  const cloneJobs: RobotVoiceCloneJob[] = jobsQuery.data ?? settings.clone_jobs;
  const voiceOptions = settings.voices.filter((voice) => voice.enabled);
  const selectedVoiceId = settings.default_voice_id ?? settings.minimax_tts_voice_id ?? "";
  const selectedVoiceIsPreset = voiceOptions.some((voice) => voice.voice_id === selectedVoiceId);

  function updateSettings(patch: Partial<RobotVoiceSettings>) {
    setSettings((current) => (current ? { ...current, ...patch } : current));
  }

  function updateDefaultVoice(value: string) {
    const voiceId = value || null;
    updateSettings({ minimax_tts_voice_id: voiceId, default_voice_id: voiceId });
  }

  function submitSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    saveSettings.mutate();
  }

  function submitPreset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLocalError(null);
    createPreset.mutate();
  }

  function submitClone(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLocalError(null);
    createClone.mutate();
  }

  function updateSourceAudio(event: ChangeEvent<HTMLInputElement>) {
    setSourceAudio(event.target.files?.[0] ?? null);
  }

  function updatePromptAudio(event: ChangeEvent<HTMLInputElement>) {
    setPromptAudio(event.target.files?.[0] ?? null);
  }

  return (
    <section>
      <p className="eyebrow">Voice models</p>
      <h2>语音模型</h2>
      <p>
        这里单独维护语音机器人的服务端 ASR/TTS、MiniMax Speech 2.8 音色、声音克隆和默认播报音色。树莓派只负责录音与播放，语音模型配置由服务器端统一控制。
      </p>

      <div className="status-grid" aria-label="语音模型状态">
        <article className="status-card">
          <span>服务端语音</span>
          <p>{settings.enabled ? `已启用 ${settings.media_provider}` : "未启用"}</p>
        </article>
        <article className="status-card">
          <span>API Key</span>
          <p>{settings.minimax_api_key_configured ? "已配置" : "未配置"}</p>
        </article>
        <article className="status-card">
          <span>默认音色</span>
          <p>{settings.default_voice_id ?? settings.minimax_tts_voice_id ?? "未设置"}</p>
        </article>
        <article className="status-card">
          <span>音色库</span>
          <p>{settings.voices.length} 个音色</p>
        </article>
      </div>

      <form onSubmit={submitSettings} aria-label="保存语音模型配置" className="settings-form">
        <fieldset>
          <legend>MiniMax ASR/TTS</legend>
          <label className="inline-check">
            <input
              type="checkbox"
              checked={settings.enabled}
              onChange={(event) =>
                updateSettings({
                  enabled: event.target.checked,
                  media_provider: event.target.checked ? "minimax" : "disabled",
                })
              }
            />
            启用服务端 ASR/TTS
          </label>
          <div className="form-grid">
            <label htmlFor="robot-voice-provider">
              语音供应商
              <select
                id="robot-voice-provider"
                value={settings.media_provider}
                onChange={(event) =>
                  updateSettings({
                    media_provider: event.target.value as RobotVoiceSettings["media_provider"],
                    enabled: event.target.value !== "disabled",
                  })
                }
              >
                <option value="disabled">关闭</option>
                <option value="minimax">MiniMax</option>
              </select>
            </label>
            <label htmlFor="minimax-api-key">
              MiniMax API Key
              <input
                id="minimax-api-key"
                type="password"
                autoComplete="off"
                placeholder={settings.minimax_api_key_configured ? "已配置，留空则不修改" : "填写 MiniMax API Key"}
                value={settings.minimax_api_key ?? ""}
                onChange={(event) => updateSettings({ minimax_api_key: event.target.value })}
              />
            </label>
            <label htmlFor="minimax-asr-model">
              ASR 模型
              <input
                id="minimax-asr-model"
                value={settings.minimax_asr_model}
                onChange={(event) => updateSettings({ minimax_asr_model: event.target.value })}
              />
            </label>
            <label htmlFor="minimax-tts-model">
              TTS 模型
              <select
                id="minimax-tts-model"
                value={settings.minimax_tts_model}
                onChange={(event) => updateSettings({ minimax_tts_model: event.target.value })}
              >
                <option value="speech-2.8-turbo">speech-2.8-turbo</option>
                <option value="speech-2.8-hd">speech-2.8-hd</option>
                <option value="speech-2.6-turbo">speech-2.6-turbo</option>
              </select>
            </label>
            <label htmlFor="robot-default-voice-id">
              默认音色
              <select
                id="robot-default-voice-id"
                value={selectedVoiceIsPreset ? selectedVoiceId : ""}
                onChange={(event) => updateDefaultVoice(event.target.value)}
              >
                <option value="">未设置</option>
                {voiceOptions.map((voice) => (
                  <option key={voice.id} value={voice.voice_id}>
                    {voiceOptionLabel(voice)}
                  </option>
                ))}
              </select>
            </label>
            <label htmlFor="robot-custom-default-voice-id">
              自定义 voice_id
              <input
                id="robot-custom-default-voice-id"
                placeholder="粘贴 MiniMax 新音色或外部生成的 voice_id"
                value={selectedVoiceIsPreset ? "" : selectedVoiceId}
                onChange={(event) => updateDefaultVoice(event.target.value)}
              />
            </label>
            <label htmlFor="robot-voice-format">
              输出格式
              <select
                id="robot-voice-format"
                value={settings.minimax_tts_audio_format}
                onChange={(event) =>
                  updateSettings({
                    minimax_tts_audio_format: event.target.value as RobotVoiceSettings["minimax_tts_audio_format"],
                  })
                }
              >
                <option value="mp3">mp3</option>
                <option value="wav">wav</option>
                <option value="flac">flac</option>
                <option value="pcm">pcm</option>
                <option value="opus">opus</option>
              </select>
            </label>
            <label htmlFor="robot-voice-sample-rate">
              采样率
              <input
                id="robot-voice-sample-rate"
                type="number"
                min={8000}
                max={48000}
                value={settings.minimax_tts_sample_rate_hz}
                onChange={(event) => updateSettings({ minimax_tts_sample_rate_hz: Number(event.target.value) })}
              />
            </label>
          </div>
          <label className="inline-check">
            <input
              type="checkbox"
              checked={settings.clone_enabled}
              onChange={(event) => updateSettings({ clone_enabled: event.target.checked })}
            />
            允许控制台发起声音克隆
          </label>
          <div className="form-grid">
            <label htmlFor="robot-clone-model">
              克隆模型
              <select
                id="robot-clone-model"
                value={settings.clone_model}
                onChange={(event) => updateSettings({ clone_model: event.target.value })}
              >
                <option value="speech-2.8-hd">speech-2.8-hd</option>
                <option value="speech-2.8-turbo">speech-2.8-turbo</option>
              </select>
            </label>
            <label htmlFor="robot-clone-preview-text">
              克隆试听文本
              <textarea
                id="robot-clone-preview-text"
                value={settings.clone_preview_text}
                onChange={(event) => updateSettings({ clone_preview_text: event.target.value })}
              />
            </label>
            <label htmlFor="robot-clone-prompt-text">
              克隆提示文本
              <textarea
                id="robot-clone-prompt-text"
                value={settings.clone_prompt_text ?? ""}
                onChange={(event) => updateSettings({ clone_prompt_text: event.target.value || null })}
              />
            </label>
          </div>
          <button type="submit" disabled={saveSettings.isPending}>
            {saveSettings.isPending ? "正在保存..." : "保存语音模型配置"}
          </button>
          {saveSettings.isSuccess ? <p role="status">语音模型配置已保存</p> : null}
        </fieldset>
      </form>

      <form onSubmit={submitPreset} aria-label="保存音色" className="settings-form">
        <fieldset>
          <legend>音色选择</legend>
          <div className="form-grid">
            <label htmlFor="voice-preset-id">
              音色 ID
              <input
                id="voice-preset-id"
                value={presetDraft.id}
                onChange={(event) => setPresetDraft((draft) => ({ ...draft, id: event.target.value }))}
              />
            </label>
            <label htmlFor="voice-preset-name">
              音色名称
              <input
                id="voice-preset-name"
                value={presetDraft.name}
                onChange={(event) => setPresetDraft((draft) => ({ ...draft, name: event.target.value }))}
              />
            </label>
            <label htmlFor="voice-preset-description">
              音色说明
              <input
                id="voice-preset-description"
                value={presetDraft.description}
                onChange={(event) => setPresetDraft((draft) => ({ ...draft, description: event.target.value }))}
              />
            </label>
          </div>
          <button type="submit" disabled={createPreset.isPending}>保存音色</button>
          {settings.voices.length === 0 ? (
            <p className="field-help">还没有保存音色。可以先保存已有 voice_id，或用下方声音克隆生成新音色。</p>
          ) : (
            <ul>
              {settings.voices.map((voice) => (
                <li key={voice.id}>
                  {voice.name}：{voice.voice_id}
                  {voice.builtin ? <span className="field-help"> 内置</span> : null}
                  {voice.builtin ? null : (
                    <button
                      type="button"
                      className="danger-action"
                      onClick={() => deletePreset.mutate(voice.id)}
                    >
                      删除
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </fieldset>
      </form>

      <form onSubmit={submitClone} aria-label="声音克隆" className="settings-form">
        <fieldset>
          <legend>声音克隆</legend>
          <p className="field-help">
            只上传已获授权的声音样本。后端只保存任务元数据、provider file_id、生成的 voice_id 和错误信息，不长期保存原始音频。
          </p>
          <div className="form-grid">
            <label htmlFor="clone-voice-id">
              克隆 voice_id
              <input
                id="clone-voice-id"
                value={cloneDraft.voice_id}
                onChange={(event) => setCloneDraft((draft) => ({ ...draft, voice_id: event.target.value }))}
              />
            </label>
            <label htmlFor="clone-voice-name">
              克隆音色名称
              <input
                id="clone-voice-name"
                value={cloneDraft.voice_name}
                onChange={(event) => setCloneDraft((draft) => ({ ...draft, voice_name: event.target.value }))}
              />
            </label>
            <label htmlFor="source-audio">
              源声音样本
              <input id="source-audio" type="file" accept="audio/*" onChange={updateSourceAudio} />
            </label>
            <label htmlFor="prompt-audio">
              Prompt 样本
              <input id="prompt-audio" type="file" accept="audio/*" onChange={updatePromptAudio} />
            </label>
          </div>
          <label className="inline-check">
            <input
              type="checkbox"
              checked={cloneDraft.authorization_confirmed}
              onChange={(event) =>
                setCloneDraft((draft) => ({
                  ...draft,
                  authorization_confirmed: event.target.checked,
                }))
              }
            />
            我确认已获得声音克隆授权
          </label>
          <button type="submit" disabled={createClone.isPending || !settings.clone_enabled}>
            {createClone.isPending ? "正在克隆..." : "上传并克隆音色"}
          </button>
        </fieldset>
      </form>

      <div className="inline-guide" aria-label="声音克隆任务">
        <h3>克隆任务</h3>
        {cloneJobs.length === 0 ? (
          <p className="field-help">还没有声音克隆任务。</p>
        ) : (
          <ul>
            {cloneJobs.map((job) => (
              <li key={job.id}>
                <span>{job.voice_name}</span> · {job.voice_id} · {job.status}
              </li>
            ))}
          </ul>
        )}
      </div>

      {localError ? <p role="alert">{localError}</p> : null}
      {saveSettings.isError ? <p role="alert">{formatApiError(saveSettings.error, "语音模型配置保存失败")}</p> : null}
      {createPreset.isError ? <p role="alert">{formatApiError(createPreset.error, "音色保存失败")}</p> : null}
      {deletePreset.isError ? <p role="alert">{formatApiError(deletePreset.error, "音色删除失败")}</p> : null}
      {createClone.isError ? <p role="alert">{formatApiError(createClone.error, "声音克隆失败")}</p> : null}
    </section>
  );
}
