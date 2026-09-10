# Cognitive Experience Layer Design

## Objective

Add a continuous learning and experience growth system to `Cubeagent_robot` so the Agent can learn from long-term interaction with the user, extract reusable lessons, update its beliefs carefully, and let validated experience influence future behavior.

The goal is not to remember more raw content. The goal is to extract the few important parts, compress them into stable and reviewable structures, verify them over time, forget weak or stale conclusions, and retrieve only the most relevant items for the current situation.

The target loop is:

```text
Interaction
  -> Episode
  -> Memory
  -> Experience
  -> Reflection
  -> Belief / Strategy
  -> Skill
  -> Future Decision
  -> Outcome
  -> New Reflection
```

## Source Of Truth

- Local project root: `E:\code_x\cubeagent_robot`
- GitHub repository: `https://github.com/zhangzhimiao1994/Cubeagent_robot`
- Existing voice robot design: `docs/superpowers/specs/2026-09-10-long-term-companion-robot-v2-design.md`
- Production/debug host: `prod-web-02`
- Web debug URL: `http://<prod-web-02-ip>:32020/login`

## Current Baseline

The repository already has the foundations required for this work:

- `src/agent_hub/memory/`: layered Memory with working, episodic, and core records; heat, recall count, lock, decay, consolidation, audit, and safety checks.
- `src/agent_hub/hermes/`: persistent Hermes run advice and confirmed lesson injection through admin resources.
- `src/agent_hub/evolution.py`: versioned evolution rounds with approval, score gates, rollback recommendations, and execution ingestion.
- `src/agent_hub/improvements/`: administrator-gated improvement proposals.
- `src/agent_hub/context/`: context construction that can include selected memories.
- `src/agent_hub/api/routers/admin.py`: admin APIs and persistent `AdminResourceRow` storage for `memory`, `hermes`, and `evolution`.
- `src/agent_hub/skills/`: reusable Skill packaging and execution foundations.

The new system should reuse these pieces. It should not replace them and should not introduce several overlapping third-party memory frameworks.

## Design Principle: Sparse, High-Signal Learning

The Agent should not convert every chat turn into long-term memory or experience. Raw interaction volume makes a companion robot less reliable because old, noisy, temporary, or contradictory details can pollute future context.

Default behavior:

- Ordinary chat remains short-lived.
- Raw transcripts remain run or episode evidence, not direct strategy.
- Only important, repeated, corrected, successful, failed, or relationship-relevant patterns can enter long-term cognitive storage.
- Long-term items must remain small, structured, source-backed, confidence-scored, and eligible for decay or replacement.
- Retrieval must be dynamic and bounded. Future prompts should receive a small selected set, not the whole cognitive store.

## Product Boundary

Add an independent `Cognitive / Experience Layer` that is decoupled from Agent Harness, Memory, SOUL/Persona, User Profile, model providers, and robot device code.

Recommended package:

```text
src/agent_hub/cognition/
  __init__.py
  types.py
  episodes.py
  experience_store.py
  reflection.py
  beliefs.py
  relationship.py
  world_state.py
  self_model.py
  skill_learning.py
  router.py
  repository.py
  service.py
```

Responsibilities:

- `episodes.py`: structured interaction episodes from voice, Web, task, and device events.
- `experience_store.py`: reusable experience records derived from episodes.
- `reflection.py`: causal, counterfactual, positive, and negative reflection.
- `beliefs.py`: confidence-scored judgments about the user, environment, and repeated patterns.
- `relationship.py`: long-term user-agent relationship state.
- `world_state.py`: ongoing facts, people, events, unfinished items, and event status changes.
- `self_model.py`: stable Agent identity and protected self constraints.
- `skill_learning.py`: promotion of validated experience into Skill or workflow improvement proposals.
- `router.py`: dynamic Memory/Experience retrieval for the current scene.
- `repository.py`: persistence abstraction.
- `service.py`: orchestration layer that connects episodes, reflection, beliefs, relationship, world state, Hermes, Memory, Evolution, and Skill.

## Data Model

### Episode

An `Episode` is a structured record of an interaction window. It is not itself reusable experience.

