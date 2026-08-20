#!/usr/bin/env python3
"""Validate the SlamCore OTA contract without running product code."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urldefrag

import yaml
from jsonschema import Draft202012Validator, FormatChecker

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


def parse_release(path: Path) -> dict[str, str] | None:
    result: dict[str, str] = {}
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        fail(path, f"cannot read UTF-8 release metadata: {exc}")
        return None
    if b"\r" in raw:
        fail(path, "must use LF line endings")
    for number, line in enumerate(text.splitlines(), 1):
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            fail(path, f"line {number} is not KEY=VALUE")
            continue
        key, value = line.split("=", 1)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) or not value:
            fail(path, f"line {number} has an invalid key or empty value")
        elif key in result:
            fail(path, f"line {number} duplicates {key}")
        result[key] = value
    return result


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
        "examples/update-request.json": "schemas/updater-api/update-request.schema.json",
        "examples/update-status.json": "schemas/common/update-status.schema.json",
        "examples/error-response.json": "schemas/common/error-response.schema.json",
        "examples/slamcore-build-manifest.json": "schemas/release/slamcore-build-manifest.schema.json",
    }
    for instance, schema in mappings.items():
        validate_instance(ROOT / instance, ROOT / schema)

    release_path = ROOT / "examples/slamcore-release.env"
    parsed = parse_release(release_path)
    if parsed is not None:
        validate_instance(release_path, ROOT / "schemas/release/slamcore-release.schema.json", parsed)

    expected_paths = {
        "openapi/slamcore-server-v1.yaml": {"/devices/register", "/devices/{deviceId}/update", "/devices/{deviceId}/status", "/devices/{deviceId}/history"},
        "openapi/slamcore-updater-v1.yaml": {"/status", "/update", "/update/{jobId}", "/rollback"},
    }
    for relative, required in expected_paths.items():
        path = ROOT / relative
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(document, dict) or document.get("openapi") != "3.1.0":
                fail(path, "must be an OpenAPI 3.1.0 mapping")
                continue
            missing = required - set(document.get("paths", {}))
            if missing:
                fail(path, f"missing required paths: {sorted(missing)}")
            check_refs(document, path)
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            fail(path, f"invalid YAML: {exc}")

    version_path = ROOT / "VERSION"
    version = version_path.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", version):
        fail(version_path, "must contain a SemVer core version")

    if ERRORS:
        print("Contract validation failed:", file=sys.stderr)
        for error in ERRORS:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Contract validation passed: JSON, schemas, examples, release metadata, OpenAPI, references, and VERSION are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
