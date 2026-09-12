import { z } from "zod";

const PrincipalSchema = z.object({
  user_id: z.string(),
  tenant_id: z.string(),
  role: z.string(),
});

const MeSchema = z.object({
  user_id: z.string(),
  tenant_id: z.string(),
  username: z.string(),
  role: z.string(),
  permissions: z.array(z.string()),
});

export type CurrentUser = z.infer<typeof MeSchema>;

const TokenResponseSchema = z.object({
  access_token: z.string(),
  token_type: z.string(),
  principal: PrincipalSchema,
});

type Principal = z.infer<typeof PrincipalSchema>;

const TOKEN_STORAGE_KEY = "agent_hub_access_token";
const TENANT_STORAGE_KEY = "agent_hub_tenant_id";

const ROLE_PERMISSIONS: Record<string, string[]> = {
  super_admin: ["*"],
  admin: [
    "config:*",
    "agent:*",
    "skill:read",
    "skill:use",
    "skill:write",
    "skill:approve",
    "mcp:read",
    "mcp:use",
    "mcp:write",
    "memory:*",
    "hermes:*",
    "cognition:*",
    "run:*",
    "plugin:read",
    "plugin:use",
    "plugin:write",
    "user:read",
    "user:write",
    "audit:read",
  ],
  operator: [
    "run:create",
    "run:read",
    "run:pause",
    "run:resume",
    "run:cancel",
    "config:read",
    "skill:read",
    "skill:use",
    "mcp:read",
    "mcp:use",
    "plugin:read",
    "plugin:use",
    "cognition:read",
  ],
  viewer: [
    "run:read",
    "config:read",
    "skill:read",
    "skill:use",
    "mcp:read",
    "mcp:use",
    "plugin:read",
    "plugin:use",
  ],
};

const EvidenceRefSchema = z.object({
  kind: z.string(),
  ref_id: z.string(),
  summary: z.string(),
});