Fields:

- `id`
- `tenant_id`
- `user_id`
- `source`: `voice`, `web`, `task`, `device`, or `system`
- `conversation_id`
- `run_id`
- `started_at`
- `ended_at`
- `summary`
- `signals`
- `outcome`
- `feedback`
- `evidence_refs`
- `privacy_level`
- `created_at`

Important signals include user correction, rejection, satisfaction, repeated question, interruption, silence, explicit success, explicit failure, task completion, playback failure, and network degradation.

### Experience

An `Experience` is a reusable lesson abstracted from one or more episodes.

Fields:

- `id`
- `tenant_id`
- `user_id`
- `kind`: `preference`, `strategy`, `failure_pattern`, `success_pattern`, `relationship_pattern`, `tool_pattern`, `voice_interaction`, or `world_pattern`
- `statement`
- `applicability`
- `recommended_action`
- `avoid_action`
- `confidence`
- `evidence_refs`
- `contradictions`
- `usage_count`
- `success_count`
- `failure_count`
- `last_used_at`
- `last_verified_at`
- `version`
- `status`: `active`, `candidate`, `stale`, `rejected`, or `superseded`
- `created_at`
- `updated_at`

Experience records must be short. They should describe the reusable pattern and the future behavior implication, not copy the chat.

Example:

```json
{
  "kind": "voice_interaction",
  "statement": "The user often interrupts long spoken explanations during deployment debugging.",
  "applicability": "voice replies during technical debugging",
  "recommended_action": "Start with one concise action and ask before expanding.",
  "avoid_action": "Do not give a long spoken checklist unless requested.",
  "confidence": 0.72
}
```

### Reflection

A `Reflection` explains why something worked or failed and what should change.

Fields:

- `id`
- `episode_id`
- `reflection_type`: `causal`, `counterfactual`, `positive`, `negative`, or `mixed`
- `trigger`: `user_corrected`, `user_rejected`, `user_satisfied`, `task_succeeded`, `task_failed`, `repeated_pattern`, `agent_uncertain`, or `scheduled_review`
- `what_happened`
- `why_it_happened`
- `better_next_time`
- `candidate_experience_ids`
- `candidate_belief_updates`
- `candidate_skill_updates`
- `confidence`
- `requires_approval`
- `created_at`

Causal reflection answers: "which behavior likely caused which outcome?"

Counterfactual reflection answers: "if this situation happened again, what would be a better approach?"

### Belief

A `Belief` is a tentative judgment, not a permanent fact.

Fields:

- `id`
- `tenant_id`
- `user_id`
- `subject`
- `predicate`
- `object`
- `scope`
- `confidence`
- `evidence_refs`
- `contradictions`
- `last_verified_at`
- `verification_count`
- `status`: `active`, `candidate`, `uncertain`, `contradicted`, or `retired`
- `created_at`
- `updated_at`

Rules:

- A single weak signal can create only a candidate belief.
- Repeated consistent evidence can increase confidence.
- Contradictory evidence lowers confidence or marks the belief contradicted.
- Beliefs about sensitive traits must require explicit user confirmation or remain out of long-term cognitive storage.

### Relationship State

`RelationshipState` tracks how the Agent should adapt to the user over time.

Fields:

- `user_id`
- `familiarity`
- `trust`
- `rapport`
- `preferred_tone`
- `preferred_depth`
- `interaction_rhythm`
- `shared_history`
- `stable_preferences`
- `recent_changes`
- `boundaries`
- `evidence_refs`
- `last_updated_at`

Relationship state should influence style and timing, not override user instructions or safety policy.

### World State

`WorldState` tracks ongoing, time-sensitive, or status-changing entities.

Fields:

- `id`
- `tenant_id`
- `user_id`
- `entity_type`: `person`, `project`, `task`, `event`, `place`, `device`, or `topic`
- `name`
- `state`
- `status`
- `starts_at`
- `due_at`
- `ended_at`
- `participants`
- `evidence_refs`
- `confidence`
- `last_verified_at`
- `created_at`
- `updated_at`

World state is for active continuity: unfinished items, future events, important people, current projects, device state, and changing facts. It should be pruned or archived when no longer active.

