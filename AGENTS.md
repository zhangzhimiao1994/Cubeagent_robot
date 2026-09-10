# Workspace Rules

- This repository is the active local project for `Cubeagent_robot` under `E:\code_x\cubeagent_robot`.
- This project's valid GitHub repository is `https://github.com/zhangzhimiao1994/Cubeagent_robot` (`git@github.com:zhangzhimiao1994/Cubeagent_robot.git` for SSH pushes). Do not push this project to `CubeAgent`, `Cube-agent`, `mutilagent`, or any other repository.
- This repository is the embodied companion robot product line. It should evolve from the inherited Agent Hub platform into a voice robot system that combines server-side Agent Brain, Hermes/Memory/Skill learning, real-time voice interaction, and Raspberry Pi runtime integration.
- Preserve and strengthen Hermes, Memory, Skill, model configuration, run history, authentication, Web debugging, database, observability, security, and deployment foundations unless the user explicitly changes this boundary.
- Remove, hide, or defer modules that do not serve the voice companion robot experience only after confirming their dependency impact. Do not delete Hermes, Memory, or Skill as generic cleanup.
- The production/debug target is `prod-web-02`; the Web debugging entry is `http://<prod-web-02-ip>:32020/login`. Do not use a proxy when testing that URL.
- For runtime-affecting changes, deploy to `prod-web-02` and run a real feature-specific probe before pushing GitHub.
- During deployment and testing, old temporary packages, stale build artifacts, obsolete release directories, stale caches, and other target-machine garbage files may be cleaned without asking again. This standing approval does not cover databases, user uploads, secrets, active release pointers, current runtime data, or any file whose ownership/purpose is unclear.
- Do not change public URL, port forwarding, secrets, provider credentials, or quota-consuming provider behavior without explicit user authorization.
- Keep `HANDOFF.md`, `task_plan.md`, `findings.md`, and `progress.md` local-only. Never commit secrets, virtual environments, caches, temporary probes, deployment packages, or local archives.
- Use test-driven development for features and bug fixes: add a focused regression, observe the expected failure, implement the smallest fix, then run focused and broader checks.
- After pushing GitHub, inspect the triggered run/check. If it fails, retrieve details, fix, verify, push, and repeat until green or a real external blocker is documented.
- If Docker, Docker Desktop, Docker Compose, or WSL2-backed containers are used, close Docker Desktop and shut down the WSL Docker backend after verification unless the user explicitly asks to keep them running.
- Before finishing Docker-related work, verify cleanup with `Get-Process '*docker*','vmmem*','wsl*'` and `wsl -l -v`; ask for approval if cleanup requires it.
- Update `HANDOFF.md` only for durable current state, meaningful verification results, deployment result changes, known blockers/risks, or ordered next work. Record results, not command logs.
