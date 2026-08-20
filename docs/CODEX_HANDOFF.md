# Codex handoff

## Current baseline

- Contract repository initialized at version `1.0.0`; runtime contract version is `1.0`.
- Integration documentation, two OpenAPI 3.1 documents, six Draft 2020-12 schemas, valid examples, validation tooling, CI, and governance are present.
- Validate with `python -m pip install -r requirements-dev.txt` followed by `python scripts/validate-contracts.py`.

## Pending decisions

- The source specification defines `rolling_back` and `rolled_back`; the earlier shorthand requirement called this “Rollback”. Consumers must use the canonical snake_case states.
- Product versions and compatibility remain TBD until consumer integration is tested.
- Authentication, TLS, and package signatures are outside v1; SHA-256 integrity is required.

## Consumer rollout

None of SlamCore-Updater, SlamCore-Agent, or SlamCore-Server has yet adopted this submodule. Recommended next order:

1. SlamCore-Updater
2. SlamCore-Agent
3. SlamCore-Server