### Self Model

`SelfModel` holds the Agent's stable identity, personality, values, boundaries, capability claims, and long-term shared story with the user.

Self model is protected:

- Ordinary reflection cannot directly rewrite core identity, safety rules, or tool permissions.
- Proposed changes require review, versioning, and rollback.
- Runtime state can adapt tone and behavior, but core identity remains stable.

## Learning Gates

An interaction may become an experience only if at least one gate passes:

- The user explicitly corrects the Agent.
- The user explicitly rejects or accepts an answer.
- A task has a measurable success or failure outcome.
- The same pattern appears repeatedly.
- The interaction reveals a durable user preference.
- The interaction changes a relationship boundary or shared history.
- The interaction updates an active world-state item.
- The Agent had high uncertainty and later received clarifying evidence.

Rejected inputs:

- One-off small talk without future value.
- Temporary mood or location unless user says it matters.
- Secrets, credentials, tokens, or private access material.
- Prompt-like external content.
- Unsupported guesses about sensitive attributes.
- Noisy ASR fragments with low confidence.
- Contradictory single evidence that would overwrite a stronger belief.

## Reflection Engine

Reflection should run on selected triggers and scheduled review windows.

Inputs:

- Episode summary.
- User feedback.
- Task outcome.
- Voice interaction signals.
- Existing Memory, Hermes lessons, Beliefs, Relationship State, and World State.

Outputs:

- Candidate experiences.
- Candidate belief updates.
- Candidate relationship updates.
- Candidate world-state updates.
- Candidate Skill or workflow improvement proposals.
- Forget, merge, decay, or contradiction recommendations.

Reflection is allowed to update normal experience and low-risk relationship/world state automatically when confidence gates pass. It must not directly modify protected self model, safety policy, core persona, tool permissions, or hardware safety boundaries.

## Positive And Negative Learning

The system must learn from both success and failure.

Negative learning:

- User correction.
- User dissatisfaction.
- Repeated misunderstanding.
- Failed task result.
- Unsafe or unhelpful tool path.
- Voice interruption caused by long or poorly timed response.

Positive learning:

- User says the answer helped.
- User accepts an action.
- Task completes successfully.
- A response style repeatedly works.
- A Skill or workflow produces a strong outcome.
- A proactive reminder is accepted as timely.

Positive learning should not blindly promote every praised interaction. It should extract the condition that made it work.

## Curiosity And Active Learning

The Agent should track known, uncertain, and unknown areas about the user. It should not interrogate the user mechanically.

Curiosity policy:

- Ask only when the answer is useful for the current conversation or a near-future action.
- Prefer natural, low-friction questions.
- Defer questions when the user is busy, stressed, or doing a task.
- Mark unresolved uncertainty instead of forcing a question.
- Use future evidence to verify or correct beliefs.

Example:

If the Agent is uncertain whether the user prefers short or detailed voice replies, it should observe interruptions and satisfaction signals first, then ask naturally when relevant: "这次我先短说，需要我展开再讲吗？"

## Memory And Experience Router

Long-term data must not be injected wholesale into prompts.

The `MemoryExperienceRouter` selects a small, scene-specific context bundle:

- `core_constraints`: protected identity, safety, and current user instruction constraints.
- `relationship_context`: at most a few high-confidence relationship preferences.
- `world_context`: active events or unfinished items relevant to the current turn.
- `experience_context`: the top relevant reusable lessons.
- `belief_context`: only beliefs that are relevant, high-confidence, and not contradicted.
- `skill_context`: recommended Skill or workflow, with evidence and confidence.

Selection factors:

- Current scene: voice chat, task execution, troubleshooting, reminder, proactive follow-up, device command, or emotional support.
- Relevance to current user request.
- Confidence.
- Recency and last verification.
- Success/failure history.
- Contradiction risk.
- Voice latency budget.
- User's current instruction.

Initial bounds for voice interaction:

- 1 protected persona or safety constraint block.
- Up to 3 relationship or preference items.
- Up to 2 active world-state items.
- Up to 2 experience items.
- Up to 1 Skill recommendation unless the user asks for task execution.

