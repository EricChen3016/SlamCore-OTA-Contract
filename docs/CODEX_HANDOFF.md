# Codex handoff

## Current baseline

- Repository version is `2.0.0`; runtime contract version is `2.0`.
- Contract 2.0 is a breaking correction of the Updater/SlamCoreWeb ownership boundary.
- The package metadata is strict JSON at `SlamCoreWeb/.slamcore-package.json`; workspace `.slamcore_release` is only a one-line SemVer active marker.
- Validate with `python -m pip install -r requirements-dev.txt` and `python scripts/validate-contracts.py`.

## Decided ownership

- Updater: download/integrity, package validation, staging, activation, active link/marker, managed runtime restart/health, rollback, durable crash recovery.
- SlamCoreWeb startup: ROS build detection and reconciliation.
- `.slamcore_build_manifest.json`: internal workspace state owned by SlamCoreWeb Build Manager. Its schema is deliberately absent from this repository. Updater may neither inspect nor alter it and must preserve unrelated workspace state.

## Consumer migration status

- SlamCore-Updater is still pinned to contract commit `2d76fe891b3f7b2ddc266ca04e268397294832b5` (Contract 1.x) and must migrate first.
- SlamCore-Agent and SlamCore-Server must then adopt runtime `2.0` DTO/state enums together; mixed 1.x/2.0 job processing is unsupported.
- SlamCoreWeb release production must emit `.slamcore-package.json`; startup must reconcile stale internal build state from the active release marker.
- No product repository is modified by this contract change.

## Required Updater work

1. Upgrade the pinned contract commit and reject Contract 1.x requests as incompatible rather than reinterpret them.
2. Remove `building`, build-manifest parsing/validation/mutation, ROS package detection, Build Manager invocation, and the standalone 45-minute Build timeout.
3. Verify artifact SHA-256 before extraction, then validate safe archive shape and strict `.slamcore-package.json` before active-link mutation.
4. Preserve `.slamcore_build_manifest.json` and all unrelated workspace-level state during install, cleanup, recovery, and rollback; accept all future internal manifest contents.
5. Treat workspace `.slamcore_release` as atomic one-line SemVer active marker only, never package metadata; rollback marker and link as a pair.
6. Use the public path `installing → restarting → health_checking`, allowing 60 minutes for runtime startup plus health convergence.
7. Persist journal checkpoints around link/marker mutation and test crashes before link mutation, after link mutation before checkpoint, and after marker commit.
8. Roll back on generic managed-runtime health failure without interpreting colcon/ROS causes; verify the previous runtime becomes healthy.
9. Add all Contract 2.0 acceptance cases from Integration Spec section 9 as contract/integration tests.

## Deferred scope

Authentication, TLS, package signatures, rollout waves, pause/cancel, and messaging remain outside Contract 2.0.
