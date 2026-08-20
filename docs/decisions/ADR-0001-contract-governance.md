# ADR-0001: Contract governance

- **Status:** Accepted
- **Date:** 2026-08-20

## Context and decision

OTA behavior crosses Server, Agent, and Updater release cycles. A separate contract repository prevents any implementation from becoming an accidental authority and permits machine validation independent of product builds.

Each product consumes this repository as a Git submodule. The submodule is pinned to a reviewed commit or `contract-v*` tag so builds are reproducible and do not silently change. Automatically tracking `main` is prohibited because an unrelated merge could otherwise change a consumer's public behavior without its review or CI evidence.

## Change process

1. Propose the specification, OpenAPI, schemas, examples, changelog, and compatibility changes here.
2. Run contract validation and obtain reviewers representing affected consumers.
3. Merge; only then create the reviewed contract tag.
4. Upgrade each consumer's pinned submodule and implement/test it independently.

Removing/renaming endpoints or fields, adding requirements, narrowing values, changing types/state semantics, or changing required package structure is breaking and requires a SemVer major increment plus an explicit migration plan. Compatible additions use minor releases; non-semantic corrections use patches. Consumers never follow `main` automatically.
