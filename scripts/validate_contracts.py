from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).parents[1]
OPENAPI = ROOT / "docs" / "enterprise-qa-system" / "openapi.yaml"
YAML_FILES = [
    OPENAPI,
    ROOT / "docs" / "enterprise-qa-system" / "s0" / "manifest.yaml",
    ROOT / "docs" / "enterprise-qa-system" / "s1" / "manifest.yaml",
    ROOT / "docs" / "enterprise-qa-system" / "s2" / "manifest.yaml",
    ROOT / "docs" / "enterprise-qa-system" / "s3" / "manifest.yaml",
    ROOT / "docs" / "enterprise-qa-system" / "s4" / "manifest.yaml",
    ROOT / "infra" / "compose" / "compose.yaml",
    ROOT / "infra" / "helm" / "qa-system" / "Chart.yaml",
    ROOT / "infra" / "helm" / "qa-system" / "values.yaml",
]


def walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def resolve(document: dict[str, Any], reference: str) -> Any:
    if not reference.startswith("#/"):
        raise ValueError(f"external reference is not allowed: {reference}")
    current: Any = document
    for raw_part in reference[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"unresolved OpenAPI reference: {reference}")
        current = current[part]
    return current


def main() -> int:
    parsed: dict[Path, Any] = {}
    for path in YAML_FILES:
        parsed[path] = yaml.safe_load(path.read_text(encoding="utf-8"))
        if parsed[path] is None:
            raise ValueError(f"empty YAML document: {path}")
    openapi = parsed[OPENAPI]
    if not isinstance(openapi, dict) or openapi.get("openapi") != "3.1.0":
        raise ValueError("OpenAPI must use 3.1.0")
    references = []
    for item in walk(openapi):
        reference = item.get("$ref")
        if reference is not None:
            references.append(str(reference))
            resolve(openapi, str(reference))
    required_paths = {
        "/knowledge-bases",
        "/knowledge-bases/{knowledge_base_id}/documents",
        "/documents/{document_id}/versions",
        "/documents/{document_id}/upload-complete",
        "/documents/{document_id}",
        "/ingestion-jobs/{job_id}",
        "/ingestion-jobs/{job_id}/retry",
        "/retrieval/search",
        "/messages/{message_id}/feedback",
        "/messages/{message_id}/citations/{citation_id}",
    }
    missing = required_paths - set(openapi.get("paths", {}))
    if missing:
        raise ValueError(f"missing S4 paths: {sorted(missing)}")
    print(
        f"contract validation passed: yaml_files={len(YAML_FILES)} "
        f"openapi_refs={len(references)} paths={len(openapi['paths'])}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"contract validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