## Integration With Existing Systems

### Memory

Memory remains the place for compact factual and episodic recall. The cognitive layer can write distilled memory records only after safety and value gates pass.

Memory should not become the only storage for experience, beliefs, relationship, and world state. Those need separate typed records so they can be scored, contradicted, versioned, and routed differently.

### Hermes

Hermes remains the confirmed lesson and run-advice system. The cognitive layer should feed Hermes higher-quality lessons:

- What strategy worked.
- What strategy failed.
- Which user preference affected the outcome.
- Which context caused a tool or workflow choice.
- Whether a lesson should influence future mode routing, prompt style, or Skill selection.

Hermes injection remains bounded and filtered.

### Cognitive Failure Learning

Cognitive-layer failures must be observable and learnable. The runtime may continue without cognitive advice when the cognitive layer fails, but the failure must not disappear silently.

When cognitive advice, routing, reflection, belief update, relationship update, world-state update, or outcome ingestion fails, the system should create a bounded Hermes failure observation:

- failure stage: `advice`, `router`, `reflection`, `belief_update`, `relationship_update`, `world_state_update`, `skill_learning`, or `outcome_ingest`
- failure class: timeout, validation error, repository error, model error, unsafe content rejection, or unexpected exception
- impact: advice skipped, episode stored without reflection, experience not promoted, state update skipped, or outcome ingest skipped
- safe summary: a short operational lesson without raw user transcript, secrets, tokens, or protected profile details
- next avoidance strategy: retry later, fall back to Memory-only context, reduce router budget, disable a bad candidate experience, or require review

These Hermes records should be categorized as runtime/cognition observations unless they have been reviewed and confirmed as future behavior guidance. Confirmed cognition lessons may later influence routing, but unconfirmed failure observations should remain diagnostic and should not pollute normal conversation context.

Example Hermes lesson:

```json
{
  "category": "scheduler",
  "outcome": "failure",
  "lesson": "cognition_failure stage=router impact=advice_skipped strategy=fallback_to_memory_only",
  "tags": ["cognition", "failure", "router"],
  "weight": 4
}
```

### Evolution

Evolution remains the mechanism for versioned improvement rounds. The cognitive layer can propose Evolution runs when multiple experiences indicate a stable opportunity:

- Optimize a Skill.
- Create a new Skill.
- Adjust a workflow.
- Improve a prompt strategy.

Promotion to Evolution requires evidence, evaluation cases, score gates, and rollback.

### Skill Library

Skill Library should receive only repeatedly validated patterns. A single good interaction should not become a Skill.

Promotion criteria:

- Multiple successful uses or one high-value explicit user request.
- Clear applicability.
- Clear evaluation cases.
- No unresolved contradiction.
- Safe permissions.
- Version and rollback path.

### Voice Robot Runtime

Voice events should become cognitive signals:

- User interrupts long answer.
- User asks the robot to repeat.
- ASR uncertainty causes misunderstanding.
- User accepts a short answer.
- Playback fails.
- User responds warmly to proactive behavior.

These signals should influence future speaking style, turn-taking, response length, and proactive policy.

## Permission Boundary

Automatic updates allowed:

- Candidate episodes.
- Low-risk experiences.
- Confidence changes.
- Contradiction markers.
- Merge and decay of ordinary experiences.
- World-state status changes from clear evidence.
- Relationship rhythm and style preferences with bounded influence.

Review or approval required:

- Core SOUL or Persona changes.
- Self Model identity changes.
- Safety policy changes.
- Tool permissions.
- Hardware command permissions.
- High-risk proactive behavior.
- Skill publication or workflow changes that affect external actions.
- Any conclusion based on sensitive personal attributes.

The Agent may suggest protected changes, but protected changes must go through explicit approval, versioning, audit, and rollback.

## Persistence

Use the repository pattern before hard-coding storage. The first implementation can persist cognitive records through `AdminResourceRow` with new resource kinds or a compact initial kind if migration risk needs to stay low.

Preferred long-term storage:

