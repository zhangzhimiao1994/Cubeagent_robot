# Project Handoff

Updated: 2026-09-10 18:50 Asia/Shanghai

## How To Continue

Continue from branch `cognitive-experience-layer` in `E:\code_x\cubeagent_robot\.worktrees\cognitive-experience-layer`. The Cognitive Experience Layer implementation is the current completed slice. The next durable work should start a separate robot runtime/protocol/provisioning/OTA plan before editing Raspberry Pi runtime code.

## Current State

- Local project root: `E:\code_x\cubeagent_robot`.
- Current implementation worktree: `E:\code_x\cubeagent_robot\.worktrees\cognitive-experience-layer`.
- GitHub repository: `https://github.com/zhangzhimiao1994/Cubeagent_robot`.
- Production/debug target: `prod-web-02`.
- Web debug entry: `http://<prod-web-02-ip>:32020/login`, tested without a proxy when deployment is needed.
- No deployment was performed for the cognition slice.

## Completed Cognitive Slices

- Added `src/agent_hub/cognition/` with bounded domain models for episodes, experiences, reflections, beliefs, relationship state, world state, protected self-model records, protected change proposals, and cognitive context bundles.
- Added sparse learning gates so raw chat is not treated as experience; secret-like, private, low-value, low-confidence, and missing-evidence episodes do not become reusable experience.
- Added repository abstraction with in-memory and `AdminResourceRow(kind="cognition")` persistence scoped by tenant and user.
- Added Experience Store, Reflection Engine, Belief/Relationship/World/Self Model services, Memory/Experience Router, and Hermes/Memory/Evolution/Skill integration helpers.
- Added best-effort runtime cognitive context injection and non-blocking outcome ingestion; cognition failures generate bounded Hermes failure observations.
- Added admin cognition API under `/api/v1/admin/cognition` with RBAC: admin write/read, operator read-only, viewer denied.
- Added Web cognition debug console with metrics, tabs, relationship/world/belief/experience visibility, and router preview.
- Added security regression tests for secret rejection, protected self-model boundary, tenant/user isolation, and Hermes failure observation.

## Verification Snapshot

- `ruff check --no-cache src tests` passed.
- `git diff --check` passed.
- `pytest tests/security/test_cognition_safety.py -q -o addopts=` printed `4 passed [100%]`, then hung during runner shutdown and was interrupted.
- The focused backend command for cognition unit/API/integration/security tests printed the cognition unit/API/security tests as passed, then the persistence integration test errored because PostgreSQL was unavailable at `127.0.0.1:54329`; Docker Desktop was not running, so the compose fixture could not be started locally.
- `mypy src --cache-dir E:\code_x\.mypy_cache_cubeagent_cognitive` no longer reports cognition source errors; remaining failures are inherited missing PyYAML stubs in `runtime/crew/plan.py`, `skills/package.py`, and `api/routers/admin.py`.
- Frontend focused verification for `CognitionPage.test.tsx` passed 3 tests. Earlier Task 10 verification also passed TypeScript check, full frontend vitest, and Vite build with existing Vite chunk-size/zod comment warnings.

## Known Problems And Risks

- The repository still contains inherited broad Agent Hub modules; robot-specific pruning should be phased after protocol/runtime dependencies are clear.
- There is no dedicated Robot Protocol v1 backend, voice session streaming API, Pi heartbeat API, or OTA status API yet.
- There is no Raspberry Pi runtime package, first-boot provisioning image/script, signed update installer, or rollback flow yet.
- The cognitive layer is designed for sparse high-value learning, but production tuning still needs real voice interaction outcomes and operator review in the Web console.
- Local Windows pytest runner behavior remains unreliable for process exit/collection; direct function checks and frontend tooling were used as focused verification fallback where needed.
- Local PostgreSQL/Redis test services are not running; integration persistence verification needs Docker Desktop or an equivalent test database.

## Next Recommended Work

1. Define Robot Protocol v1 for server-to-Pi playback, capture, heartbeat, health, logs, version, and OTA commands.
2. Implement the server-side robot runtime/session layer that treats Raspberry Pi as playback/tool endpoint, not the brain.
3. Add `cube-robot-runtime/` for Raspberry Pi with mockable audio playback/capture, reconnect logic, heartbeat, and local health reporting.
4. Add first-boot provisioning for Wi-Fi/server URL/device token setup and `systemd` service installation.
5. Design and implement OTA: signed/checksummed update metadata, staged install, health check, rollback, and Web visibility.
6. Run end-to-end voice robot tests against `prod-web-02` on port `32020` after deployment cleanup.