function safeSessionGet(key: string): string | null {
  try {
    return window.sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeSessionSet(key: string, value: string): void {
  try {
    window.sessionStorage.setItem(key, value);
  } catch {
    // Ignore storage failures; the in-memory token still works for the current page lifetime.
  }
}

function safeSessionRemove(key: string): void {
  try {
    window.sessionStorage.removeItem(key);
  } catch {
    // Ignore storage failures.
  }
}

let accessToken = safeSessionGet(TOKEN_STORAGE_KEY);

function currentAccessToken(): string | null {
  return accessToken ?? safeSessionGet(TOKEN_STORAGE_KEY);
}

function principalToCurrentUser(principal: Principal): CurrentUser {
  return {
    user_id: principal.user_id,
    tenant_id: principal.tenant_id,
    username: `${principal.role}:${principal.user_id.slice(0, 8)}`,
    role: principal.role,
    permissions: ROLE_PERMISSIONS[principal.role] ?? [],
  };
}

function archiveContentType(filename: string): string {
  const lowered = filename.toLowerCase();
  if (lowered.endsWith(".zip")) return "application/zip";
  if (lowered.endsWith(".tar")) return "application/x-tar";
  if (lowered.endsWith(".tar.gz") || lowered.endsWith(".tgz")) return "application/gzip";
  return "application/octet-stream";
}
function encodedFilenameHeader(filename: string): { encoded: string; encoding: "percent" } {
  return { encoded: encodeURIComponent(filename), encoding: "percent" };
}

function rememberSession(token: string, principal: Principal): CurrentUser {
  accessToken = token;
  safeSessionSet(TOKEN_STORAGE_KEY, token);
  safeSessionSet(TENANT_STORAGE_KEY, principal.tenant_id);
  return principalToCurrentUser(principal);
}

function clearSession(): void {
  accessToken = null;
  safeSessionRemove(TOKEN_STORAGE_KEY);
  safeSessionRemove(TENANT_STORAGE_KEY);
}

export function rememberedTenantId(): string {
  return safeSessionGet(TENANT_STORAGE_KEY) ?? "";
}

const UserSchema = z.object({
  id: z.string(),
  username: z.string(),
  role: z.string(),
  disabled: z.boolean(),
  feishu_open_id: z.string().nullable(),
  protected: z.boolean(),
});

export type ManagedUser = z.infer<typeof UserSchema>;

const ModelDeploymentSchema = z.object({
  id: z.string(),
  provider: z.string(),
  api_base: z.string(),
  api_protocol: z.enum(["openai_compatible", "anthropic_messages"]).default("openai_compatible"),
  upstream_model: z.string(),
  logical_model: z.string(),
  capabilities: z.array(z.string()),
  credential_ref: z.string(),
  quota_scope: z.string(),
  max_concurrency: z.number(),
  target_utilization: z.number(),
  reserved_capacity: z.number(),
  rpm: z.number().nullable(),
  tpm: z.number().nullable(),
  queue_timeout_seconds: z.number(),
  fallback: z.string().nullable(),
  weight: z.number(),
  effective_slots: z.number(),
  saturation_policy: z.string(),
});

export type ModelDeployment = z.infer<typeof ModelDeploymentSchema>;

const SecretReferenceSchema = z.object({
  ref: z.string(),
  last_four: z.string(),
});

export type SecretReference = z.infer<typeof SecretReferenceSchema>;

const DiffSchema = z.object({
  added: z.array(z.string()),
  removed: z.array(z.string()),
  changed: z.array(z.string()),
});

export type ConfigDiff = z.infer<typeof DiffSchema>;

const NamedResourceSchema = z.object({
  id: z.string(),
  name: z.string(),
  enabled: z.boolean(),
  role: z.string().nullable().optional(),
  prompt: z.string().nullable().optional(),
  model: z.string().nullable().optional(),
  skills: z.array(z.string()).optional(),
});

export type NamedResource = z.infer<typeof NamedResourceSchema>;

const WorkflowResourceSchema = NamedResourceSchema.extend({
  mode: z.enum(["auto", "direct", "dispatch", "discuss", "hybrid"]).nullable().optional(),
  task_type: z.string().nullable().optional(),
  allow_main_agent_override: z.boolean().default(false),
  allow_temporary_agents: z.boolean().default(false),
  temporary_agent_policy: z.string().nullable().optional(),
  role_selection_policy: z.string().nullable().optional(),
  agent_ids: z.array(z.string()).optional(),
  objective: z.string().nullable().optional(),
  steps: z.array(z.string()).optional(),
  deliverables: z.array(z.string()).optional(),
  decision_policy: z.string().nullable().optional(),
});

export type WorkflowResource = z.infer<typeof WorkflowResourceSchema>;

const OpenClawRemoteAdapterConfigSchema = z.object({
  platform: z.enum(["linux", "windows", "macos"]),
  target_type: z.enum(["server", "computer", "desktop", "filesystem", "screen"]),
  target: z.string(),
  base_url: z.string(),
  credential_ref: z.string(),
});

const RobotVoicePresetSchema = z.object({
  id: z.string(),
  name: z.string(),
  provider: z.literal("minimax").default("minimax"),
  voice_id: z.string(),
  description: z.string().nullable().optional(),
  enabled: z.boolean().default(true),
  cloned: z.boolean().default(false),
  builtin: z.boolean().default(false),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});

export type RobotVoicePreset = z.infer<typeof RobotVoicePresetSchema>;

const RobotVoiceCloneJobSchema = z.object({
  id: z.string(),
  status: z.enum(["succeeded", "failed"]),
  provider: z.literal("minimax").default("minimax"),
  voice_id: z.string(),
  voice_name: z.string(),
  source_filename: z.string(),
  source_size_bytes: z.number(),
  source_content_type: z.string(),
  prompt_filename: z.string().nullable().optional(),
  provider_file_id: z.string().nullable().optional(),
  provider_prompt_file_id: z.string().nullable().optional(),
  preview_audio_url: z.string().nullable().optional(),
  error: z.string().nullable().optional(),
  created_at: z.string(),
});

export type RobotVoiceCloneJob = z.infer<typeof RobotVoiceCloneJobSchema>;

const RobotVoiceSettingsSchema = z.object({
  configured: z.boolean().default(false),
  enabled: z.boolean().default(false),
  media_provider: z.enum(["disabled", "minimax"]).default("disabled"),
  minimax_credential_ref: z.string().nullable().default(null),
  minimax_api_key: z.string().optional(),
  minimax_api_key_configured: z.boolean().default(false),
  minimax_api_base_url: z.string().default("https://api.minimax.io"),
  minimax_asr_model: z.string().default("asr-1.0"),
  minimax_tts_model: z.string().default("speech-2.8-turbo"),
  minimax_tts_voice_id: z.string().nullable().default(null),
  minimax_tts_audio_format: z.enum(["mp3", "wav", "flac", "pcm", "opus"]).default("mp3"),
  minimax_tts_sample_rate_hz: z.number().default(32000),
  minimax_tts_bitrate: z.number().default(128000),
  minimax_tts_language_boost: z.string().default("auto"),
  minimax_tts_speed: z.number().default(1),
  minimax_tts_volume: z.number().default(1),
  minimax_tts_pitch: z.number().default(0),
  default_voice_id: z.string().nullable().default(null),
  voices: z.array(RobotVoicePresetSchema).default([]),
  clone_enabled: z.boolean().default(false),
  clone_model: z.string().default("speech-2.8-hd"),
  clone_preview_text: z.string().default("你好，我是你的语音机器人。"),
  clone_prompt_text: z.string().nullable().default(null),
  clone_jobs: z.array(RobotVoiceCloneJobSchema).default([]),
});

const DEFAULT_ROBOT_VOICE_SETTINGS: z.infer<typeof RobotVoiceSettingsSchema> = {
  configured: false,
  enabled: false,
  media_provider: "disabled",
  minimax_credential_ref: null,
  minimax_api_key_configured: false,
  minimax_api_base_url: "https://api.minimax.io",
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
  voices: [],
  clone_enabled: false,
  clone_model: "speech-2.8-hd",
  clone_preview_text: "你好，我是你的语音机器人。",
  clone_prompt_text: null,
  clone_jobs: [],
};

const SystemSettingsSchema = z.object({
  default_mode: z.enum(["auto", "direct", "dispatch", "discuss", "hybrid"]),
  default_workflow_id: z.string().nullable(),
  default_agent_ids: z.array(z.string()),
  log_level: z.enum(["warning", "error"]),
  hermes_enabled: z.boolean(),
  safe_tools_enabled: z.boolean(),
  require_approval_for_tools: z.boolean(),
  allow_main_agent_override: z.boolean().default(false),
  allow_temporary_agents: z.boolean().default(false),
  vibe_coding_enabled: z.boolean().default(false),
  multimedia_generation_enabled: z.boolean().default(false),
  openclaw_enabled: z.boolean().default(false),
  openclaw_mode: z.enum(["ask", "read_only", "auto_review", "trusted_auto"]).default("ask"),
  openclaw_allowed_commands: z.array(z.array(z.string())).default([]),
  openclaw_remote_adapters: z.array(OpenClawRemoteAdapterConfigSchema).default([]),
  temporary_agent_policy: z.string().default(
    "主 Agent 发现角色池缺少必要能力时，必须先说明原因并取得用户确认，再临时加入子 Agent。",
  ),
  channel_entry: z.string(),
  attachment_retention_days: z.number(),
  attachment_max_mb: z.number(),
  robot_voice: RobotVoiceSettingsSchema.default(DEFAULT_ROBOT_VOICE_SETTINGS),
});

export type SystemSettings = z.infer<typeof SystemSettingsSchema>;
export type RobotVoiceSettings = z.infer<typeof RobotVoiceSettingsSchema>;

export type RobotVoiceCloneUpload = {
  voice_id: string;
  voice_name: string;
  authorization_confirmed: boolean;
  source_audio: File;
  prompt_audio?: File | null;
};

const OpenClawOperationRequestSchema = z.object({
  platform: z.enum(["linux", "windows", "macos"]),
  kind: z.enum(["server_command", "desktop_action", "screen_read", "file_read"]),
  target: z.string(),
  argv: z.array(z.string()),
  risk_level: z.enum(["low", "medium", "high"]),
  reason: z.string(),
  session_id: z.string().optional(),
});

export type OpenClawOperationRequest = z.infer<typeof OpenClawOperationRequestSchema>;

const OpenClawOperationSchema = z.object({
  id: z.string(),
  status: z.enum(["waiting_user_approval", "approved", "rejected", "executed"]),
  approval_id: z.string(),
  requires_user_approval: z.boolean(),
  platform: z.string(),
  kind: z.string(),
  operation: z.record(z.string(), z.unknown()),
  approval_summary: z.string(),
  requested_by: z.string(),
  created_at: z.string(),
  resolved_by: z.string().nullable().optional(),
  resolved_at: z.string().nullable().optional(),
  execution: z.record(z.string(), z.unknown()).nullable().optional(),
});

export type OpenClawOperation = z.infer<typeof OpenClawOperationSchema>;

const OpenClawExecutionSchema = z.object({
  operation: OpenClawOperationSchema,
  exit_code: z.number(),
  stdout: z.string(),
  stderr: z.string(),
  truncated: z.boolean(),
});

export type OpenClawExecution = z.infer<typeof OpenClawExecutionSchema>;

const OpenClawAdapterSchema = z.object({
  platform: z.enum(["linux", "windows", "macos"]),
  kind: z.enum(["server_command", "desktop_action", "screen_read", "file_read"]),
  target_type: z.enum(["server", "computer", "desktop", "filesystem", "screen"]),
  status: z.enum(["available", "adapter_unavailable"]),
  execution_host: z.string(),
  requires_user_approval: z.boolean(),
  supports_read_only: z.boolean(),
  description: z.string(),
});

export type OpenClawAdapter = z.infer<typeof OpenClawAdapterSchema>;

const OpenClawSessionRequestSchema = z.object({
  platform: z.enum(["linux", "windows", "macos"]),
  target_type: z.enum(["server", "computer", "desktop"]),
  target: z.string(),
  purpose: z.string(),
});

export type OpenClawSessionRequest = z.infer<typeof OpenClawSessionRequestSchema>;

const OpenClawSessionSchema = z.object({
  id: z.string(),
  status: z.enum(["active", "paused", "stopped", "adapter_unavailable"]),
  adapter_status: z.enum(["available", "adapter_unavailable"]),
  mode: z.enum(["ask", "read_only", "auto_review", "trusted_auto"]),
  platform: z.string(),
  target_type: z.string(),
  target: z.string(),
  purpose: z.string(),
  execution_host: z.string(),
  requested_by: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
  stopped_at: z.string().nullable().optional(),
  operation_ids: z.array(z.string()),
});

export type OpenClawSession = z.infer<typeof OpenClawSessionSchema>;


const EvolutionRoundSchema = z.object({
  round: z.number(),
  changed_dimension: z.string(),
  candidate_summary: z.string(),
  score_before: z.number(),
  score_after: z.number(),
  delta: z.number(),
  tests_passed: z.boolean(),
  regression_detected: z.boolean(),
  accepted: z.boolean(),
  recommendation: z.string(),
  stop_reason: z.string().nullable(),
  judge_summary: z.string(),
  artifact_refs: z.array(z.string()),
  tokens_used: z.number(),
  elapsed_seconds: z.number(),
  created_at: z.string(),
});

const EvolutionNextRoundPlanSchema = z.object({
  run_id: z.string(),
  round: z.number(),
  action: z.string(),
  task_title: z.string(),
  task_prompt: z.string(),
  baseline_agent_id: z.string(),
  candidate_agent_ids: z.array(z.string()),
  evaluator_agent_id: z.string(),
  memory_policy: z.string(),
  required_output_schema: z.record(z.string(), z.string()),
  previous_rounds: z.array(z.string()),
});

const EvolutionNextRoundExecutionSchema = z.object({
  evolution_run_id: z.string(),
  round: z.number(),
  action: z.string(),
  execution_run_id: z.string(),
  execution_conversation_id: z.string(),
  status: z.string(),
  task_title: z.string(),
  task_prompt: z.string(),
});

const EvolutionRunSchema = z.object({
  id: z.string(),
  kind: z.string(),
  title: z.string(),
  objective: z.string(),
  mode: z.string(),
  source_skill_ids: z.array(z.string()),
  source_conversation_id: z.string().nullable().optional().default(null),
  source_run_id: z.string().nullable().optional().default(null),
  target_artifact_type: z.string(),
  baseline_agent_id: z.string().nullable().optional().default(null),
  candidate_agent_ids: z.array(z.string()).optional().default([]),
  evaluator_agent_id: z.string().nullable().optional().default(null),
  approval_policy: z.string().optional().default("ask"),
  approval_status: z.string().optional().default("pending"),
  approved_by: z.string().nullable().optional().default(null),
  approved_at: z.string().nullable().optional().default(null),
  approval_note: z.string().optional().default(""),
  iteration_policy: z.string().optional().default("score_gated"),
  memory_policy: z.string().optional().default("summarize_between_rounds"),
  next_action: z.string().optional().default("request_approval"),
  status: z.string(),
  max_rounds: z.number(),
  min_delta: z.number(),
  budget_tokens: z.number(),
  budget_minutes: z.number(),
  rubric: z.array(z.string()),
  rounds: z.array(EvolutionRoundSchema),
  created_by: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
  stop_reason: z.string().nullable(),
});

export type EvolutionRun = z.infer<typeof EvolutionRunSchema>;
export type EvolutionNextRoundPlan = z.infer<typeof EvolutionNextRoundPlanSchema>;
export type EvolutionNextRoundExecution = z.infer<typeof EvolutionNextRoundExecutionSchema>;
export type EvolutionRunRequest = {
  kind: "skill_distillation" | "skill_optimization" | "media_strategy" | "academic_research" | "custom";
  title: string;
  objective: string;
  mode?: "auto" | "direct" | "dispatch" | "discuss" | "hybrid";
  source_skill_ids?: string[];
  source_conversation_id?: string | null;
  source_run_id?: string | null;
  target_artifact_type?: "skill" | "strategy" | "research_gap" | "paper_plan" | "media_plan" | "custom";
  baseline_agent_id?: string | null;
  candidate_agent_ids?: string[];
  evaluator_agent_id?: string | null;
  approval_policy?: "ask" | "auto" | "manual";
  iteration_policy?: "score_gated" | "fixed_rounds" | "manual_review";
  memory_policy?: "none" | "summarize_between_rounds" | "full_ledger";
  max_rounds?: number;
  min_delta?: number;
  budget_tokens?: number;
  budget_minutes?: number;
  rubric?: string[];
};

export type EvolutionApprovalRequest = {
  approved: boolean;
  baseline_agent_id?: string | null;
  evaluator_agent_id?: string | null;
  note?: string;
};

export type EvolutionRoundRequest = {
  changed_dimension: string;
  candidate_summary: string;
  score_before: number;
  score_after: number;
  tests_passed?: boolean;
  regression_detected?: boolean;
  accepted?: boolean | null;
  judge_summary?: string;
  artifact_refs?: string[];
  tokens_used?: number;
  elapsed_seconds?: number;
};
const MainAgentModelConfigSchema = z.object({
  provider: z.string(),
  api_base: z.string(),
  api_protocol: z.enum(["openai_compatible", "anthropic_messages"]),
  upstream_model: z.string(),
  credential_ref: z.string(),
  capabilities: z.array(z.string()),
  max_concurrency: z.number().default(1),
});

const MainAgentConfigSchema = z.object({
  model: MainAgentModelConfigSchema.nullable(),
  control_mode: z.enum(["supervisor", "planner", "reviewer", "autonomous"]),
  decision_policy: z.string(),
  operating_style: z.string().default("control the room, clarify goals, choose mode and roles, decide conflicts, review failures"),
  direct_answerer: z.string().default("main_agent"),
  hermes_policy: z.enum(["off", "observe", "suggest", "confirm_before_apply"]),
  max_review_rounds: z.number(),
});

export type MainAgentConfig = z.infer<typeof MainAgentConfigSchema>;

const ConfigRevisionSchema = z.object({
  id: z.string(),
  version: z.number(),
  status: z.string(),
  document: z.object({
    models: z.record(z.string(), z.unknown()),
    agents: z.array(z.unknown()),
  }),
  created_by: z.string().nullable(),
  created_at: z.string(),
  notification_status: z.string().optional(),
});

export type ConfigRevision = z.infer<typeof ConfigRevisionSchema>;

const RunListItemSchema = z.object({
  id: z.string(),
  status: z.string(),
  mode: z.string(),
  conversation_id: z.string().nullable().optional(),
  request: z.string().optional(),
  created_at: z.string().nullable().optional(),
  queue_wait_ms: z.number(),
  capacity_wait_ms: z.number(),
  cost_usd: z.string(),
});

export type RunListItem = z.infer<typeof RunListItemSchema>;

const TemporaryAgentProposalSchema = z.object({
  id: z.string(),
  name: z.string(),
  role: z.string(),
  prompt: z.string(),
  reason: z.string(),
  missing_capability: z.string(),
  model: z.string().optional(),
  recommended_model: z.string().optional(),
  suggested_skills: z.array(z.string()),
  permanentizable: z.boolean(),
});

const ScheduleProposalSchema = z.object({
  name: z.string(),
  message: z.string(),
  mode: z.enum(["auto", "direct", "dispatch", "discuss", "hybrid"]),
  workflow_id: z.string(),
  kind: z.enum(["one_time", "cron"]),
  timezone: z.string(),
  misfire_policy: z.enum(["fire_once", "skip"]),
  budget: z.number(),
  run_at: z.string().nullable().optional(),
  cron: z.string().nullable().optional(),
  summary: z.string(),
  metadata: z.record(z.string(), z.string()),
});

const EvolutionProposalSchema = z.object({
  kind: z.enum(["skill_distillation", "skill_optimization", "media_strategy", "academic_research", "custom"]),
  title: z.string(),
  objective: z.string(),
  mode: z.enum(["auto", "direct", "dispatch", "discuss", "hybrid"]),
  source_skill_ids: z.array(z.string()),
  source_conversation_id: z.string().nullable().optional(),
  source_run_id: z.string().nullable().optional(),
  target_artifact_type: z.enum(["skill", "strategy", "research_gap", "paper_plan", "media_plan", "custom"]),
  baseline_agent_id: z.string().nullable().optional(),
  candidate_agent_ids: z.array(z.string()).default([]),
  evaluator_agent_id: z.string().nullable().optional(),
  approval_policy: z.enum(["ask", "auto", "manual"]),
  iteration_policy: z.enum(["score_gated", "fixed_rounds", "manual_review"]),
  memory_policy: z.enum(["none", "summarize_between_rounds", "full_ledger"]),
  max_rounds: z.number(),
  min_delta: z.number(),
  budget_tokens: z.number(),
  budget_minutes: z.number(),
  rubric: z.array(z.string()),
  summary: z.string(),
  metadata: z.record(z.string(), z.string()),
});
const OpenClawProposalSchema = z.object({
  kind: z.enum(["server_command", "desktop_action", "screen_read", "file_read"]),
  platform: z.enum(["auto", "linux", "windows", "macos"]),
  target_type: z.enum(["server", "computer", "desktop", "filesystem", "screen"]),
  target: z.string(),
  operation_text: z.string(),
  source_conversation_id: z.string().nullable().optional(),
  summary: z.string(),
  metadata: z.record(z.string(), z.string()),
});
const SubmittedRunSchema = z.object({
  id: z.string(),
  tenant_id: z.string(),
  status: z.string(),
  mode: z.string().nullable(),
  decision_token: z.string().nullable(),
  version: z.number(),
  clarification_reason: z.string().nullable(),
  conversation_id: z.string().nullable().optional(),
  reference_conversation_id: z.string().nullable().optional(),
  temporary_agent_proposal: TemporaryAgentProposalSchema.nullable().optional(),
  schedule_proposal: ScheduleProposalSchema.nullable().optional(),
  evolution_proposal: EvolutionProposalSchema.nullable().optional(),
  openclaw_proposal: OpenClawProposalSchema.nullable().optional(),
});

export type SubmittedRun = z.infer<typeof SubmittedRunSchema>;

const RunArtifactSchema = z.object({
  id: z.string(),
  kind: z.string(),
  title: z.string(),
  text: z.string().nullable().optional(),
  filename: z.string().nullable().optional(),
  mime_type: z.string().nullable().optional(),
  size_bytes: z.number().nullable().optional(),
  sha256: z.string().nullable().optional(),
  download_url: z.string().nullable().optional(),
});

const RunEventSchema = z.object({
  sequence: z.number(),
  kind: z.string(),
  message: z.string(),
  created_at: z.string(),
  actor: z.string().nullable().optional(),
  participants: z.array(z.string()).default([]),
  tool_name: z.string().nullable().optional(),
  step_id: z.string().nullable().optional(),
  action: z.string().nullable().optional(),
  decision: z.string().nullable().optional(),
  payload: z.record(z.string(), z.unknown()).default({}),
  artifact: RunArtifactSchema.nullable().optional(),
});

const HermesInjectedMemorySchema = z.object({
  id: z.string(),
  summary: z.string(),
  memory_type: z.string(),
  target: z.string(),
  score: z.number(),
  reason: z.string(),
});

const HermesSkippedMemorySchema = z.object({
  id: z.string(),
  summary: z.string(),
  reason: z.string(),
  score: z.number(),
});

const RoutingDecisionSchema = z
  .object({
    hermes: z
      .object({
        injected_memories: z.array(HermesInjectedMemorySchema).default([]),
        skipped_memories: z.array(HermesSkippedMemorySchema).default([]),
      })
      .nullable()
      .optional(),
  })
  .passthrough();

const RunDetailSchema = RunListItemSchema.extend({
  request: z.string(),
  events: z.array(RunEventSchema),
  artifacts: z.array(RunArtifactSchema),
  explicit_details: z.record(z.string(), z.string()),
  routing_decision: RoutingDecisionSchema.nullable().optional(),
  decision_token: z.string().nullable().optional(),
  temporary_agent_proposal: TemporaryAgentProposalSchema.nullable().optional(),
  schedule_proposal: ScheduleProposalSchema.nullable().optional(),
  evolution_proposal: EvolutionProposalSchema.nullable().optional(),
  openclaw_proposal: OpenClawProposalSchema.nullable().optional(),
});

const RunDeleteSchema = z.object({
  id: z.string(),
  deleted: z.boolean(),
});

const BulkFailureSchema = z.object({
  id: z.string(),
  code: z.string(),
  message: z.string(),
});

const RunBulkDeleteSchema = z.object({
  deleted: z.array(RunDeleteSchema),
  failed: z.array(BulkFailureSchema),
});

export type RunDetail = z.infer<typeof RunDetailSchema>;
export type RunDeleteResult = z.infer<typeof RunDeleteSchema>;
export type BulkFailure = z.infer<typeof BulkFailureSchema>;
export type RunBulkDeleteResult = z.infer<typeof RunBulkDeleteSchema>;

const ConversationSchema = z.object({
  conversation_id: z.string(),
  runs: z.array(RunDetailSchema),
});

export type Conversation = z.infer<typeof ConversationSchema>;

const SkillVersionSchema = z.object({
  id: z.string(),
  status: z.string(),
  source_filename: z.string().nullable().optional(),
  package_version_id: z.string().nullable().optional(),
  content_sha256: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
  is_current: z.boolean(),
});

const SkillSchema = z.object({
  id: z.string(),
  name: z.string(),
  status: z.string(),
  scan_diff: z.array(z.string()),
  requested_permissions: z.array(z.string()),
  source_filename: z.string().nullable().optional(),
  package_version_id: z.string().nullable().optional(),
  content_sha256: z.string().nullable().optional(),
  current_version_id: z.string().nullable().optional(),
  versions: z.array(SkillVersionSchema).default([]),
});

export type Skill = z.infer<typeof SkillSchema>;
export type SkillVersion = z.infer<typeof SkillVersionSchema>;

const SkillBulkDeleteSchema = z.object({
  deleted: z.array(z.string()),
  failed: z.array(BulkFailureSchema),
});

export type SkillBulkDeleteResult = z.infer<typeof SkillBulkDeleteSchema>;

const SkillArchiveSkippedSchema = z.object({
  path: z.string(),
  reason: z.string(),
});

const SkillArchiveUploadSchema = z.object({
  filename: z.string(),
  bundle: z.boolean(),
  items: z.array(SkillSchema),
  skipped: z.array(SkillArchiveSkippedSchema).default([]),
});

export type SkillArchiveUpload = z.infer<typeof SkillArchiveUploadSchema>;

const AttachmentUploadSchema = z.object({
  id: z.string(),
  filename: z.string(),
  kind: z.string(),
  content_type: z.string(),
  size_bytes: z.number(),
  sha256: z.string(),
  expires_at: z.string(),
});

export type AttachmentUpload = z.infer<typeof AttachmentUploadSchema>;

const AttachmentListSchema = z.object({
  items: z.array(AttachmentUploadSchema),
});

const AttachmentDeleteSchema = z.object({
  id: z.string(),
  deleted: z.boolean(),
});

const AttachmentBulkDeleteSchema = z.object({
  deleted: z.array(z.string()),
  failed: z.array(BulkFailureSchema),
});

const MultimediaGenerationSchema = z.object({
  kind: z.enum(["image", "video", "audio"]),
  logical_model: z.string(),
  deployment_id: z.string(),
  text: z.string().nullable(),
});

export type MultimediaGeneration = z.infer<typeof MultimediaGenerationSchema>;

const ScheduleSchema = z.object({
  id: z.string(),
  name: z.string(),
  status: z.string(),
  kind: z.enum(["one_time", "cron"]),
  mode: z.enum(["auto", "direct", "dispatch", "discuss", "hybrid"]),
  workflow_id: z.string(),
  message: z.string(),
  timezone: z.string(),
  next_fire_at: z.string().nullable(),
  run_at: z.string().nullable(),
  cron: z.string().nullable(),
  misfire_policy: z.enum(["fire_once", "skip"]),
  budget: z.number(),
  metadata: z.record(z.string(), z.string()),
});

export type Schedule = z.infer<typeof ScheduleSchema>;

export type ScheduleCreatePayload = {
  name: string;
  message: string;
  mode: "auto" | "direct" | "dispatch" | "discuss" | "hybrid";
  workflow_id: string;
  kind: "one_time" | "cron";
  run_at?: string | null;
  cron?: string | null;
  timezone: string;
  misfire_policy: "fire_once" | "skip";
  budget: number;
  metadata: Record<string, string>;
};

const McpServerSchema = z.object({
  id: z.string(),
  name: z.string(),
  health: z.string(),
  allowed_tools: z.array(z.string()),
  transport: z.string().default("streamable_http"),
  command: z.string().nullable().default(null),
  args: z.array(z.string()).default([]),
  url: z.string().nullable().default(null),
  executable_allowlist: z.array(z.string()).default([]),
  domain_allowlist: z.array(z.string()).default([]),
  timeout_seconds: z.number().default(10),
});

export type McpServer = z.infer<typeof McpServerSchema>;

const ChannelRuntimeStatusSchema = z.object({
  status: z.string(),
  ready: z.boolean(),
  connection_attempts: z.number(),
  reconnects: z.number(),
  received_events: z.number(),
  submitted_messages: z.number(),
  ignored_events: z.number(),
  failures: z.number(),
  last_error_type: z.string().nullable(),
  last_error_message: z.string().nullable(),
});
const ChannelStatusSchema = z.object({
  id: z.string(),
  name: z.string(),
  status: z.string(),
  transports: z.array(z.string()),
  webhook_path: z.string().nullable(),
  public_webhook_url: z.string().nullable(),
  missing: z.array(z.string()),
  configured: z.array(z.string()).default([]),
  configured_sources: z.record(z.string(), z.string()).default({}),
  command_aliases: z.record(z.string(), z.string()).default({}),
  notes: z.array(z.string()),
  runtime: ChannelRuntimeStatusSchema.nullable().optional(),
});

export type ChannelStatus = z.infer<typeof ChannelStatusSchema>;

const ChannelConfigSaveSchema = z.object({
  id: z.string(),
  saved: z.array(z.string()),
  status: ChannelStatusSchema,
});

export type ChannelConfigSave = z.infer<typeof ChannelConfigSaveSchema>;

const MemoryRecordSchema = z.object({
  id: z.string(),
  scope: z.string(),
  value: z.string(),
  heat: z.number().default(0.5),
  locked: z.boolean().default(false),
  project_id: z.string().nullable().default(null),
  conversation_id: z.string().nullable().default(null),
  summary_period: z.enum(["none", "day", "week", "month"]).default("none"),
  recall_count: z.number().default(0),
  last_recalled_at: z.string().nullable().default(null),
});

export type MemoryRecord = z.infer<typeof MemoryRecordSchema>;

const CognitionEpisodeSchema = z.object({
  id: z.string(),
  tenant_id: z.string(),
  user_id: z.string(),
  source: z.string(),
  conversation_id: z.string().nullable().optional(),
  run_id: z.string().nullable().optional(),
  started_at: z.string(),
  ended_at: z.string().nullable().optional(),
  summary: z.string(),
  signals: z.array(z.string()).default([]),
  outcome: z.string(),
  feedback: z.string().default(""),
  evidence_refs: z.array(EvidenceRefSchema).default([]),
  privacy_level: z.string().default("normal"),
  created_at: z.string(),
});

const CognitionExperienceSchema = z.object({
  id: z.string(),
  tenant_id: z.string(),
  user_id: z.string(),
  kind: z.string(),
  statement: z.string(),
  applicability: z.string(),
  recommended_action: z.string().default(""),
  avoid_action: z.string().default(""),
  confidence: z.number(),
  evidence_refs: z.array(EvidenceRefSchema).default([]),
  contradictions: z.array(EvidenceRefSchema).default([]),
  usage_count: z.number().default(0),
  success_count: z.number().default(0),
  failure_count: z.number().default(0),
  last_used_at: z.string().nullable().optional(),
  last_verified_at: z.string().nullable().optional(),
  version: z.number(),
  status: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
});

const CognitionReflectionSchema = z.object({
  id: z.string(),
  episode_id: z.string(),
  reflection_type: z.string(),
  trigger: z.string(),
  what_happened: z.string(),
  why_it_happened: z.string(),
  better_next_time: z.string(),
  candidate_experience_ids: z.array(z.string()).default([]),
  candidate_belief_updates: z.array(z.string()).default([]),
  candidate_skill_updates: z.array(z.string()).default([]),
  confidence: z.number(),
  requires_approval: z.boolean(),
  evidence_refs: z.array(EvidenceRefSchema).default([]),
  status: z.string(),
  version: z.number(),
  created_at: z.string(),
});

const CognitionBeliefSchema = z.object({
  id: z.string(),
  tenant_id: z.string(),
  user_id: z.string(),
  subject: z.string(),
  predicate: z.string(),
  object: z.string(),
  scope: z.string(),
  confidence: z.number(),
  evidence_refs: z.array(EvidenceRefSchema).default([]),
  contradictions: z.array(EvidenceRefSchema).default([]),
  last_verified_at: z.string().nullable().optional(),
  verification_count: z.number().default(0),
  status: z.string(),
  version: z.number(),
  created_at: z.string(),
  updated_at: z.string(),
});

const CognitionRelationshipRecordSchema = z.object({
  tenant_id: z.string(),
  user_id: z.string(),
  familiarity: z.number(),
  trust: z.number(),
  rapport: z.number(),
  preferred_tone: z.string(),
  preferred_depth: z.string(),
  interaction_rhythm: z.string(),
  shared_history: z.array(z.string()).default([]),
  stable_preferences: z.array(z.string()).default([]),
  recent_changes: z.array(z.string()).default([]),
  boundaries: z.array(z.string()).default([]),
  confidence: z.number(),
  status: z.string(),
  version: z.number(),
  evidence_refs: z.array(EvidenceRefSchema).default([]),
  last_updated_at: z.string(),
});

const CognitionRelationshipSchema = z.array(CognitionRelationshipRecordSchema);

const CognitionWorldStateSchema = z.object({
  id: z.string(),
  tenant_id: z.string(),
  user_id: z.string(),
  entity_type: z.string(),
  name: z.string(),
  state: z.string(),
  status: z.string(),
  starts_at: z.string().nullable().optional(),
  due_at: z.string().nullable().optional(),
  ended_at: z.string().nullable().optional(),
  participants: z.array(z.string()).default([]),
  evidence_refs: z.array(EvidenceRefSchema).default([]),
  confidence: z.number(),
  version: z.number(),
  last_verified_at: z.string().nullable().optional(),
  created_at: z.string(),
  updated_at: z.string(),
});

const CognitiveContextBundleSchema = z.object({
  core_constraints: z.array(z.string()).default([]),
  relationship_context: z.array(z.string()).default([]),
  world_context: z.array(z.string()).default([]),
  experience_context: z.array(z.string()).default([]),
  belief_context: z.array(z.string()).default([]),
  skill_context: z.array(z.string()).default([]),
  reasons: z.array(z.string()).default([]),
});

export type CognitionEpisode = z.infer<typeof CognitionEpisodeSchema>;
export type CognitionExperience = z.infer<typeof CognitionExperienceSchema>;
export type CognitionReflection = z.infer<typeof CognitionReflectionSchema>;
export type CognitionBelief = z.infer<typeof CognitionBeliefSchema>;
export type CognitionRelationshipRecord = z.infer<typeof CognitionRelationshipRecordSchema>;
export type CognitionRelationship = z.infer<typeof CognitionRelationshipSchema>;
export type CognitionWorldState = z.infer<typeof CognitionWorldStateSchema>;
export type CognitiveContextBundle = z.infer<typeof CognitiveContextBundleSchema>;
export type CognitionRouterPreviewPayload = {
  scene: string;
  current_request: string;
  limit?: number;
};

const AuditEventSchema = z.object({
  id: z.string(),
  actor: z.string(),
  action: z.string(),
  resource: z.string(),
  details: z.record(z.string(), z.string()).default({}),
  created_at: z.string(),
});

export type AuditEvent = z.infer<typeof AuditEventSchema>;

const LogEntrySchema = z.object({
  id: z.string(),
  category: z.string(),
  level: z.string(),
  title: z.string(),
  message: z.string(),
  source: z.string(),
  details: z.record(z.string(), z.string()),
  created_at: z.string(),
});

export type LogEntry = z.infer<typeof LogEntrySchema>;

const HermesInsightSchema = z.object({
  id: z.string(),
  category: z.enum(["conversation", "scheduler"]).default("conversation"),
  outcome: z.string(),
  lesson: z.string(),
  summary: z.string(),
  user_summary: z.string().default(""),
  run_id: z.string().nullable(),
  conversation_id: z.string().nullable(),
  confirmed_at: z.string().nullable(),
  tags: z.array(z.string()),
  weight: z.number(),
  created_at: z.string(),
});

export type HermesInsight = z.infer<typeof HermesInsightSchema>;

const HermesBulkConfirmSchema = z.object({
  confirmed: z.array(HermesInsightSchema),
  failed: z.array(BulkFailureSchema),
});

export type HermesBulkConfirmResult = z.infer<typeof HermesBulkConfirmSchema>;

const HermesBulkDeleteSchema = z.object({
  deleted: z.array(z.string()),
  failed: z.array(BulkFailureSchema),
});

export type HermesBulkDeleteResult = z.infer<typeof HermesBulkDeleteSchema>;

const OperationStatusSchema = z.object({
  status: z.string(),
});

export type OperationStatus = z.infer<typeof OperationStatusSchema>;

const HermesRecommendationSchema = z.object({
  recommended_mode: z.string(),
  recommended_model: z.string().nullable(),
  recommended_skills: z.array(z.string()),
  confidence: z.number(),
  reasons: z.array(z.string()),
  requires_approval: z.boolean(),
});

export type HermesRecommendation = z.infer<typeof HermesRecommendationSchema>;

const ErrorDetailValueSchema = z.union([z.string(), z.number(), z.boolean(), z.null()]);

const ErrorEnvelopeSchema = z.object({
  error: z.union([
    z.string(),
    z.object({
      code: z.string(),
      message: z.string(),
      details: z.record(z.string(), ErrorDetailValueSchema).optional(),
    }),
  ]),
});

export type ApiErrorDetails = Record<string, string | number | boolean | null>;

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string = "request_failed",
    public readonly errorId: string | null = null,
    public readonly details: ApiErrorDetails | null = null,
  ) {
    super(message);
  }
}