- Dedicated typed tables for episodes, experiences, beliefs, relationship state, world state, reflections, and skill learning records.
- Tenant and user isolation on every record.
- Indexes by user, kind, status, confidence, updated time, and scene tags.
- Audit events for create, update, merge, decay, retire, contradiction, promotion, and protected-change proposal.

The design must preserve delete, forget, and export paths.

## Web Debug Surface

Add a cognitive debugging area to the Web console after backend foundations exist:

- Episode list and detail.
- Experience candidates, accepted records, retired records.
- Reflection trace with causal and counterfactual output.
- Belief graph/table with confidence, evidence, contradiction, and last verification.
- Relationship state timeline.
- World-state active items.
- Skill learning proposals.
- Router preview showing why a context bundle was selected.

The debug UI should be operational and dense, not a marketing interface.

## Failure Modes To Prevent

- Remembering too much raw text.
- Treating one interaction as permanent truth.
- Injecting stale or contradicted beliefs into context.
- Letting praise promote weak strategies.
- Letting failures overcorrect behavior.
- Automatically changing persona or permissions.
- Asking too many curiosity questions.
- Using memory retrieval that makes voice response latency feel slow.
- Mixing user facts, strategy lessons, relationship state, and world state into one untyped memory bucket.
- Swallowing cognitive-layer failures without recording a bounded Hermes failure observation.

## Phasing

### Phase 1: Types, Repository, And Gates

Implement core typed models, repository abstraction, safety/value gates, and focused tests. The system can accept episodes and reject low-value/noisy input.

### Phase 2: Experience Store And Reflection Engine

Implement experience creation, causal/counterfactual reflection records, positive/negative learning, confidence updates, contradiction handling, and merge/retire behavior.

### Phase 3: Belief, Relationship, And World State

Implement typed stores and update policies for beliefs, relationship state, and active world-state items. Add verification timestamps and contradiction handling.

### Phase 4: Memory/Experience Router

Implement bounded scene-specific retrieval and context bundle rendering. Integrate with existing context construction without flooding prompts.

### Phase 5: Hermes And Evolution Integration

Feed selected cognitive lessons into Hermes, propose Skill/Evolution improvements from repeated validated experiences, and keep protected changes behind review.

### Phase 6: Voice Robot Signals And Web Debugging

Connect voice/device interaction events to episodes and reflections. Add Web debugging pages for the cognitive layer and router decisions.

## Test Strategy

Start with focused failing tests:

- Episode validation rejects noisy or unsafe records.
- Learning gates reject ordinary low-value chat.
- Learning gates accept corrections, success, failure, repeated patterns, and durable preferences.
- Experience records require evidence, confidence, version, and status.
- Reflection creates causal and counterfactual outputs from failure and correction signals.
- Positive learning extracts a strategy only when there is a reusable condition.
- Belief updates increase confidence on repeated evidence and decrease confidence on contradiction.
- Relationship state changes influence style only through bounded router output.
- World state updates active item status without creating permanent facts from weak evidence.
- Router returns a small bounded context bundle.
- Protected self model, persona, safety, and permission changes require approval.
- Skill promotion requires repeated validation and evaluation cases.
- Tenant/user isolation prevents cross-user cognitive retrieval.

## Acceptance Criteria

The implementation is acceptable when:

- Ordinary chat does not automatically become long-term experience.
- Important interactions produce structured episodes and selected candidate experiences.
- Reflections explain cause and counterfactual improvement.
- Beliefs and experiences carry confidence, evidence, contradiction, usage, success/failure, and last verification metadata.
- Future decisions can be influenced by a small, relevant router-selected context bundle.
- Repeated successful strategies can propose Skill or workflow improvements.
- Protected persona, SOUL, safety, and permissions cannot be changed by ordinary reflection.
- The Web debug surface can show why a memory, experience, belief, or Skill was selected.

## Open Implementation Choices

The first implementation should decide these before coding:

- Whether Phase 1 uses `AdminResourceRow` as temporary persistence or adds dedicated Alembic tables immediately.
- Whether the first Reflection Engine is deterministic rules-only or model-assisted behind a structured schema.
- Whether cognitive router output is injected through existing `ContextBuilder` first or through a separate companion voice prompt bridge.
