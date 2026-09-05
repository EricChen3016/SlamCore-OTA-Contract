#!/usr/bin/env python3
"""Validate the SlamCore OTA contract without running product code."""
from __future__ import annotations

import json
import copy
import re
import sys
from pathlib import Path
from urllib.parse import urldefrag

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate_spec

ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []


def fail(path: Path, reason: str) -> None:
    ERRORS.append(f"{path.relative_to(ROOT)}: {reason}")


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(path, f"invalid JSON: {exc}")
        return None


def validate_instance(instance_path: Path, schema_path: Path, instance=None) -> None:
    schema = load_json(schema_path)
    if instance is None:
        instance = load_json(instance_path)
    if schema is None or instance is None:
        return
    try:
        Draft202012Validator.check_schema(schema)
        errors = Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(instance)
        for error in sorted(errors, key=lambda item: list(item.path)):
            location = "/".join(map(str, error.absolute_path)) or "<root>"
            fail(instance_path, f"schema {schema_path.relative_to(ROOT)} at {location}: {error.message}")
    except Exception as exc:  # validator errors must be reported with their file
        fail(schema_path, f"schema validation failed: {exc}")


def validate_invalid_instance(instance_path: Path, schema_path: Path) -> None:
    schema = load_json(schema_path)
    instance = load_json(instance_path)
    if schema is None or instance is None:
        return
    try:
        Draft202012Validator.check_schema(schema)
        errors = list(Draft202012Validator(
            schema, format_checker=FormatChecker()).iter_errors(instance))
        if not errors:
            fail(instance_path, f"must be rejected by {schema_path.relative_to(ROOT)}")
    except Exception as exc:
        fail(schema_path, f"invalid-case validation failed: {exc}")


def validate_json_round_trip(path: Path) -> None:
    instance = load_json(path)
    if instance is None:
        return
    try:
        serialized = json.dumps(instance, ensure_ascii=False, sort_keys=True)
        if json.loads(serialized) != instance:
            fail(path, "JSON serialization/deserialization round trip changed the payload")
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        fail(path, f"JSON round trip failed: {exc}")


def validate_distinct_rollback_identity(path: Path, expect_valid: bool) -> None:
    instance = load_json(path)
    if not isinstance(instance, dict):
        return
    is_distinct = instance.get("jobId") != instance.get("originalUpdateJobId")
    if expect_valid and not is_distinct:
        fail(path, "rollback command jobId R must differ from originalUpdateJobId U")
    if not expect_valid and is_distinct:
        fail(path, "invalid identity example must reuse U as rollback command identity")


def validate_active_release_marker(path: Path) -> None:
    try:
        raw = path.read_bytes()
        raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        fail(path, f"cannot read UTF-8 active release marker: {exc}")
        return
    if b"\r" in raw:
        fail(path, "must use LF line endings")
    semver = rb"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?\n"
    if re.fullmatch(semver, raw) is None:
        fail(path, "must contain exactly one SemVer followed by LF")


def check_refs(document, source: Path) -> None:
    if isinstance(document, dict):
        ref = document.get("$ref")
        if isinstance(ref, str) and not ref.startswith(("#", "http://", "https://")):
            file_part, _ = urldefrag(ref)
            target = (source.parent / file_part).resolve()
            if not target.is_relative_to(ROOT) or not target.is_file():
                fail(source, f"missing or unsafe $ref target: {ref}")
        for value in document.values():
            check_refs(value, source)
    elif isinstance(document, list):
        for value in document:
            check_refs(value, source)


def absolute_refs(document, source: Path) -> None:
    """Make local refs absolute in a validation-only copy for the OpenAPI library."""
    if isinstance(document, dict):
        ref = document.get("$ref")
        if isinstance(ref, str) and not ref.startswith(("#", "http://", "https://", "file://")):
            file_part, fragment = urldefrag(ref)
            document["$ref"] = (source.parent / file_part).resolve().as_uri()
            if fragment:
                document["$ref"] += f"#{fragment}"
        for value in document.values():
            absolute_refs(value, source)
    elif isinstance(document, list):
        for value in document:
            absolute_refs(value, source)


def validate_required_header_component(
    document: dict,
    source: Path,
    component_name: str,
    header_name: str,
) -> None:
    parameter = document.get("components", {}).get("parameters", {}).get(component_name)
    if not isinstance(parameter, dict):
        fail(source, f"missing required header parameter component: {component_name}")
        return
    if parameter.get("name") != header_name or parameter.get("in") != "header":
        fail(source, f"{component_name} must define the {header_name} header")
    if parameter.get("required") is not True:
        fail(source, f"{component_name} must be required")


