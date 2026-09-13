import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TestApp } from "../app/router";

const principal = {
  user_id: "11111111-1111-4111-8111-111111111111",
  tenant_id: "33333333-3333-4333-8333-333333333333",
  role: "super_admin",
};

type VoicePresetFixture = {
  id: string;
  name: string;
  provider: "minimax";
  voice_id: string;
  description: string | null;
  enabled: boolean;
  cloned: boolean;
  builtin: boolean;
  created_at: string | null;
  updated_at: string | null;
};

type VoiceCloneJobFixture = {
  id: string;
  status: "succeeded" | "failed";
  provider: "minimax";
  voice_id: string;
  voice_name: string;
  source_filename: string;
  source_size_bytes: number;
  source_content_type: string;
  prompt_filename: string | null;
  provider_file_id: string | null;
  provider_prompt_file_id: string | null;
  preview_audio_url: string | null;
  error: string | null;
  created_at: string;
};

type VoiceSettingsFixture = {
  configured: boolean;
  enabled: boolean;
  media_provider: "disabled" | "minimax";
  minimax_credential_ref: string | null;
  minimax_api_key_configured: boolean;
  minimax_api_base_url: string;
  minimax_asr_model: string;
  minimax_tts_model: string;
  minimax_tts_voice_id: string | null;
  minimax_tts_audio_format: "mp3" | "wav" | "flac" | "pcm" | "opus";
  minimax_tts_sample_rate_hz: number;
  minimax_tts_bitrate: number;
  minimax_tts_language_boost: string;
  minimax_tts_speed: number;
  minimax_tts_volume: number;
  minimax_tts_pitch: number;
  default_voice_id: string | null;
  voices: VoicePresetFixture[];
  clone_enabled: boolean;
  clone_model: string;
  clone_preview_text: string;
  clone_prompt_text: string | null;
  clone_jobs: VoiceCloneJobFixture[];
  wake_word_required: boolean;
  wake_words: string[];
};

const voiceSettings: VoiceSettingsFixture = {
  configured: false,
  enabled: false,
  media_provider: "disabled",
  minimax_credential_ref: null,
  minimax_api_key_configured: false,
  minimax_api_base_url: "https://api.minimaxi.com",
  minimax_asr_model: "asr-1.0",
  minimax_tts_model: "speech-2.8-turbo",
  minimax_tts_voice_id: null,
  minimax_tts_audio_format: "mp3",
  minimax_tts_sample_rate_hz: 32000,
  minimax_tts_bitrate: 128000,
  minimax_tts_language_boost: "auto",
  minimax_tts_speed: 1,
  minimax_tts_volume: 1,
  minimax_tts_pitch: 0,
  default_voice_id: null,
  voices: [
    {
      id: "Chinese (Mandarin)_Warm_Girl",
      name: "温暖女声",
      provider: "minimax",
      voice_id: "Chinese (Mandarin)_Warm_Girl",
      description: "MiniMax 内置中文陪伴音色",
      enabled: true,
      cloned: false,
      builtin: true,
      created_at: null,
      updated_at: null,
    },
    {
      id: "Chinese (Mandarin)_Gentle_Youth",
      name: "温和青年",
      provider: "minimax",
      voice_id: "Chinese (Mandarin)_Gentle_Youth",
      description: "MiniMax 内置中文陪伴音色",
      enabled: true,
      cloned: false,
      builtin: true,
      created_at: null,
      updated_at: null,
    },
  ],
  clone_enabled: false,
  clone_model: "speech-2.8-hd",
  clone_preview_text: "你好，我是你的语音机器人。",
  clone_prompt_text: null,
  clone_jobs: [],
  wake_word_required: false,
  wake_words: [],
};

