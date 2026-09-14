#!/usr/bin/env python3
"""
Merge structural QC, FAIRe-fier validation, and contextual QC into one
canonical dataset-readiness result.

The canonical machine-readable output is:
    dataset_readiness.json

Readiness policy used by this prototype:
- READY: all validation layers PASS
- REVIEW_REQUIRED: no FAIL/SYSTEM_ERROR, but at least one WARN
- NOT_READY: at least one validation layer FAIL
- SYSTEM_ERROR: at least one validation layer reports SYSTEM_ERROR/UNKNOWN

Warnings therefore require human review and do not count as publication-ready.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


CHECK_LABELS = {
    "structural_qc": "Structural / lab-return QC",
    "faire_qc": "FAIRe checklist QC",
    "context_qc": "Contextual / plausibility QC",
}

CHECK_ACTIONS = {
    "structural_qc": {
        "fail": "Review workbook structure and lab-return content before continuing.",
        "warn": "Review structural/lab-return warnings before continuing.",
    },
    "faire_qc": {
        "fail": "Correct FAIRe projectMetadata/sampleMetadata errors and re-run validation.",
        "warn": "Review FAIRe warnings and confirm whether correction is required.",
    },
    "context_qc": {
        "fail": "Review contextual QC errors such as coordinates, units, or implausible values.",
        "warn": "Review contextual plausibility warnings and approve or correct them.",
    },
}


class MergeInputError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise MergeInputError(f"Required summary file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise MergeInputError(f"Unable to parse JSON '{path}': {exc}") from exc


def normalize_status(value: Any) -> str:
    status = str(value or "UNKNOWN").strip().upper()
    aliases = {
        "SUCCESS": "PASS",
        "OK": "PASS",
        "WARNING": "WARN",
        "WARNINGS": "WARN",
        "ERROR": "FAIL",
        "FAILED": "FAIL",
    }
    return aliases.get(status, status)


def int_count(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def summarize_check(name: str, data: dict[str, Any], source: Path) -> dict[str, Any]:
    return {
        "label": CHECK_LABELS[name],
        "status": normalize_status(data.get("status")),
        "errors": int_count(data.get("errors")),
        "warnings": int_count(data.get("warnings")),
        "source_summary": source.name,
    }


def determine_readiness(checks: dict[str, dict[str, Any]]) -> tuple[str, bool, bool]:
    statuses = [v["status"] for v in checks.values()]

    if any(s in {"SYSTEM_ERROR", "UNKNOWN"} for s in statuses):
        return "SYSTEM_ERROR", False, True

    if any(s == "FAIL" for s in statuses):
        return "NOT_READY", False, True

    if any(s == "WARN" for s in statuses):
        return "REVIEW_REQUIRED", False, True

    if all(s == "PASS" for s in statuses):
        return "READY", True, False

    return "SYSTEM_ERROR", False, True


def build_actions(checks: dict[str, dict[str, Any]]) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    reviews: list[str] = []

    for name, check in checks.items():
        status = check["status"]
        label = check["label"]

        if status == "FAIL":
            blockers.append(
                f"{label}: {CHECK_ACTIONS[name]['fail']}"
            )
        elif status == "WARN":
            reviews.append(
                f"{label}: {CHECK_ACTIONS[name]['warn']}"
            )
        elif status in {"SYSTEM_ERROR", "UNKNOWN"}:
            blockers.append(
                f"{label}: validation did not complete with a usable status."
            )

    return blockers, reviews


def write_tsv(path: Path, result: dict[str, Any]) -> None:
    headers = [
        "dataset_readiness",
        "ready_for_publication",
        "review_required",
        "total_errors",
        "total_warnings",
        "structural_qc_status",
        "structural_qc_errors",
        "structural_qc_warnings",
        "faire_qc_status",
        "faire_qc_errors",
        "faire_qc_warnings",
        "context_qc_status",
        "context_qc_errors",
        "context_qc_warnings",
    ]

    checks = result["checks"]
    values = [
        result["dataset_readiness"],
        str(result["ready_for_publication"]).lower(),
        str(result["review_required"]).lower(),
        result["totals"]["errors"],
        result["totals"]["warnings"],
        checks["structural_qc"]["status"],
        checks["structural_qc"]["errors"],
        checks["structural_qc"]["warnings"],
        checks["faire_qc"]["status"],
        checks["faire_qc"]["errors"],
        checks["faire_qc"]["warnings"],
        checks["context_qc"]["status"],
        checks["context_qc"]["errors"],
        checks["context_qc"]["warnings"],
    ]

    with path.open("w", encoding="utf-8") as handle:
        handle.write("\t".join(map(str, headers)) + "\n")
        handle.write("\t".join(map(str, values)) + "\n")


def write_markdown(path: Path, result: dict[str, Any]) -> None:
    checks = result["checks"]

    lines = [
        "# Dataset readiness",
        "",
        f"**Readiness:** {result['dataset_readiness']}",
        f"**Ready for publication:** {result['ready_for_publication']}",
        f"**Human review required:** {result['review_required']}",
        "",
        "| Validation layer | Status | Errors | Warnings |",
        "|---|---:|---:|---:|",
    ]

    for name in ("structural_qc", "faire_qc", "context_qc"):
        item = checks[name]
        lines.append(
            f"| {item['label']} | {item['status']} | "
            f"{item['errors']} | {item['warnings']} |"
        )

    lines += [
        "",
        f"**Total errors:** {result['totals']['errors']}",
        f"**Total warnings:** {result['totals']['warnings']}",
    ]

    if result["blocking_checks"]:
        lines += ["", "## Blocking actions"]
        for item in result["blocking_checks"]:
            lines.append(f"- {item}")

    if result["review_checks"]:
        lines += ["", "## Review actions"]
        for item in result["review_checks"]:
            lines.append(f"- {item}")

    lines += [
        "",
        "## Prototype readiness policy",
        "",
        "A dataset is marked **READY** only when structural QC, FAIRe QC, "
        "and contextual QC all return PASS. WARN produces REVIEW_REQUIRED. "
        "FAIL produces NOT_READY.",
    ]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def merge_validation(
    structural_path: Path,
    faire_path: Path,
    context_path: Path,
    outdir: Path,
) -> dict[str, Any]:
    outdir.mkdir(parents=True, exist_ok=True)

    structural = load_json(structural_path)
    faire = load_json(faire_path)
    context = load_json(context_path)

    checks = {
        "structural_qc": summarize_check(
            "structural_qc", structural, structural_path
        ),
        "faire_qc": summarize_check(
            "faire_qc", faire, faire_path
        ),
        "context_qc": summarize_check(
            "context_qc", context, context_path
        ),
    }

    readiness, ready, review_required = determine_readiness(checks)
    blockers, reviews = build_actions(checks)

    total_errors = sum(x["errors"] for x in checks.values())
    total_warnings = sum(x["warnings"] for x in checks.values())

    result = {
        "schema_version": "0.1",
        "result_type": "edna_dataset_readiness",
        "pipeline_status": "SUCCESS",
        "dataset_readiness": readiness,
        "ready_for_publication": ready,
        "review_required": review_required,
        "totals": {
            "errors": total_errors,
            "warnings": total_warnings,
        },
        "checks": checks,
        "blocking_checks": blockers,
        "review_checks": reviews,
        "policy": {
            "ready_requires_all_checks_pass": True,
            "warnings_require_human_review": True,
            "validation_failure_does_not_mean_pipeline_failure": True,
        },
        "next_action": (
            "Proceed to publication/conversion workflow."
            if ready
            else (
                "Human review required before publication."
                if readiness == "REVIEW_REQUIRED"
                else "Resolve blocking validation findings and re-run the workflow."
            )
        ),
        "outputs": [
            "dataset_readiness.json",
            "dataset_readiness.tsv",
            "dataset_readiness.md",
        ],
    }

    (outdir / "dataset_readiness.json").write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )
    write_tsv(outdir / "dataset_readiness.tsv", result)
    write_markdown(outdir / "dataset_readiness.md", result)

    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Merge eDNA validation summaries into one dataset-readiness result."
    )
    parser.add_argument("--structural", required=True, type=Path)
    parser.add_argument("--faire", required=True, type=Path)
    parser.add_argument("--context", required=True, type=Path)
    parser.add_argument("--outdir", required=True, type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        result = merge_validation(
            args.structural.resolve(),
            args.faire.resolve(),
            args.context.resolve(),
            args.outdir.resolve(),
        )
    except Exception as exc:
        args.outdir.mkdir(parents=True, exist_ok=True)
        result = {
            "schema_version": "0.1",
            "result_type": "edna_dataset_readiness",
            "pipeline_status": "FAILED_AT_MERGE",
            "dataset_readiness": "SYSTEM_ERROR",
            "ready_for_publication": False,
            "review_required": True,
            "message": f"{type(exc).__name__}: {exc}",
            "outputs": ["dataset_readiness.json"],
        }
        (args.outdir / "dataset_readiness.json").write_text(
            json.dumps(result, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(result, indent=2))
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