def validate_operation_parameter_ref(
    document: dict,
    source: Path,
    path_name: str,
    method: str,
    reference: str,
) -> None:
    operation = document.get("paths", {}).get(path_name, {}).get(method)
    if not isinstance(operation, dict):
        fail(source, f"missing operation {method.upper()} {path_name}")
        return
    references = {
        parameter.get("$ref")
        for parameter in operation.get("parameters", [])
        if isinstance(parameter, dict)
    }
    if reference not in references:
        fail(source, f"{method.upper()} {path_name} must reference {reference}")


def validate_machine_conformance(openapi_documents: dict[str, dict]) -> None:
    status_schema_path = ROOT / "schemas/server-api/device-status.schema.json"
    status_schema = load_json(status_schema_path)
    status_example_path = ROOT / "examples/device-status.json"
    status_example = load_json(status_example_path)
    if not isinstance(status_schema, dict) or not isinstance(status_example, dict):
        return

    if "sequence" not in status_schema.get("required", []):
        fail(status_schema_path, "sequence must remain required")
    sequence_schema = status_schema.get("properties", {}).get("sequence")
    if (
        not isinstance(sequence_schema, dict)
        or sequence_schema.get("type") != "integer"
        or sequence_schema.get("minimum") != 0
    ):
        fail(status_schema_path, "sequence must remain a non-negative integer")

    correlation_ref = "#/components/parameters/CorrelationId"
    json_request_operations = {
        "openapi/slamcore-server-v1.yaml": [
            ("/devices/register", "post"),
            ("/devices/{deviceId}/status", "post"),
        ],
        "openapi/slamcore-updater-v1.yaml": [
            ("/update", "post"),
            ("/rollback", "post"),
        ],
    }
    for relative, operations in json_request_operations.items():
        document = openapi_documents.get(relative)
        source = ROOT / relative
        if not isinstance(document, dict):
            continue
        validate_required_header_component(document, source, "CorrelationId", "X-Correlation-Id")
        correlation = (
            document.get("components", {})
            .get("parameters", {})
            .get("CorrelationId", {})
        )
        if not isinstance(correlation.get("example"), str):
            fail(source, "CorrelationId must provide a string header example")
        for path_name, method in operations:
            validate_operation_parameter_ref(
                document, source, path_name, method, correlation_ref)

    server_relative = "openapi/slamcore-server-v1.yaml"
    server_path = ROOT / server_relative
    server = openapi_documents.get(server_relative)
    if not isinstance(server, dict):
        return
    status_key_ref = "#/components/parameters/StatusIdempotencyKey"
    validate_required_header_component(
        server, server_path, "StatusIdempotencyKey", "Idempotency-Key")
    validate_operation_parameter_ref(
        server, server_path, "/devices/{deviceId}/status", "post", status_key_ref)
    status_operation = (
        server.get("paths", {})
        .get("/devices/{deviceId}/status", {})
        .get("post", {})
    )
    if "409" not in status_operation.get("responses", {}):
        fail(
            server_path,
            "POST /devices/{deviceId}/status must expose idempotency conflict response 409",
        )

    status_key = (
        server.get("components", {})
        .get("parameters", {})
        .get("StatusIdempotencyKey", {})
    )
    key_example = status_key.get("example")
    key_pattern = status_key.get("schema", {}).get("pattern")
    if (
        not isinstance(key_example, str)
        or not isinstance(key_pattern, str)
        or re.fullmatch(key_pattern, key_example) is None
    ):
        fail(server_path, "status Idempotency-Key example must match its declared format")
    else:
        sequence_suffix = key_example.rsplit(":", 1)[-1]
        if (
            not isinstance(status_example.get("sequence"), int)
            or sequence_suffix != str(status_example["sequence"])
        ):
            fail(
                server_path,
                "status Idempotency-Key example suffix must equal "
                "examples/device-status.json sequence",
            )

    external_value = (
        server.get("paths", {})
        .get("/devices/{deviceId}/status", {})
        .get("post", {})
        .get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("examples", {})
        .get("initialStatus", {})
        .get("externalValue")
    )
    if external_value != "../examples/device-status.json":
        fail(server_path, "status request example must reference examples/device-status.json")