function jsonResponse(payload: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

describe("VoiceModelsPage", () => {
  const requests: Array<{ body: unknown; method: string; path: string }> = [];
  let currentVoiceSettings: typeof voiceSettings;

  beforeEach(() => {
    requests.length = 0;
    currentVoiceSettings = structuredClone(voiceSettings);
    window.sessionStorage.setItem("agent_hub_access_token", "owner-token");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        const method = init?.method ?? "GET";
        if (path === "/api/v1/auth/me") return jsonResponse(principal);
        if (path === "/api/v1/admin/robot/voice-settings") {
          if (method === "PUT") {
            currentVoiceSettings = {
              ...currentVoiceSettings,
              ...JSON.parse(String(init?.body)),
              configured: true,
              minimax_api_key_configured: true,
            };
            requests.push({ path, method, body: JSON.parse(String(init?.body)) });
            return jsonResponse(currentVoiceSettings);
          }
          return jsonResponse(currentVoiceSettings);
        }
        if (path === "/api/v1/admin/robot/voices" && method === "POST") {
          const body = JSON.parse(String(init?.body));
          currentVoiceSettings = {
            ...currentVoiceSettings,
            default_voice_id: body.voice_id,
            voices: [body],
          };
          requests.push({ path, method, body });
          return jsonResponse(currentVoiceSettings, { status: 201 });
        }
        if (path === "/api/v1/admin/robot/voice-clones" && method === "GET") {
          return jsonResponse(currentVoiceSettings.clone_jobs);
        }
        if (path === "/api/v1/admin/robot/voice-clones" && method === "POST") {
          const form = init?.body as FormData;
          requests.push({
            path,
            method,
            body: {
              voice_id: form.get("voice_id"),
              voice_name: form.get("voice_name"),
              authorization_confirmed: form.get("authorization_confirmed"),
              source_audio_name: (form.get("source_audio") as File).name,
            },
          });
          const job: VoiceCloneJobFixture = {
            id: "clone-job-1",
            status: "succeeded",
            provider: "minimax",
            voice_id: String(form.get("voice_id")),
            voice_name: String(form.get("voice_name")),
            source_filename: "sample.wav",
            source_size_bytes: 12,
            source_content_type: "audio/wav",
            prompt_filename: null,
            provider_file_id: "file-voice-1",
            provider_prompt_file_id: null,
            preview_audio_url: null,
            error: null,
            created_at: "2026-09-13T00:00:00Z",
          };
          currentVoiceSettings = {
            ...currentVoiceSettings,
            default_voice_id: job.voice_id,
            voices: [
              ...currentVoiceSettings.voices,
            {
              id: job.voice_id,
              name: job.voice_name,
              provider: "minimax",
              voice_id: job.voice_id,
              description: "MiniMax Voice Clone 生成音色",
              enabled: true,
              cloned: true,
              builtin: false,
              created_at: null,
              updated_at: null,
            },
            ],
            clone_jobs: [job],
          };
          return jsonResponse(job, { status: 201 });
        }
        return jsonResponse({});
      }),
    );
  });

  afterEach(() => {
    window.sessionStorage.clear();
    vi.unstubAllGlobals();
  });

  it("saves MiniMax settings, voice presets, and authorized clone uploads", async () => {
    const user = userEvent.setup();
    render(<TestApp initialPath="/voice-models" />);

    expect(await screen.findByRole("heading", { name: "语音模型" })).not.toBeNull();

    await user.click(screen.getByLabelText("启用服务端 ASR/TTS"));
    await user.selectOptions(screen.getByLabelText("语音供应商"), "minimax");
    await user.type(screen.getByLabelText("MiniMax API Key"), "minimax-live-key");
    await user.selectOptions(screen.getByLabelText("TTS 模型"), "speech-2.8-hd");
    await user.selectOptions(screen.getByLabelText("默认音色"), "Chinese (Mandarin)_Warm_Girl");
    await user.click(screen.getByLabelText("允许控制台发起声音克隆"));
    await user.click(screen.getByLabelText("必须命中唤醒词才触发 Agent"));
    await user.type(screen.getByLabelText("唤醒词"), "小立方,你好立方");
    await user.click(screen.getByRole("button", { name: "保存语音模型配置" }));

    await waitFor(() => {
      expect(requests.find((request) => request.path === "/api/v1/admin/robot/voice-settings")).toMatchObject({
        method: "PUT",
        body: {
          enabled: true,
          media_provider: "minimax",
          minimax_api_key: "minimax-live-key",
          minimax_tts_model: "speech-2.8-hd",
          minimax_tts_voice_id: "Chinese (Mandarin)_Warm_Girl",
          default_voice_id: "Chinese (Mandarin)_Warm_Girl",
          clone_enabled: true,
          wake_word_required: true,
          wake_words: ["小立方", "你好立方"],
        },
      });
    });

    await user.type(screen.getByLabelText("音色 ID"), "warm-voice");
    await user.type(screen.getByLabelText("音色名称"), "温和陪伴音色");
    await user.click(screen.getByRole("button", { name: "保存音色" }));

    expect(await screen.findByText("温和陪伴音色：warm-voice")).not.toBeNull();
    expect(requests.find((request) => request.path === "/api/v1/admin/robot/voices")).toMatchObject({
      method: "POST",
      body: {
        id: "warm-voice",
        name: "温和陪伴音色",
        provider: "minimax",
        voice_id: "warm-voice",
        enabled: true,
        cloned: false,
        builtin: false,
      },
    });

    await user.type(screen.getByLabelText("克隆 voice_id"), "cloned-warm");
    await user.type(screen.getByLabelText("克隆音色名称"), "克隆温和音色");
    await user.upload(
      screen.getByLabelText("源声音样本"),
      new File(["voice sample"], "sample.wav", { type: "audio/wav" }),
    );
    await user.click(screen.getByLabelText("我确认已获得声音克隆授权"));
    await user.click(screen.getByRole("button", { name: "上传并克隆音色" }));

    expect(await screen.findByText("克隆温和音色")).not.toBeNull();
    expect(screen.getByRole("option", { name: "克隆温和音色 - cloned-warm" })).not.toBeNull();
    expect(requests.find((request) => request.path === "/api/v1/admin/robot/voice-clones")).toMatchObject({
      method: "POST",
      body: {
        voice_id: "cloned-warm",
        voice_name: "克隆温和音色",
        authorization_confirmed: "true",
        source_audio_name: "sample.wav",
      },
    });
  });
});
