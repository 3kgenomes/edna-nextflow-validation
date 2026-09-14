#!/usr/bin/env python3
"""
Contextual QC for marine eDNA metadata.

This is intentionally separate from FAIRe-fier:
- FAIRe-fier checks checklist/schema compliance.
- CONTEXT_QC checks project-specific plausibility and normalization.

Current checks:
- decimalLatitude / decimalLongitude are numeric and globally valid;
- coordinates fall within a configured project bounding box;
- coordinates match expected hemispheres;
- configured measurement fields use allowed units;
- measurement values are normalized to a canonical unit;
- normalized values outside configured plausible ranges are flagged.

The module does not silently modify the submitted workbook. Normalized values
are written to context_qc_normalized.tsv for review/use downstream.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd


class ContextQCInputError(RuntimeError):
    pass


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except Exception:
        pass
    return isinstance(value, str) and value.strip() == ""


def parse_number(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("Boolean is not a numeric measurement.")
    if isinstance(value, (int, float)) and not pd.isna(value):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if cleaned == "":
            raise ValueError("Empty value.")
        return float(cleaned)
    raise ValueError(f"Unsupported numeric value: {value!r}")


def read_sample_metadata(filepath: Path) -> pd.DataFrame:
    if filepath.suffix.lower() not in {".xlsx", ".xls"}:
        raise ContextQCInputError("Input must be an Excel workbook (.xlsx/.xls).")

    try:
        with pd.ExcelFile(filepath) as xlsx:
            sheets = list(xlsx.sheet_names)
            sheet = (
                "sampleMetadata_revise"
                if "sampleMetadata_revise" in sheets
                else "sampleMetadata"
            )
            if sheet not in sheets:
                raise ContextQCInputError(
                    "sampleMetadata or sampleMetadata_revise worksheet not found."
                )

            skiprows = 0 if sheet == "sampleMetadata_revise" else 2
            df = pd.read_excel(
                xlsx,
                sheet_name=sheet,
                header=0,
                skiprows=skiprows,
            )
    except ContextQCInputError:
        raise
    except Exception as exc:
        raise ContextQCInputError(f"Unable to read sample metadata: {exc}") from exc

    if "samp_name" not in df.columns:
        raise ContextQCInputError("Column 'samp_name' was not found in sampleMetadata.")

    return df


def load_config(path: Path) -> dict[str, Any]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ContextQCInputError(f"Unable to read context QC config: {exc}") from exc

    if "region" not in config:
        raise ContextQCInputError("Context QC config must contain a 'region' object.")
    return config


def add_issue(
    issues: list[dict[str, Any]],
    *,
    record: str,
    severity: str,
    field: str,
    rule: str,
    input_value: Any = None,
    input_unit: Any = None,
    normalized_value: Any = None,
    normalized_unit: Any = None,
    message: str,
) -> None:
    issues.append(
        {
            "record": record,
            "severity": severity,
            "field": field,
            "rule": rule,
            "input_value": input_value,
            "input_unit": input_unit,
            "normalized_value": normalized_value,
            "normalized_unit": normalized_unit,
            "message": message,
        }
    )


def hemisphere_mismatch(value: float, hemisphere: str | None) -> bool:
    if not hemisphere:
        return False
    h = hemisphere.strip().lower()
    if h == "south":
        return value > 0
    if h == "north":
        return value < 0
    if h == "east":
        return value < 0
    if h == "west":
        return value > 0
    return False


def check_coordinates(
    df: pd.DataFrame,
    config: dict[str, Any],
    issues: list[dict[str, Any]],
) -> None:
    region = config["region"]
    required = ["decimalLatitude", "decimalLongitude"]
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        raise ContextQCInputError(
            "Coordinate column(s) missing from sampleMetadata: "
            + ", ".join(missing_cols)
        )

    for _, row in df.iterrows():
        record = str(row.get("samp_name", "")).strip()

        values: dict[str, float | None] = {}
        for field, global_min, global_max in (
            ("decimalLatitude", -90.0, 90.0),
            ("decimalLongitude", -180.0, 180.0),
        ):
            raw = row.get(field)
            if is_blank(raw):
                # Missing mandatory/required fields are already FAIRe-fier territory.
                # CONTEXT_QC avoids duplicating that error.
                values[field] = None
                continue
            try:
                value = parse_number(raw)
                values[field] = value
            except Exception:
                values[field] = None
                add_issue(
                    issues,
                    record=record,
                    severity="ERROR",
                    field=field,
                    rule="coordinate_numeric",
                    input_value=raw,
                    message=f"{field} must be numeric.",
                )
                continue

            if not (global_min <= value <= global_max):
                add_issue(
                    issues,
                    record=record,
                    severity="ERROR",
                    field=field,
                    rule="coordinate_global_range",
                    input_value=raw,
                    message=(
                        f"{field}={value} is outside the valid global range "
                        f"{global_min} to {global_max}."
                    ),
                )

        lat = values.get("decimalLatitude")
        lon = values.get("decimalLongitude")

        if lat is not None and -90 <= lat <= 90:
            expected = region.get("expected_latitude_hemisphere")
            if hemisphere_mismatch(lat, expected):
                add_issue(
                    issues,
                    record=record,
                    severity="ERROR",
                    field="decimalLatitude",
                    rule="latitude_hemisphere",
                    input_value=lat,
                    message=(
                        f"Latitude {lat} is inconsistent with the configured "
                        f"{expected}ern hemisphere. A missing sign may be present."
                    ),
                )

            min_lat = region.get("min_latitude")
            max_lat = region.get("max_latitude")
            if (
                min_lat is not None
                and max_lat is not None
                and not (float(min_lat) <= lat <= float(max_lat))
            ):
                add_issue(
                    issues,
                    record=record,
                    severity="ERROR",
                    field="decimalLatitude",
                    rule="project_bounding_box",
                    input_value=lat,
                    message=(
                        f"Latitude {lat} falls outside configured project region "
                        f"[{min_lat}, {max_lat}]."
                    ),
                )

        if lon is not None and -180 <= lon <= 180:
            expected = region.get("expected_longitude_hemisphere")
            if hemisphere_mismatch(lon, expected):
                add_issue(
                    issues,
                    record=record,
                    severity="ERROR",
                    field="decimalLongitude",
                    rule="longitude_hemisphere",
                    input_value=lon,
                    message=(
                        f"Longitude {lon} is inconsistent with the configured "
                        f"{expected}ern hemisphere."
                    ),
                )

            min_lon = region.get("min_longitude")
            max_lon = region.get("max_longitude")
            if (
                min_lon is not None
                and max_lon is not None
                and not (float(min_lon) <= lon <= float(max_lon))
            ):
                add_issue(
                    issues,
                    record=record,
                    severity="ERROR",
                    field="decimalLongitude",
                    rule="project_bounding_box",
                    input_value=lon,
                    message=(
                        f"Longitude {lon} falls outside configured project region "
                        f"[{min_lon}, {max_lon}]."
                    ),
                )


def canonicalize_unit(unit: Any, spec: dict[str, Any]) -> str | None:
    if is_blank(unit):
        return None
    raw = str(unit).strip()
    allowed = spec.get("allowed_units", {})
    if raw in allowed:
        return raw
    aliases = spec.get("unit_aliases", {})
    return aliases.get(raw.lower())


def rule_applies(row: pd.Series, spec: dict[str, Any]) -> bool:
    """Return True when an optional rule condition matches the current row."""
    cond = spec.get("when")
    if not cond:
        return True

    field = cond.get("field")
    if not field or field not in row.index:
        return False

    raw = row.get(field)
    if is_blank(raw):
        return False

    values = cond.get("values", [])
    case_sensitive = bool(cond.get("case_sensitive", False))

    if case_sensitive:
        return str(raw).strip() in {str(v).strip() for v in values}

    observed = str(raw).strip().lower()
    expected = {str(v).strip().lower() for v in values}
    return observed in expected


def check_measurements(
    df: pd.DataFrame,
    config: dict[str, Any],
    issues: list[dict[str, Any]],
    normalized: list[dict[str, Any]],
) -> None:
    """
    Apply config-driven measurement rules.

    Multiple rules can target the same fields under different conditions.
    Example: samp_size is a volume for Niskin samples, but a distance for tow
    samples. This avoids assuming every samp_size value uses L/mL.
    """
    for spec in config.get("measurement_rules", []):
        rule_name = spec.get("name", "measurement_rule")
        value_field = spec["value_field"]
        unit_field = spec["unit_field"]

        if value_field not in df.columns:
            continue
        if unit_field not in df.columns:
            raise ContextQCInputError(
                f"Configured unit field '{unit_field}' is missing for '{value_field}'."
            )

        canonical = spec["canonical_unit"]
        allowed_units = spec.get("allowed_units", {})

        for _, row in df.iterrows():
            if not rule_applies(row, spec):
                continue

            record = str(row.get("samp_name", "")).strip()
            raw_value = row.get(value_field)
            raw_unit = row.get(unit_field)

            if is_blank(raw_value):
                continue

            try:
                numeric_value = parse_number(raw_value)
            except Exception:
                add_issue(
                    issues,
                    record=record,
                    severity="ERROR",
                    field=value_field,
                    rule=f"{rule_name}:measurement_numeric",
                    input_value=raw_value,
                    input_unit=raw_unit,
                    message=f"{value_field} must be numeric before unit normalization.",
                )
                continue

            unit = canonicalize_unit(raw_unit, spec)
            if unit is None:
                if is_blank(raw_unit):
                    add_issue(
                        issues,
                        record=record,
                        severity="ERROR",
                        field=unit_field,
                        rule=f"{rule_name}:missing_unit",
                        input_value=raw_value,
                        input_unit=raw_unit,
                        message=(
                            f"{value_field} has a value ({raw_value}) but "
                            f"{unit_field} is missing for rule '{rule_name}'."
                        ),
                    )
                else:
                    add_issue(
                        issues,
                        record=record,
                        severity="ERROR",
                        field=unit_field,
                        rule=f"{rule_name}:unsupported_unit",
                        input_value=raw_value,
                        input_unit=raw_unit,
                        message=(
                            f"Unsupported unit '{raw_unit}' for rule '{rule_name}'. "
                            f"Allowed units/aliases normalize to: "
                            f"{', '.join(sorted(allowed_units.keys()))}."
                        ),
                    )
                continue

            factor = float(allowed_units[unit])
            normalized_value = numeric_value * factor

            normalized.append(
                {
                    "record": record,
                    "rule": rule_name,
                    "field": value_field,
                    "original_value": raw_value,
                    "original_unit": raw_unit,
                    "normalized_value": normalized_value,
                    "normalized_unit": canonical,
                }
            )

            min_v = spec.get("plausible_min_canonical")
            max_v = spec.get("plausible_max_canonical")
            if min_v is not None and normalized_value < float(min_v):
                add_issue(
                    issues,
                    record=record,
                    severity="WARNING",
                    field=value_field,
                    rule=f"{rule_name}:implausible_low",
                    input_value=raw_value,
                    input_unit=raw_unit,
                    normalized_value=normalized_value,
                    normalized_unit=canonical,
                    message=spec.get(
                        "plausibility_message",
                        f"Normalized {value_field} is below the configured plausible range.",
                    ),
                )
            elif max_v is not None and normalized_value > float(max_v):
                add_issue(
                    issues,
                    record=record,
                    severity="WARNING",
                    field=value_field,
                    rule=f"{rule_name}:implausible_high",
                    input_value=raw_value,
                    input_unit=raw_unit,
                    normalized_value=normalized_value,
                    normalized_unit=canonical,
                    message=spec.get(
                        "plausibility_message",
                        f"Normalized {value_field} is above the configured plausible range.",
                    ),
                )

def run_context_qc(
    input_path: Path,
    config_path: Path,
    outdir: Path,
) -> dict[str, Any]:
    outdir.mkdir(parents=True, exist_ok=True)
    config = load_config(config_path)
    df = read_sample_metadata(input_path)

    issues: list[dict[str, Any]] = []
    normalized: list[dict[str, Any]] = []

    check_coordinates(df, config, issues)
    check_measurements(df, config, issues, normalized)

    issue_columns = [
        "record",
        "severity",
        "field",
        "rule",
        "input_value",
        "input_unit",
        "normalized_value",
        "normalized_unit",
        "message",
    ]
    issue_df = pd.DataFrame(issues, columns=issue_columns)
    issue_df.to_csv(outdir / "context_qc_issues.tsv", sep="\t", index=False)

    norm_columns = [
        "record",
        "rule",
        "field",
        "original_value",
        "original_unit",
        "normalized_value",
        "normalized_unit",
    ]
    norm_df = pd.DataFrame(normalized, columns=norm_columns)
    norm_df.to_csv(outdir / "context_qc_normalized.tsv", sep="\t", index=False)

    errors = int((issue_df["severity"] == "ERROR").sum()) if not issue_df.empty else 0
    warnings_count = (
        int((issue_df["severity"] == "WARNING").sum()) if not issue_df.empty else 0
    )
    status = "FAIL" if errors else ("WARN" if warnings_count else "PASS")

    summary = {
        "validator": "eDNA contextual QC",
        "input_file": input_path.name,
        "config_file": config_path.name,
        "status": status,
        "errors": errors,
        "warnings": warnings_count,
        "records_checked": int(len(df)),
        "normalized_measurements": int(len(norm_df)),
        "region": config.get("region", {}),
        "outputs": [
            "context_qc_summary.json",
            "context_qc_issues.tsv",
            "context_qc_normalized.tsv",
        ],
        "scope_note": (
            "Contextual/project-specific QC only. FAIRe checklist compliance "
            "remains the responsibility of FAIRe-fier."
        ),
    }

    (outdir / "context_qc_summary.json").write_text(
        json.dumps(summary, indent=2, default=str),
        encoding="utf-8",
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run project-specific eDNA contextual QC.")
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--config", required=True, type=Path)
    p.add_argument("--outdir", required=True, type=Path)
    p.add_argument(
        "--fail-on-errors",
        action="store_true",
        help="Return exit code 2 if contextual QC status is FAIL.",
    )
    return p


def main() -> int:
    args = build_parser().parse_args()
    try:
        summary = run_context_qc(
            args.input.resolve(),
            args.config.resolve(),
            args.outdir.resolve(),
        )
    except Exception as exc:
        args.outdir.mkdir(parents=True, exist_ok=True)
        summary = {
            "validator": "eDNA contextual QC",
            "input_file": args.input.name,
            "config_file": args.config.name,
            "status": "SYSTEM_ERROR",
            "errors": 0,
            "warnings": 0,
            "message": f"{type(exc).__name__}: {exc}",
            "outputs": ["context_qc_summary.json"],
        }
        (args.outdir / "context_qc_summary.json").write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(summary, indent=2))
        return 1

    print(json.dumps(summary, indent=2))
    if args.fail_on_errors and summary["status"] == "FAIL":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