def validate_explicit_command_conformance(openapi_documents: dict[str, dict]) -> None:
    schema_path = ROOT / "schemas/server-api/device-command.schema.json"
    update_example_path = ROOT / "examples/device-command-update.json"
    rollback_example_path = ROOT / "examples/device-command-rollback.json"
    rollback_request_path = ROOT / "examples/rollback-request.json"
    schema = load_json(schema_path)
    update = load_json(update_example_path)
    rollback = load_json(rollback_example_path)
    rollback_request = load_json(rollback_request_path)
    if not all(isinstance(value, dict) for value in
               (schema, update, rollback, rollback_request)):
        return

    if len(schema.get("oneOf", [])) != 2:
        fail(schema_path, "must define exactly two discriminated command variants")
    if update.get("commandType") != "update":
        fail(update_example_path, "commandType must be update")
    if rollback.get("commandType") != "rollback":
        fail(rollback_example_path, "commandType must be rollback")
    if rollback.get("jobId") == rollback.get("originalUpdateJobId"):
        fail(rollback_example_path, "rollback command R must be independent from original update U")
    if rollback_request.get("jobId") != rollback.get("originalUpdateJobId"):
        fail(rollback_request_path, "Updater rollback jobId must equal originalUpdateJobId U")

    package_fields = {"targetVersion", "packageUrl", "packageSha256", "platform"}
    contradictory = sorted(package_fields.intersection(rollback))
    if contradictory:
        fail(rollback_example_path, f"rollback must omit package/target fields: {contradictory}")
    if "originalUpdateJobId" in update:
        fail(update_example_path, "update must omit originalUpdateJobId")

    server_relative = "openapi/slamcore-server-v1.yaml"
    server_path = ROOT / server_relative
    server = openapi_documents.get(server_relative)
    if isinstance(server, dict):
        command_schema_ref = (
            server.get("paths", {})
            .get("/devices/{deviceId}/command", {})
            .get("get", {})
            .get("responses", {})
            .get("200", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
            .get("$ref")
        )
        if command_schema_ref != "../schemas/server-api/device-command.schema.json":
            fail(server_path, "/command must reference device-command.schema.json")
        examples = (
            server.get("paths", {})
            .get("/devices/{deviceId}/command", {})
            .get("get", {})
            .get("responses", {})
            .get("200", {})
            .get("content", {})
            .get("application/json", {})
            .get("examples", {})
        )
        expected = {
            "update": "../examples/device-command-update.json",
            "rollback": "../examples/device-command-rollback.json",
        }
        for name, external_value in expected.items():
            if examples.get(name, {}).get("externalValue") != external_value:
                fail(server_path, f"/command {name} example must reference {external_value}")

        legacy_description = (
            server.get("paths", {})
            .get("/devices/{deviceId}/update", {})
            .get("get", {})
            .get("description", "")
        )
        if "update-only" not in legacy_description:
            fail(server_path, "legacy /update endpoint must remain explicitly update-only")

    updater_relative = "openapi/slamcore-updater-v1.yaml"
    updater_path = ROOT / updater_relative
    updater = openapi_documents.get(updater_relative)
    if isinstance(updater, dict):
        rollback_operation = updater.get("paths", {}).get("/rollback", {}).get("post", {})
        schema_ref = (
            rollback_operation.get("requestBody", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
            .get("$ref")
        )
        if schema_ref != "../schemas/updater-api/rollback-request.schema.json":
            fail(updater_path, "POST /rollback must reference rollback-request.schema.json")
        external_value = (
            rollback_operation.get("requestBody", {})
            .get("content", {})
            .get("application/json", {})
            .get("examples", {})
            .get("explicitRollback", {})
            .get("externalValue")
        )
        if external_value != "../examples/rollback-request.json":
            fail(updater_path, "POST /rollback must reference examples/rollback-request.json")

        rollback_key_ref = "#/components/parameters/RollbackIdempotencyKey"
        validate_required_header_component(
            updater, updater_path, "RollbackIdempotencyKey", "Idempotency-Key")
        validate_operation_parameter_ref(
            updater, updater_path, "/rollback", "post", rollback_key_ref)
        validate_operation_parameter_ref(
            updater,
            updater_path,
            "/update",
            "post",
            "#/components/parameters/IdempotencyKey",
        )
        rollback_key = (
            updater.get("components", {})
            .get("parameters", {})
            .get("RollbackIdempotencyKey", {})
        )
        key_example = rollback_key.get("example")
        key_pattern = rollback_key.get("schema", {}).get("pattern")
        expected_key = f"rollback:{rollback_request['jobId']}"
        if key_example != expected_key:
            fail(updater_path, "rollback key example must equal rollback:<body.jobId>")
        if not isinstance(key_pattern, str) or re.fullmatch(key_pattern, expected_key) is None:
            fail(updater_path, "rollback key pattern must accept rollback:<body.jobId>")


def main() -> int:
    for path in ROOT.rglob("*.json"):
        document = load_json(path)
        if document is not None:
            check_refs(document, path)
            if path.is_relative_to(ROOT / "schemas"):
                try:
                    Draft202012Validator.check_schema(document)
                except Exception as exc:
                    fail(path, f"invalid Draft 2020-12 schema: {exc}")

    mappings = {
        "examples/device-status.json": "schemas/server-api/device-status.schema.json",
        "examples/device-command-update.json": "schemas/server-api/device-command.schema.json",
        "examples/device-command-rollback.json": "schemas/server-api/device-command.schema.json",
        "examples/update-request.json": "schemas/updater-api/update-request.schema.json",
        "examples/rollback-request.json": "schemas/updater-api/rollback-request.schema.json",
        "examples/update-status.json": "schemas/common/update-status.schema.json",
        "examples/error-response.json": "schemas/common/error-response.schema.json",
        "examples/slamcore-package.json": "schemas/release/slamcore-package.schema.json",
    }
    for instance, schema in mappings.items():
        validate_instance(ROOT / instance, ROOT / schema)

    invalid_mappings = {
        "examples/invalid/device-command-rollback-missing-original.json":
            "schemas/server-api/device-command.schema.json",
        "examples/invalid/device-command-update-missing-package-url.json":
            "schemas/server-api/device-command.schema.json",
        "examples/invalid/device-command-unknown-type.json":
            "schemas/server-api/device-command.schema.json",
        "examples/invalid/device-command-rollback-with-package-fields.json":
            "schemas/server-api/device-command.schema.json",
    }
    for instance, schema in invalid_mappings.items():
        validate_invalid_instance(ROOT / instance, ROOT / schema)

    validate_distinct_rollback_identity(
        ROOT / "examples/device-command-rollback.json", expect_valid=True)
    validate_instance(
        ROOT / "examples/invalid/device-command-rollback-reuses-original-id.json",
        ROOT / "schemas/server-api/device-command.schema.json",
    )
    validate_distinct_rollback_identity(
        ROOT / "examples/invalid/device-command-rollback-reuses-original-id.json",
        expect_valid=False,
    )

    for relative in [
        "examples/device-command-update.json",
        "examples/device-command-rollback.json",
        "examples/rollback-request.json",
    ]:
        validate_json_round_trip(ROOT / relative)

    validate_active_release_marker(ROOT / "examples/workspace-active-release.txt")

    expected_paths = {
        "openapi/slamcore-server-v1.yaml": {"/devices/register", "/devices/{deviceId}/update", "/devices/{deviceId}/command", "/devices/{deviceId}/status", "/devices/{deviceId}/history"},
        "openapi/slamcore-updater-v1.yaml": {"/status", "/update", "/update/{jobId}", "/rollback"},
    }
    openapi_documents: dict[str, dict] = {}
    for relative, required in expected_paths.items():
        path = ROOT / relative
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(document, dict) or document.get("openapi") != "3.1.0":
                fail(path, "must be an OpenAPI 3.1.0 mapping")
                continue
            openapi_documents[relative] = document
            missing = required - set(document.get("paths", {}))
            if missing:
                fail(path, f"missing required paths: {sorted(missing)}")
            check_refs(document, path)
            validation_document = copy.deepcopy(document)
            absolute_refs(validation_document, path)
            validate_spec(validation_document, base_uri=path.resolve().as_uri())
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            fail(path, f"invalid YAML: {exc}")
        except Exception as exc:
            fail(path, f"invalid OpenAPI document: {exc}")

    validate_machine_conformance(openapi_documents)
    validate_explicit_command_conformance(openapi_documents)

    version_path = ROOT / "VERSION"
    version = version_path.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", version):
        fail(version_path, "must contain a SemVer core version")
    elif version != "2.1.0":
        fail(version_path, "explicit rollback orchestration release must be 2.1.0")

    for relative, document in openapi_documents.items():
        if document.get("info", {}).get("version") != version:
            fail(ROOT / relative, f"info.version must match repository VERSION {version}")

    for path in [*ROOT.glob("schemas/**/*.json"), *ROOT.glob("openapi/*.yaml")]:
        text = path.read_text(encoding="utf-8")
        if "1.1" in text or '"building"' in text or " building" in text:
            fail(path, "contains a legacy Contract 1.1/building value")

    for path in [
        ROOT / "schemas/release/slamcore-build-manifest.schema.json",
        ROOT / "examples/slamcore-build-manifest.json",
        ROOT / "schemas/release/slamcore-release.schema.json",
        ROOT / "examples/slamcore-release.env",
    ]:
        if path.exists():
            fail(path, "legacy Contract 1.x artifact must remain removed")

    if ERRORS:
        print("Contract validation failed:", file=sys.stderr)
        for error in ERRORS:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(
        "Contract validation passed: JSON, schemas, examples, package metadata, "
        "active marker, OpenAPI, references, status and rollback idempotency, "
        "explicit command variants and invalid cases, JSON round trips, "
        "JSON-request correlation headers, ownership invariants, and VERSION are valid."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