export function formatApiError(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) return fallback;
  const parts = [error.code, `HTTP ${error.status}`];
  if (error.errorId) parts.push(`error ${error.errorId}`);
  return `${fallback}: ${error.message} (${parts.join(", ")})`;
}

async function errorFromResponse(response: Response): Promise<ApiError> {
  const errorId = response.headers.get("x-error-id");
  const fallbackMessage = response.statusText || "request failed";
  try {
    const payload: unknown = await response.json();
    const parsed = ErrorEnvelopeSchema.safeParse(payload);
    if (parsed.success) {
      const error = parsed.data.error;
      if (typeof error === "string") {
        return new ApiError(error || fallbackMessage, response.status, "request_failed", errorId);
      }
      return new ApiError(error.message, response.status, error.code, errorId, error.details ?? null);
    }
  } catch {
    return new ApiError(fallbackMessage, response.status, "invalid_error_response", errorId);
  }
  return new ApiError(fallbackMessage, response.status, "invalid_error_response", errorId);
}

async function request<T>(
  path: string,
  init: RequestInit,
  schema: z.ZodType<T>,
): Promise<T> {
  let response: Response;
  const token = currentAccessToken();
  try {
    response = await fetch(path, {
      ...init,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError("network request failed", 0, "network_error");
  }
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
  const payload = await response.json();
  const parsed = schema.safeParse(payload);
  if (!parsed.success) {
    throw new ApiError(
      `response schema validation failed for ${path}`,
      response.status,
      "invalid_response",
    );
  }
  return parsed.data;
}

async function requestForm<T>(
  path: string,
  formData: FormData,
  schema: z.ZodType<T>,
): Promise<T> {
  let response: Response;
  const token = currentAccessToken();
  try {
    response = await fetch(path, {
      method: "POST",
      credentials: "include",
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: formData,
    });
  } catch {
    throw new ApiError("network request failed", 0, "network_error");
  }
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
  const payload = await response.json();
  const parsed = schema.safeParse(payload);
  if (!parsed.success) {
    throw new ApiError(
      `response schema validation failed for ${path}`,
      response.status,
      "invalid_response",
    );
  }
  return parsed.data;
}

async function requestNoContent(path: string, init: RequestInit): Promise<void> {
  let response: Response;
  const token = currentAccessToken();
  try {
    response = await fetch(path, {
      ...init,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError("network request failed", 0, "network_error");
  }
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
}

async function requestBinary<T>(
  path: string,
  init: RequestInit,
  schema: z.ZodType<T>,
): Promise<T> {
  let response: Response;
  const token = currentAccessToken();
  try {
    response = await fetch(path, {
      ...init,
      credentials: "include",
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError("network request failed", 0, "network_error");
  }
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
  const payload = await response.json();
  const parsed = schema.safeParse(payload);
  if (!parsed.success) {
    throw new ApiError(
      `response schema validation failed for ${path}`,
      response.status,
      "invalid_response",
    );
  }
  return parsed.data;
}

export const api = {
  me(): Promise<CurrentUser> {
    return request("/api/v1/auth/me", { method: "GET" }, PrincipalSchema).then((principal) =>
      principalToCurrentUser(principal),
    );
  },
  login(username: string, password: string, tenant_id = ""): Promise<CurrentUser> {
    const trimmedTenantId = tenant_id.trim();
    return request(
      "/api/v1/auth/login",
      {
        method: "POST",
        body: JSON.stringify({
          ...(trimmedTenantId ? { tenant_id: trimmedTenantId } : {}),
          username,
          password,
        }),
      },
      TokenResponseSchema,
    ).then((response) => rememberSession(response.access_token, response.principal));
  },
  setup(code: string, username: string, password: string): Promise<CurrentUser> {
    return request(
      "/api/v1/setup",
      { method: "POST", body: JSON.stringify({ code, username, password }) },
      TokenResponseSchema,
    ).then((response) => rememberSession(response.access_token, response.principal));
  },
  async logout(): Promise<void> {
    clearSession();
  },
  users(): Promise<ManagedUser[]> {
    return request("/api/v1/users", { method: "GET" }, z.array(UserSchema));
  },
  changeUserRole(userId: string, role: string): Promise<ManagedUser> {
    return request(
      `/api/v1/users/${userId}/role`,
      { method: "PATCH", body: JSON.stringify({ role }) },
      UserSchema,
    );
  },
  createUser(payload: { username: string; password: string; role: string }): Promise<ManagedUser> {
    return request(
      "/api/v1/users",
      { method: "POST", body: JSON.stringify(payload) },
      UserSchema,
    );
  },
  updateUser(
    userId: string,
    payload: { username?: string; role?: string; disabled?: boolean },
  ): Promise<ManagedUser> {
    return request(
      `/api/v1/users/${userId}`,
      { method: "PATCH", body: JSON.stringify(payload) },
      UserSchema,
    );
  },
  setUserDisabled(userId: string, disabled: boolean): Promise<ManagedUser> {
    return request(
      `/api/v1/users/${userId}/disabled`,
      { method: "PATCH", body: JSON.stringify({ disabled }) },
      UserSchema,
    );
  },
  resetUserPassword(userId: string, password: string): Promise<ManagedUser> {
    return request(
      `/api/v1/users/${userId}/password`,
      { method: "PATCH", body: JSON.stringify({ password }) },
      UserSchema,
    );
  },
  bindUserFeishu(userId: string, openId: string): Promise<ManagedUser> {
    return request(
      `/api/v1/users/${userId}/feishu`,
      { method: "PATCH", body: JSON.stringify({ open_id: openId }) },
      UserSchema,
    );
  },
  unbindUserFeishu(userId: string): Promise<ManagedUser> {
    return request(
      `/api/v1/users/${userId}/feishu`,
      { method: "DELETE" },
      UserSchema,
    );
  },
  async deleteUser(userId: string): Promise<void> {
    await requestNoContent(`/api/v1/users/${userId}`, { method: "DELETE" });
  },
  models(): Promise<ModelDeployment[]> {
    return request("/api/v1/admin/models", { method: "GET" }, z.array(ModelDeploymentSchema));
  },
  createModel(payload: Omit<ModelDeployment, "id" | "effective_slots" | "saturation_policy">) {
    return request(
      "/api/v1/admin/models",
      { method: "POST", body: JSON.stringify(payload) },
      ModelDeploymentSchema,
    );
  },
  updateModel(id: string, payload: Omit<ModelDeployment, "id" | "effective_slots" | "saturation_policy">) {
    return request(
      `/api/v1/admin/models/${encodeURIComponent(id)}`,
      { method: "PUT", body: JSON.stringify(payload) },
      ModelDeploymentSchema,
    );
  },
  async deleteModel(id: string): Promise<void> {
    await requestNoContent(`/api/v1/admin/models/${encodeURIComponent(id)}`, { method: "DELETE" });
  },
  createSecret(label: string, value: string): Promise<SecretReference> {
    return request(
      "/api/v1/admin/secrets",
      { method: "POST", body: JSON.stringify({ label, value }) },
      SecretReferenceSchema,
    );
  },
  probeModel(quota_scope: string, desired_concurrency: number) {
    return request(
      "/api/v1/admin/models/probe",
      { method: "POST", body: JSON.stringify({ quota_scope, desired_concurrency }) },
      z.object({ recommended_concurrency: z.number(), warning: z.string() }),
    );
  },
  diffConfig(yaml: string): Promise<ConfigDiff> {
    return request(
      "/api/v1/admin/config/diff",
      { method: "POST", body: JSON.stringify({ yaml }) },
      DiffSchema,
    );
  },
  publishConfig(expected_version: number) {
    return request(
      "/api/v1/admin/config/publish",
      { method: "POST", body: JSON.stringify({ expected_version }) },
      z.object({ version: z.number(), status: z.string() }),
    );
  },
  currentConfig(): Promise<ConfigRevision> {
    return request("/api/v1/config/current", { method: "GET" }, ConfigRevisionSchema);
  },
  createConfigDraft(document: { agents: unknown[]; models: Record<string, unknown> }) {
    return request(
      "/api/v1/config/drafts",
      { method: "POST", body: JSON.stringify(document) },
      ConfigRevisionSchema,
    );
  },
  publishConfigDraft(revisionId: string) {
    return request(
      `/api/v1/config/drafts/${revisionId}/publish`,
      { method: "POST" },
      ConfigRevisionSchema,
    );
  },
  agents(): Promise<NamedResource[]> {
    return request("/api/v1/admin/agents", { method: "GET" }, z.array(NamedResourceSchema));
  },
  createAgent(payload: NamedResource): Promise<NamedResource> {
    return request(
      "/api/v1/admin/agents",
      { method: "POST", body: JSON.stringify(payload) },
      NamedResourceSchema,
    );
  },
  deleteAgent(id: string): Promise<{ status: string }> {
    return request(
      `/api/v1/admin/agents/${encodeURIComponent(id)}`,
      { method: "DELETE" },
      z.object({ status: z.string() }),
    );
  },
  workflows(): Promise<WorkflowResource[]> {
    return request(
      "/api/v1/admin/workflows",
      { method: "GET" },
      z.array(WorkflowResourceSchema),
    );
  },
  createWorkflow(payload: WorkflowResource): Promise<WorkflowResource> {
    return request(
      "/api/v1/admin/workflows",
      { method: "POST", body: JSON.stringify(payload) },
      WorkflowResourceSchema,
    );
  },
  deleteWorkflow(id: string): Promise<{ status: string }> {
    return request(
      `/api/v1/admin/workflows/${encodeURIComponent(id)}`,
      { method: "DELETE" },
      z.object({ status: z.string() }),
    );
  },
  settings(): Promise<SystemSettings> {
    return request("/api/v1/admin/settings", { method: "GET" }, SystemSettingsSchema);
  },
  updateSettings(payload: SystemSettings): Promise<SystemSettings> {
    return request(
      "/api/v1/admin/settings",
      { method: "PUT", body: JSON.stringify(payload) },
      SystemSettingsSchema,
    );
  },
  robotVoiceSettings(): Promise<RobotVoiceSettings> {
    return request(
      "/api/v1/admin/robot/voice-settings",
      { method: "GET" },
      RobotVoiceSettingsSchema,
    );
  },
  updateRobotVoiceSettings(payload: RobotVoiceSettings): Promise<RobotVoiceSettings> {
    return request(
      "/api/v1/admin/robot/voice-settings",
      { method: "PUT", body: JSON.stringify(payload) },
      RobotVoiceSettingsSchema,
    );
  },
  createRobotVoicePreset(payload: RobotVoicePreset): Promise<RobotVoiceSettings> {
    return request(
      "/api/v1/admin/robot/voices",
      { method: "POST", body: JSON.stringify(payload) },
      RobotVoiceSettingsSchema,
    );
  },
  deleteRobotVoicePreset(id: string): Promise<RobotVoiceSettings> {
    return request(
      `/api/v1/admin/robot/voices/${encodeURIComponent(id)}`,
      { method: "DELETE" },
      RobotVoiceSettingsSchema,
    );
  },
  robotVoiceCloneJobs(): Promise<RobotVoiceCloneJob[]> {
    return request(
      "/api/v1/admin/robot/voice-clones",
      { method: "GET" },
      z.array(RobotVoiceCloneJobSchema),
    );
  },
  createRobotVoiceClone(payload: RobotVoiceCloneUpload): Promise<RobotVoiceCloneJob> {
    const formData = new FormData();
    formData.set("voice_id", payload.voice_id);
    formData.set("voice_name", payload.voice_name);
    formData.set("authorization_confirmed", String(payload.authorization_confirmed));
    formData.set("source_audio", payload.source_audio);
    if (payload.prompt_audio) formData.set("prompt_audio", payload.prompt_audio);
    return requestForm(
      "/api/v1/admin/robot/voice-clones",
      formData,
      RobotVoiceCloneJobSchema,
    );
  },
  createOpenClawOperationFromRun(runId: string): Promise<OpenClawOperation> {
    return request(
      `/api/v1/admin/openclaw/operations/from-run/${encodeURIComponent(runId)}`,
      { method: "POST" },
      OpenClawOperationSchema,
    );
  },
  createOpenClawOperation(payload: OpenClawOperationRequest): Promise<OpenClawOperation> {
    return request(
      "/api/v1/admin/openclaw/operations",
      { method: "POST", body: JSON.stringify(payload) },
      OpenClawOperationSchema,
    );
  },
  resolveOpenClawOperation(id: string, decision: "approve" | "reject"): Promise<OpenClawOperation> {
    return request(
      `/api/v1/admin/openclaw/operations/${encodeURIComponent(id)}`,
      { method: "PATCH", body: JSON.stringify({ decision }) },
      OpenClawOperationSchema,
    );
  },
  executeOpenClawOperation(id: string): Promise<OpenClawExecution> {
    return request(
      `/api/v1/admin/openclaw/operations/${encodeURIComponent(id)}/execute`,
      { method: "POST" },
      OpenClawExecutionSchema,
    );
  },
  openClawAdapters(): Promise<OpenClawAdapter[]> {
    return request(
      "/api/v1/admin/openclaw/adapters",
      { method: "GET" },
      z.array(OpenClawAdapterSchema),
    );
  },
  createOpenClawSession(payload: OpenClawSessionRequest): Promise<OpenClawSession> {
    return request(
      "/api/v1/admin/openclaw/sessions",
      { method: "POST", body: JSON.stringify(payload) },
      OpenClawSessionSchema,
    );
  },
  openClawSessions(): Promise<OpenClawSession[]> {
    return request(
      "/api/v1/admin/openclaw/sessions",
      { method: "GET" },
      z.array(OpenClawSessionSchema),
    );
  },
  updateOpenClawSession(id: string, action: "pause" | "resume" | "stop"): Promise<OpenClawSession> {
    return request(
      `/api/v1/admin/openclaw/sessions/${encodeURIComponent(id)}`,
      { method: "PATCH", body: JSON.stringify({ action }) },
      OpenClawSessionSchema,
    );
  },
  evolutionRuns(): Promise<EvolutionRun[]> {
    return request("/api/v1/admin/evolution-runs", { method: "GET" }, z.array(EvolutionRunSchema));
  },
  createEvolutionRun(payload: EvolutionRunRequest): Promise<EvolutionRun> {
    return request(
      "/api/v1/admin/evolution-runs",
      { method: "POST", body: JSON.stringify(payload) },
      EvolutionRunSchema,
    );
  },
  evolutionNextRoundPlan(id: string): Promise<EvolutionNextRoundPlan> {
    return request(
      `/api/v1/admin/evolution-runs/${encodeURIComponent(id)}/next-round-plan`,
      { method: "GET" },
      EvolutionNextRoundPlanSchema,
    );
  },
  executeEvolutionNextRound(id: string): Promise<EvolutionNextRoundExecution> {
    return request(
      `/api/v1/admin/evolution-runs/${encodeURIComponent(id)}/execute-next-round`,
      { method: "POST" },
      EvolutionNextRoundExecutionSchema,
    );
  },
  ingestEvolutionExecutionRun(id: string, executionRunId: string): Promise<EvolutionRun> {
    return request(
      `/api/v1/admin/evolution-runs/${encodeURIComponent(id)}/execution-runs/${encodeURIComponent(executionRunId)}/ingest`,
      { method: "POST" },
      EvolutionRunSchema,
    );
  },
  approveEvolutionRun(id: string, payload: EvolutionApprovalRequest): Promise<EvolutionRun> {
    return request(
      `/api/v1/admin/evolution-runs/${encodeURIComponent(id)}/approve`,
      { method: "POST", body: JSON.stringify(payload) },
      EvolutionRunSchema,
    );
  },
  recordEvolutionRound(id: string, payload: EvolutionRoundRequest): Promise<EvolutionRun> {
    return request(
      `/api/v1/admin/evolution-runs/${encodeURIComponent(id)}/rounds`,
      { method: "POST", body: JSON.stringify(payload) },
      EvolutionRunSchema,
    );
  },
  mainAgent(): Promise<MainAgentConfig> {
    return request("/api/v1/admin/main-agent", { method: "GET" }, MainAgentConfigSchema);
  },
  updateMainAgent(
    payload: MainAgentConfig,
  ): Promise<MainAgentConfig> {
    return request(
      "/api/v1/admin/main-agent",
      { method: "PUT", body: JSON.stringify(payload) },
      MainAgentConfigSchema,
    );
  },
  createRun(payload: {
    message: string;
    mode: "auto" | "direct" | "dispatch" | "discuss" | "hybrid";
    agent_ids?: string[];
    direct_model?: string | null;
    workflow_id?: string | null;
    allow_workflow_adjustment?: boolean;
    conversation_id?: string | null;
    reference_conversation_id?: string | null;
    attachment_ids?: string[];
    vibe_coding?: boolean;
    skip_evolution_proposal?: boolean;
  }): Promise<SubmittedRun> {
    return request(
      "/api/v1/runs",
      { method: "POST", body: JSON.stringify(payload) },
      SubmittedRunSchema,
    );
  },
  uploadAttachment(file: File): Promise<AttachmentUpload> {
    const filename = encodedFilenameHeader(file.name);
    return requestBinary(
      "/api/v1/runs/attachments/upload",
      {
        method: "POST",
        body: file,
        headers: {
          "Content-Type": file.type || "application/octet-stream",
          "X-Agent-Hub-Filename": filename.encoded,
          "X-Agent-Hub-Filename-Encoding": filename.encoding,
        },
      },
      AttachmentUploadSchema,
    );
  },
  attachments(): Promise<AttachmentUpload[]> {
    return request("/api/v1/runs/attachments", { method: "GET" }, AttachmentListSchema).then((result) => result.items);
  },
  deleteAttachment(id: string): Promise<{ id: string; deleted: boolean }> {
    return request(
      `/api/v1/runs/attachments/${encodeURIComponent(id)}`,
      { method: "DELETE" },
      AttachmentDeleteSchema,
    );
  },
  bulkDeleteAttachments(ids: string[]): Promise<{ deleted: string[]; failed: { id: string; code: string; message: string }[] }> {
    return request(
      "/api/v1/runs/attachments/bulk-delete",
      { method: "POST", body: JSON.stringify({ ids }) },
      AttachmentBulkDeleteSchema,
    );
  },
  generateMultimedia(payload: {
    kind: "image" | "video" | "audio";
    logical_model: string;
    prompt: string;
  }): Promise<MultimediaGeneration> {
    return request(
      "/api/v1/admin/multimedia/generate",
      { method: "POST", body: JSON.stringify(payload) },
      MultimediaGenerationSchema,
    );
  },
  schedules(): Promise<Schedule[]> {
    return request("/api/v1/admin/schedules", { method: "GET" }, z.array(ScheduleSchema));
  },
  createSchedule(payload: ScheduleCreatePayload): Promise<Schedule> {
    return request(
      "/api/v1/admin/schedules",
      { method: "POST", body: JSON.stringify(payload) },
      ScheduleSchema,
    );
  },
  tickSchedules(now: string): Promise<{ fired: string[] }> {
    return request(
      "/api/v1/admin/schedules/tick",
      { method: "POST", body: JSON.stringify({ now }) },
      z.object({ fired: z.array(z.string()) }),
    );
  },
  deleteSchedule(id: string): Promise<{ id: string; deleted: boolean }> {
    return request(
      `/api/v1/admin/schedules/${encodeURIComponent(id)}`,
      { method: "DELETE" },
      z.object({ id: z.string(), deleted: z.boolean() }),
    );
  },
  chooseMode(
    id: string,
    payload: {
      mode: "direct" | "dispatch" | "discuss" | "hybrid";
      decision_token: string;
      version: number;
      operator_note?: string;
    },
  ): Promise<SubmittedRun> {
    return request(
      `/api/v1/runs/${encodeURIComponent(id)}/choose-mode`,
      { method: "POST", body: JSON.stringify(payload) },
      SubmittedRunSchema,
    );
  },
  approveTemporaryAgent(
    id: string,
    payload: { decision_token: string; version: number },
  ): Promise<SubmittedRun> {
    return request(
      `/api/v1/runs/${encodeURIComponent(id)}/approve-temporary-agent`,
      { method: "POST", body: JSON.stringify(payload) },
      SubmittedRunSchema,
    );
  },
  reviseTemporaryAgent(
    id: string,
    payload: { decision_token: string; version: number; feedback: string },
  ): Promise<SubmittedRun> {
    return request(
      `/api/v1/runs/${encodeURIComponent(id)}/revise-temporary-agent`,
      { method: "POST", body: JSON.stringify(payload) },
      SubmittedRunSchema,
    );
  },
  runs(): Promise<RunListItem[]> {
    return request("/api/v1/admin/runs", { method: "GET" }, z.array(RunListItemSchema));
  },
  run(id: string): Promise<RunDetail> {
    return request(`/api/v1/admin/runs/${id}`, { method: "GET" }, RunDetailSchema);
  },
  conversation(conversationId: string): Promise<Conversation> {
    return request(
      `/api/v1/admin/conversations/${encodeURIComponent(conversationId)}`,
      { method: "GET" },
      ConversationSchema,
    );
  },
  pauseRun(id: string): Promise<RunDetail> {
    return request(`/api/v1/admin/runs/${id}/pause`, { method: "POST" }, RunDetailSchema);
  },
  resumeRun(id: string): Promise<RunDetail> {
    return request(`/api/v1/admin/runs/${id}/resume`, { method: "POST" }, RunDetailSchema);
  },
  cancelRun(id: string): Promise<RunDetail> {
    return request(`/api/v1/admin/runs/${id}/cancel`, { method: "POST" }, RunDetailSchema);
  },
  deleteRun(id: string): Promise<RunDeleteResult> {
    return request(`/api/v1/admin/runs/${id}`, { method: "DELETE" }, RunDeleteSchema);
  },
  bulkDeleteRuns(ids: string[]): Promise<RunBulkDeleteResult> {
    return request(
      "/api/v1/admin/runs/bulk-delete",
      { method: "POST", body: JSON.stringify({ ids }) },
      RunBulkDeleteSchema,
    );
  },
  skills(): Promise<Skill[]> {
    return request("/api/v1/admin/skills", { method: "GET" }, z.array(SkillSchema));
  },
  uploadSkill(filename: string): Promise<Skill> {
    return request(
      "/api/v1/admin/skills",
      { method: "POST", body: JSON.stringify({ filename }) },
      SkillSchema,
    );
  },
  uploadSkillArchive(file: File, strategy?: "overwrite" | "new_version"): Promise<SkillArchiveUpload> {
    const filename = encodedFilenameHeader(file.name);
    const query = strategy ? `?strategy=${encodeURIComponent(strategy)}` : "";
    return requestBinary(
      `/api/v1/admin/skills/upload${query}`,
      {
        method: "POST",
        body: file,
        headers: {
          "Content-Type": archiveContentType(file.name),
          "X-Agent-Hub-Skill-Filename": filename.encoded,
          "X-Agent-Hub-Skill-Filename-Encoding": filename.encoding,
        },
      },
      SkillArchiveUploadSchema,
    );
  },
  activateSkillVersion(skillId: string, versionId: string): Promise<Skill> {
    return request(
      `/api/v1/admin/skills/${encodeURIComponent(skillId)}/versions/${encodeURIComponent(versionId)}/activate`,
      { method: "POST" },
      SkillSchema,
    );
  },
  approveSkill(id: string): Promise<Skill> {
    return request(`/api/v1/admin/skills/${id}/approve`, { method: "POST" }, SkillSchema);
  },
  deleteSkill(id: string): Promise<{ status: string }> {
    return request(
      `/api/v1/admin/skills/${encodeURIComponent(id)}`,
      { method: "DELETE" },
      z.object({ status: z.string() }),
    );
  },
  bulkDeleteSkills(ids: string[]): Promise<SkillBulkDeleteResult> {
    return request(
      "/api/v1/admin/skills/bulk-delete",
      { method: "POST", body: JSON.stringify({ ids }) },
      SkillBulkDeleteSchema,
    );
  },
  mcpServers(): Promise<McpServer[]> {
    return request("/api/v1/admin/mcp", { method: "GET" }, z.array(McpServerSchema));
  },
  createMcpServer(payload: {
    id: string;
    name: string;
    allowed_tools: string[];
    transport: string;
    command?: string | null;
    args?: string[];
    url?: string | null;
    executable_allowlist?: string[];
    domain_allowlist?: string[];
    timeout_seconds?: number;
  }): Promise<McpServer> {
    return request(
      "/api/v1/admin/mcp",
      { method: "POST", body: JSON.stringify(payload) },
      McpServerSchema,
    );
  },
  deleteMcpServer(id: string): Promise<{ status: string }> {
    return request(
      `/api/v1/admin/mcp/${encodeURIComponent(id)}`,
      { method: "DELETE" },
      z.object({ status: z.string() }),
    );
  },
  channels(): Promise<ChannelStatus[]> {
    return request("/api/v1/admin/channels", { method: "GET" }, z.array(ChannelStatusSchema));
  },
  saveChannelConfig(id: string, payload: { values: Record<string, string> }): Promise<ChannelConfigSave> {
    return request(
      `/api/v1/admin/channels/${encodeURIComponent(id)}/config`,
      { method: "POST", body: JSON.stringify(payload) },
      ChannelConfigSaveSchema,
    );
  },
  clearChannelConfig(id: string): Promise<ChannelConfigSave> {
    return request(
      `/api/v1/admin/channels/${encodeURIComponent(id)}/config`,
      { method: "DELETE" },
      ChannelConfigSaveSchema,
    );
  },
  memory(): Promise<MemoryRecord[]> {
    return request("/api/v1/admin/memory", { method: "GET" }, z.array(MemoryRecordSchema));
  },
  cognitionEpisodes(): Promise<CognitionEpisode[]> {
    return request("/api/v1/admin/cognition/episodes", { method: "GET" }, z.array(CognitionEpisodeSchema));
  },
  cognitionExperiences(): Promise<CognitionExperience[]> {
    return request("/api/v1/admin/cognition/experiences", { method: "GET" }, z.array(CognitionExperienceSchema));
  },
  cognitionReflections(): Promise<CognitionReflection[]> {
    return request("/api/v1/admin/cognition/reflections", { method: "GET" }, z.array(CognitionReflectionSchema));
  },
  cognitionBeliefs(): Promise<CognitionBelief[]> {
    return request("/api/v1/admin/cognition/beliefs", { method: "GET" }, z.array(CognitionBeliefSchema));
  },
  cognitionRelationship(): Promise<CognitionRelationship> {
    return request("/api/v1/admin/cognition/relationship", { method: "GET" }, CognitionRelationshipSchema);
  },
  cognitionWorldState(): Promise<CognitionWorldState[]> {
    return request("/api/v1/admin/cognition/world-state", { method: "GET" }, z.array(CognitionWorldStateSchema));
  },
  cognitionRouterPreview(payload: CognitionRouterPreviewPayload): Promise<CognitiveContextBundle> {
    return request(
      "/api/v1/admin/cognition/router-preview",
      { method: "POST", body: JSON.stringify(payload) },
      CognitiveContextBundleSchema,
    );
  },
  createMemory(payload: { id: string; scope: string; value: string }): Promise<MemoryRecord> {
    return request(
      "/api/v1/admin/memory",
      { method: "POST", body: JSON.stringify(payload) },
      MemoryRecordSchema,
    );
  },
  updateMemory(id: string, value: string): Promise<MemoryRecord> {
    return request(
      `/api/v1/admin/memory/${encodeURIComponent(id)}`,
      { method: "PATCH", body: JSON.stringify({ value }) },
      MemoryRecordSchema,
    );
  },
  lockMemory(id: string): Promise<MemoryRecord> {
    return request(
      `/api/v1/admin/memory/${encodeURIComponent(id)}/lock`,
      { method: "POST" },
      MemoryRecordSchema,
    );
  },
  unlockMemory(id: string): Promise<MemoryRecord> {
    return request(
      `/api/v1/admin/memory/${encodeURIComponent(id)}/unlock`,
      { method: "POST" },
      MemoryRecordSchema,
    );
  },
  async forgetMemory(id: string): Promise<void> {
    await requestNoContent(`/api/v1/admin/memory/${encodeURIComponent(id)}`, { method: "DELETE" });
  },
  audit(action?: string): Promise<AuditEvent[]> {
    const query = action ? `?action=${encodeURIComponent(action)}` : "";
    return request(`/api/v1/admin/audit${query}`, { method: "GET" }, z.array(AuditEventSchema));
  },
  logs(category?: string): Promise<LogEntry[]> {
    const query = category ? `?category=${encodeURIComponent(category)}` : "";
    return request(`/api/v1/admin/logs${query}`, { method: "GET" }, z.array(LogEntrySchema));
  },
  hermesInsights(): Promise<HermesInsight[]> {
    return request("/api/v1/admin/hermes", { method: "GET" }, z.array(HermesInsightSchema));
  },
  hermesInsight(id: string): Promise<HermesInsight> {
    return request(`/api/v1/admin/hermes/${encodeURIComponent(id)}`, { method: "GET" }, HermesInsightSchema);
  },
  confirmHermesInsight(id: string): Promise<HermesInsight> {
    return request(`/api/v1/admin/hermes/${encodeURIComponent(id)}/confirm`, { method: "POST" }, HermesInsightSchema);
  },
  deleteHermesInsight(id: string): Promise<OperationStatus> {
    return request(`/api/v1/admin/hermes/${encodeURIComponent(id)}`, { method: "DELETE" }, OperationStatusSchema);
  },
  bulkConfirmHermesInsights(ids: string[]): Promise<HermesBulkConfirmResult> {
    return request(
      "/api/v1/admin/hermes/bulk-confirm",
      { method: "POST", body: JSON.stringify({ ids }) },
      HermesBulkConfirmSchema,
    );
  },
  bulkDeleteHermesInsights(ids: string[]): Promise<HermesBulkDeleteResult> {
    return request(
      "/api/v1/admin/hermes/bulk-delete",
      { method: "POST", body: JSON.stringify({ ids }) },
      HermesBulkDeleteSchema,
    );
  },
  recordHermesFeedback(payload: {
    run_id?: string | null;
    conversation_id?: string | null;
    category?: "conversation" | "scheduler";
    outcome: "success" | "failure" | "neutral";
    lesson: string;
    tags: string[];
    weight: number;
  }): Promise<HermesInsight> {
    return request(
      "/api/v1/admin/hermes/feedback",
      { method: "POST", body: JSON.stringify(payload) },
      HermesInsightSchema,
    );
  },
  recommendWithHermes(payload: {
    task: string;
    mode_candidates: string[];
    model_candidates: string[];
    skill_candidates: string[];
  }): Promise<HermesRecommendation> {
    return request(
      "/api/v1/admin/hermes/recommend",
      { method: "POST", body: JSON.stringify(payload) },
      HermesRecommendationSchema,
    );
  },
};
