#!/usr/bin/env python3
"""
Batch/CLI wrapper for FAIRe-fier.

This module reuses the deterministic validation functions in create_validator.py
without starting the Shiny UI. It preserves the FAIRe-fier project/sample
validation logic and adds machine-readable outputs for orchestration by
Nextflow, FastAPI, Sciansa, or a future web portal.

Expected files beside this script (or importable on PYTHONPATH):
    create_validator.py
    config_data.py

Example:
    python fairefier_batch.py \
        --input OcOm_2518_metadata.xlsx \
        --checklist FAIRe_checklist_v1.0.xlsx \
        --outdir fairefier_results

Exit behaviour:
    By default, a completed validation exits 0 even if the DATA fail validation.
    Inspect validation_summary.json for PASS/WARN/FAIL.
    Use --fail-on-errors if you explicitly want validation errors to return code 2.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pydantic import ValidationError

import create_validator
import config_data


TERM_NAME_COL = config_data.term_name_col
SAMP_NAME_COL = config_data.samp_name_col

WARN_COLOR = "#DDAA33"
ERROR_COLOR = "#BB5566"


class BatchInputError(RuntimeError):
    """Raised when the submitted workbook/checklist cannot be parsed."""


def read_worksheets(filepath: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Read projectMetadata and sampleMetadata using the same layout rules
    as the Shiny FAIRe-fier application.

    Supports resubmission of *_revise sheets.
    """
    if filepath.suffix.lower() not in {".xlsx", ".xls"}:
        raise BatchInputError(
            "Unsupported file type. Expected a single Excel file (.xlsx/.xls)."
        )

    try:
        # Use ExcelFile as a context manager so the underlying file handle is
        # closed before validation begins. This prevents delayed ResourceWarning
        # messages (for example "unclosed file <_io.BufferedReader ...>") from
        # being captured as if they were FAIRe metadata warnings.
        with pd.ExcelFile(filepath) as xlsx:
            sheet_names = list(xlsx.sheet_names)

            project_sheet = (
                "projectMetadata_revise"
                if "projectMetadata_revise" in sheet_names
                else "projectMetadata"
            )
            sample_sheet = (
                "sampleMetadata_revise"
                if "sampleMetadata_revise" in sheet_names
                else "sampleMetadata"
            )

            missing = [
                sheet
                for sheet in (project_sheet, sample_sheet)
                if sheet not in sheet_names
            ]
            if missing:
                raise BatchInputError(
                    "Required worksheet(s) not found. Expected "
                    "projectMetadata/projectMetadata_revise and "
                    "sampleMetadata/sampleMetadata_revise."
                )

            df_project = pd.read_excel(xlsx, sheet_name=project_sheet)

            # Original template contains requirement_level_code and section
            # before term_name. The Shiny app drops these first two columns.
            if project_sheet == "projectMetadata":
                df_project = df_project.iloc[:, 2:]

            # Original sampleMetadata has two descriptive rows before field names.
            skiprows = 0 if sample_sheet == "sampleMetadata_revise" else 2
            df_sample = pd.read_excel(
                xlsx,
                sheet_name=sample_sheet,
                header=0,
                skiprows=skiprows,
            )
    except BatchInputError:
        raise
    except Exception as exc:
        raise BatchInputError(f"Unable to read metadata worksheets: {exc}") from exc

    if TERM_NAME_COL not in df_project.columns:
        raise BatchInputError(
            f"Column '{TERM_NAME_COL}' was not found in {project_sheet}."
        )
    if SAMP_NAME_COL not in df_sample.columns:
        raise BatchInputError(
            f"Column '{SAMP_NAME_COL}' was not found in {sample_sheet}."
        )

    # Match the Shiny duplicate check.
    samp_col = df_sample[SAMP_NAME_COL]
    dup_mask = samp_col.duplicated(keep=False)
    if dup_mask.any():
        dup_samp = samp_col[dup_mask]
        summary = ", ".join(
            f"'{samp}' ({count} rows)"
            for samp, count in dup_samp.value_counts().items()
        )
        raise BatchInputError(
            f"Duplicate {SAMP_NAME_COL} in sampleMetadata worksheet: {summary}. "
            "Please ensure sample names are unique."
        )

    return df_project, df_sample


def load_checklist(
    checklist_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load checklist and split projectMetadata/sampleMetadata validation rules."""
    try:
        df_checklist = pd.read_excel(
            checklist_path,
            sheet_name="checklist",
            header=0,
        )
    except Exception as exc:
        raise BatchInputError(
            f"Unable to read checklist '{checklist_path}': {exc}"
        ) from exc

    required_cols = {
        "data_type",
        TERM_NAME_COL,
        "term_type",
        "requirement_level",
        "description",
    }
    missing = sorted(required_cols - set(df_checklist.columns))
    if missing:
        raise BatchInputError(
            "Checklist is missing required column(s): " + ", ".join(missing)
        )

    df_project = df_checklist[
        df_checklist["data_type"].astype(str).str.contains(
            "projectMetadata", na=False
        )
    ].copy()

    df_sample = df_checklist[
        df_checklist["data_type"].astype(str).str.contains(
            "sampleMetadata", na=False
        )
    ].copy()
    df_sample = df_sample[df_sample[TERM_NAME_COL] != SAMP_NAME_COL].copy()

    return df_checklist, df_project, df_sample


def combine_locmsgall(
    df: pd.DataFrame,
    group_colname: str,
    n_in_group: int,
) -> pd.DataFrame:
    """Port of FAIRe-fier's helper for collapsing repeated warning/error rows."""
    if df.empty:
        return df

    df = df.copy()

    if df["loc"].apply(lambda x: isinstance(x, list)).all():
        df["loc"] = df["loc"].str[0]

    grouped = (
        df.groupby(["loc", "msg"])[group_colname]
        .apply(lambda x: set(x))
        .reset_index()
    )
    grouped[group_colname] = grouped[group_colname].apply(
        lambda x: "ALL" if len(x) == n_in_group else None
    )

    df = df.merge(
        grouped,
        how="inner",
        on=["loc", "msg"],
        suffixes=(None, "_all"),
    )

    df = df[
        ~(
            df.duplicated(["loc", "msg"])
            & (df[f"{group_colname}_all"] == "ALL")
        )
    ]

    df[group_colname] = df.apply(
        lambda row: (
            row[group_colname]
            if row[f"{group_colname}_all"] is None
            else "ALL"
        ),
        axis=1,
    )
    df = df.drop(columns=[f"{group_colname}_all"])
    df.reset_index(drop=True, inplace=True)
    df.insert(0, group_colname, df.pop(group_colname))
    return df


def combine_difftypemsg(
    df: pd.DataFrame,
    group_colname: str,
) -> pd.DataFrame:
    """Port of FAIRe-fier's helper for merging related Pydantic error messages."""
    if df.empty:
        return df

    df = df.copy()
    df["input"] = df["input"].fillna("None")
    df["input"] = df["input"].astype("string")

    split_char = "; "
    df = (
        df.groupby([group_colname, "loc", "input"], as_index=False)
        .agg(
            {
                "type": lambda x: split_char.join(x.astype(str).unique()),
                "msg": lambda x: split_char.join(x.astype(str).unique()),
            }
        )
    )

    def remove_last_string_error(row: pd.Series) -> pd.Series:
        list_type = row["type"].split(split_char)
        list_msg = row["msg"].split(split_char)
        if (
            len(list_type) > 1
            and list_type[-1] == "string_type"
            and bool(__import__("re").search(r"\bstring\b", list_msg[-1]))
        ):
            list_type.pop()
            list_msg.pop()
            row["type"] = split_char.join(list_type)
            row["msg"] = split_char.join(list_msg)
        return row

    df = df.apply(remove_last_string_error, axis=1)
    df["input"] = df["input"].replace("None", None)
    return df


def get_nonempty_term(input_dict: dict[str, dict[str, Any]]) -> set[str]:
    """
    Extract fields populated at project_level and fields populated across
    every assay column, matching FAIRe-fier behaviour.
    """
    result: set[str] = set()

    project_level = input_dict.get("project_level", {})
    result.update(k for k, v in project_level.items() if v)

    other_dicts = {
        key: value
        for key, value in input_dict.items()
        if key != "project_level"
    }
    if other_dicts:
        first = next(iter(other_dicts.values()))
        for subkey in first.keys():
            if all(
                subkey in dictionary and dictionary[subkey]
                for dictionary in other_dicts.values()
            ):
                result.add(subkey)

    return result


def warnings_to_df(
    caught: list[warnings.WarningMessage],
    group_colname: str,
    group_value: str,
) -> pd.DataFrame:
    """
    Convert FAIRe-fier's pipe-delimited warning messages to a DataFrame.
    """
    if not caught:
        return pd.DataFrame()

    rows = []
    for warning in caught:
        text = str(warning.message)
        parts = [part.strip() for part in text.split("|")]
        while len(parts) < 4:
            parts.append("")
        rows.append(
            {
                group_colname: group_value,
                "loc": parts[0],
                "msg": parts[1],
                "input": parts[2],
                "output": parts[3],
            }
        )

    return pd.DataFrame(rows)


def validation_error_to_df(
    exc: ValidationError,
    group_colname: str,
    group_value: str,
) -> pd.DataFrame:
    """Convert Pydantic ValidationError to FAIRe-fier's tabular structure."""
    records = json.loads(
        exc.json(include_url=False, include_context=False)
    )
    df = pd.DataFrame(records)
    if df.empty:
        return df
    df.insert(0, group_colname, group_value)
    return df


def validate_metadata(
    df_input_project: pd.DataFrame,
    df_input_sample: pd.DataFrame,
    df_project_rules: pd.DataFrame,
    df_sample_rules: pd.DataFrame,
) -> dict[str, Any]:
    """
    Run the FAIRe-fier projectMetadata and sampleMetadata validation
    outside Shiny.
    """
    validator_messages: list[str] = []

    # ---------- projectMetadata ----------
    df_project_work = (
        df_input_project.fillna("")
        .set_index(TERM_NAME_COL)
        .T
    )
    dicts_project = df_project_work.to_dict("index")
    n_project_groups = len(df_project_work.index.unique())

    project_out: list[pd.DataFrame] = []
    project_warn: list[pd.DataFrame] = []
    project_error: list[pd.DataFrame] = []

    dict_meta_project = create_validator.create_dictterms(df_project_rules)
    mandatory_terms = {
        k for k, v in dict_meta_project.items() if v[1].is_required()
    }
    mandatory_to_optional = list(
        mandatory_terms.intersection(get_nonempty_term(dicts_project))
    )

    for study_assay, record in dicts_project.items():
        caught: list[warnings.WarningMessage] = []
        try:
            with warnings.catch_warnings(record=True) as caught:
                # FAIRe-fier communicates validation warnings with warnings.warn(),
                # whose default category is UserWarning. Ignore unrelated runtime
                # warnings so they do not become metadata issues.
                warnings.simplefilter("ignore")
                warnings.simplefilter("always", UserWarning)
                validated = create_validator.validate_projectMetadata(
                    df_project_rules,
                    dict_meta_project,
                    record,
                    mandatory_to_optional=mandatory_to_optional,
                )
            project_out.append(
                pd.DataFrame([validated], index=[study_assay])
            )
        except ValidationError as exc:
            project_error.append(
                validation_error_to_df(
                    exc,
                    TERM_NAME_COL,
                    str(study_assay),
                )
            )
        finally:
            warning_df = warnings_to_df(
                caught,
                TERM_NAME_COL,
                str(study_assay),
            )
            if not warning_df.empty:
                project_warn.append(warning_df)

    df_out_project = pd.DataFrame()
    df_warn_project = pd.DataFrame()
    df_error_project = pd.DataFrame()

    if project_out and not project_error:
        df_out_project = (
            pd.concat(project_out)
            .T
            .rename_axis(TERM_NAME_COL)
            .reset_index()
        )
        validator_messages.append("For projectMetadata: Success!")
    else:
        validator_messages.append(
            "For projectMetadata: Failed! Please review errors before resubmitting."
        )

    if project_warn:
        df_warn_project = pd.concat(project_warn, ignore_index=True)
        df_warn_project = combine_locmsgall(
            df_warn_project,
            TERM_NAME_COL,
            n_project_groups,
        )

    if project_error:
        df_error_project = pd.concat(project_error, ignore_index=True)
        df_error_project = combine_locmsgall(
            df_error_project,
            TERM_NAME_COL,
            n_project_groups,
        )
        df_error_project = combine_difftypemsg(
            df_error_project,
            TERM_NAME_COL,
        )
        # Do not output clean metadata if project validation contains errors.
        df_out_project = pd.DataFrame()

    # ---------- sampleMetadata ----------
    df_sample_work = (
        df_input_sample.fillna("")
        .set_index(SAMP_NAME_COL)
    )
    dicts_sample = df_sample_work.to_dict("index")
    n_samples = len(df_sample_work.index.unique())

    sample_out: list[pd.DataFrame] = []
    sample_warn: list[pd.DataFrame] = []
    sample_error: list[pd.DataFrame] = []

    informationwithheld_latlon = False
    project_level = dicts_project.get("project_level", {})
    input_informationwithheld = project_level.get("informationWithheld")
    if isinstance(input_informationwithheld, str):
        latlon_keywords = {
            "latitude",
            "longitude",
            "lat",
            "long",
            "gps",
            "coordinate",
            "location",
            "site",
        }
        if latlon_keywords.intersection(
            set(input_informationwithheld.lower().split())
        ):
            informationwithheld_latlon = True

    for samp_name, record in dicts_sample.items():
        caught: list[warnings.WarningMessage] = []
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("ignore")
                warnings.simplefilter("always", UserWarning)

                if informationwithheld_latlon:
                    warnings.warn(
                        "decimalLatitude | Latitude and/or longitude is mentioned "
                        "in informationWithheld. | Mandatory | Optional"
                    )
                    warnings.warn(
                        "decimalLongitude | Latitude and/or longitude is mentioned "
                        "in informationWithheld. | Mandatory | Optional"
                    )

                # Match original code: create a fresh model specification for
                # each sample because validate_sampleMetadata can modify it.
                dict_meta_sample = create_validator.create_dictterms(
                    df_sample_rules
                )

                validated = create_validator.validate_sampleMetadata(
                    df_sample_rules,
                    dict_meta_sample,
                    record,
                    inputs_pm=dicts_project,
                    informationwithheld_latlon=informationwithheld_latlon,
                )

            sample_out.append(
                pd.DataFrame([validated], index=[samp_name])
            )
        except ValidationError as exc:
            sample_error.append(
                validation_error_to_df(
                    exc,
                    SAMP_NAME_COL,
                    str(samp_name),
                )
            )
        finally:
            warning_df = warnings_to_df(
                caught,
                SAMP_NAME_COL,
                str(samp_name),
            )
            if not warning_df.empty:
                sample_warn.append(warning_df)

    df_out_sample = pd.DataFrame()
    df_warn_sample = pd.DataFrame()
    df_error_sample = pd.DataFrame()

    if sample_out and not sample_error:
        df_out_sample = (
            pd.concat(sample_out)
            .rename_axis(SAMP_NAME_COL)
            .reset_index()
        )
        validator_messages.append("For sampleMetadata: Success!")
    else:
        validator_messages.append(
            "For sampleMetadata: Failed! Please review errors before resubmitting."
        )

    if sample_warn:
        df_warn_sample = pd.concat(sample_warn, ignore_index=True)
        df_warn_sample = combine_locmsgall(
            df_warn_sample,
            SAMP_NAME_COL,
            n_samples,
        )

    if sample_error:
        df_error_sample = pd.concat(sample_error, ignore_index=True)
        df_error_sample = combine_locmsgall(
            df_error_sample,
            SAMP_NAME_COL,
            n_samples,
        )
        df_error_sample = combine_difftypemsg(
            df_error_sample,
            SAMP_NAME_COL,
        )
        # Do not output clean metadata if sample validation contains errors.
        df_out_sample = pd.DataFrame()

    return {
        "message": "\n".join(validator_messages),
        "input_project": df_input_project,
        "input_sample": df_input_sample,
        "output_project": df_out_project,
        "warning_project": df_warn_project,
        "error_project": df_error_project,
        "output_sample": df_out_sample,
        "warning_sample": df_warn_sample,
        "error_sample": df_error_sample,
    }


def highlight_cells_by_group_loc(
    df: pd.DataFrame,
    df_issues: pd.DataFrame,
    group_colname: str,
    color: str,
    group_colname_as_header: bool = False,
) -> pd.DataFrame:
    """Create a Styler-compatible map for highlighting revision cells."""
    style = pd.DataFrame("", index=df.index, columns=df.columns)

    if df_issues.empty:
        return style

    for group_value, loc in df_issues[[group_colname, "loc"]].values:
        if group_value is None or loc is None:
            continue
        group_value = str(group_value).strip()
        loc = str(loc).strip()

        if group_colname_as_header:
            if loc in df[group_colname].astype(str).values and group_value in df.columns:
                style.loc[df[group_colname].astype(str) == loc, group_value] = (
                    f"background-color: {color}"
                )
        else:
            if group_colname in df.columns and loc in df.columns:
                style.loc[
                    df[group_colname].astype(str) == group_value,
                    loc,
                ] = f"background-color: {color}"

    return style


def write_validated_workbook(
    outpath: Path,
    result: dict[str, Any],
) -> None:
    """Write clean validated metadata workbook, matching Shiny output structure."""
    with pd.ExcelWriter(outpath, engine="openpyxl") as writer:
        result["output_project"].to_excel(
            writer,
            sheet_name="projectMetadata",
            index=False,
        )
        result["output_sample"].to_excel(
            writer,
            sheet_name="sampleMetadata",
            index=False,
        )


def write_revision_workbook(
    outpath: Path,
    result: dict[str, Any],
) -> None:
    """
    Write warning/error tables plus *_revise sheets with highlighted cells.
    """
    in_project = result["input_project"].copy()
    in_sample = result["input_sample"].copy()
    warn_project = result["warning_project"].copy()
    error_project = result["error_project"].copy()
    warn_sample = result["warning_sample"].copy()
    error_sample = result["error_sample"].copy()

    styler_project = in_project.style
    styler_sample = in_sample.style

    if not warn_project.empty:
        all_warn_locs = (
            warn_project.loc[
                warn_project[TERM_NAME_COL] == "ALL", "loc"
            ]
            .astype(str)
            .str.strip()
            .unique()
        )
        styler_project = styler_project.apply(
            lambda x: np.where(
                x.isin(all_warn_locs),
                f"background-color: {WARN_COLOR}",
                "",
            ),
            axis=None,
        ).apply(
            lambda df: highlight_cells_by_group_loc(
                df,
                warn_project[warn_project[TERM_NAME_COL] != "ALL"],
                TERM_NAME_COL,
                WARN_COLOR,
                group_colname_as_header=True,
            ),
            axis=None,
        )

    if not error_project.empty:
        all_error_locs = (
            error_project.loc[
                error_project[TERM_NAME_COL] == "ALL", "loc"
            ]
            .astype(str)
            .str.strip()
            .unique()
        )
        styler_project = styler_project.apply(
            lambda x: np.where(
                x.isin(all_error_locs),
                f"background-color: {ERROR_COLOR}",
                "",
            ),
            axis=None,
        ).apply(
            lambda df: highlight_cells_by_group_loc(
                df,
                error_project[error_project[TERM_NAME_COL] != "ALL"],
                TERM_NAME_COL,
                ERROR_COLOR,
                group_colname_as_header=True,
            ),
            axis=None,
        )

    if not warn_sample.empty:
        warn_all_locs = (
            warn_sample.loc[
                warn_sample[SAMP_NAME_COL] == "ALL", "loc"
            ]
            .astype(str)
            .str.strip()
            .unique()
        )
        styler_sample = styler_sample.apply_index(
            lambda x: np.where(
                x.isin(warn_all_locs),
                f"background-color: {WARN_COLOR}",
                "",
            ),
            axis=1,
        ).apply(
            lambda df: highlight_cells_by_group_loc(
                df,
                warn_sample[warn_sample[SAMP_NAME_COL] != "ALL"],
                SAMP_NAME_COL,
                WARN_COLOR,
            ),
            axis=None,
        )

    if not error_sample.empty:
        error_all_locs = (
            error_sample.loc[
                error_sample[SAMP_NAME_COL] == "ALL", "loc"
            ]
            .astype(str)
            .str.strip()
            .unique()
        )
        styler_sample = styler_sample.apply_index(
            lambda x: np.where(
                x.isin(error_all_locs),
                f"background-color: {ERROR_COLOR}",
                "",
            ),
            axis=1,
        ).apply(
            lambda df: highlight_cells_by_group_loc(
                df,
                error_sample[error_sample[SAMP_NAME_COL] != "ALL"],
                SAMP_NAME_COL,
                ERROR_COLOR,
            ),
            axis=None,
        )

    with pd.ExcelWriter(outpath, engine="openpyxl") as writer:
        (
            warn_project
            if warn_project.empty
            else warn_project.style.map_index(
                lambda _: f"background-color: {WARN_COLOR}",
                axis="columns",
            )
        ).to_excel(
            writer,
            sheet_name="projectMetadata_warning",
            index=False,
        )

        (
            error_project
            if error_project.empty
            else error_project.style.map_index(
                lambda _: f"background-color: {ERROR_COLOR}",
                axis="columns",
            )
        ).to_excel(
            writer,
            sheet_name="projectMetadata_error",
            index=False,
        )

        styler_project.to_excel(
            writer,
            sheet_name="projectMetadata_revise",
            header=True,
            index=False,
        )

        (
            warn_sample
            if warn_sample.empty
            else warn_sample.style.map_index(
                lambda _: f"background-color: {WARN_COLOR}",
                axis="columns",
            )
        ).to_excel(
            writer,
            sheet_name="sampleMetadata_warning",
            index=False,
        )

        (
            error_sample
            if error_sample.empty
            else error_sample.style.map_index(
                lambda _: f"background-color: {ERROR_COLOR}",
                axis="columns",
            )
        ).to_excel(
            writer,
            sheet_name="sampleMetadata_error",
            index=False,
        )

        styler_sample.to_excel(
            writer,
            sheet_name="sampleMetadata_revise",
            header=True,
            index=False,
        )


def issue_table(
    result: dict[str, Any],
) -> pd.DataFrame:
    """Combine project/sample warning and error tables into one TSV-friendly table."""
    frames: list[pd.DataFrame] = []

    def add(
        df: pd.DataFrame,
        worksheet: str,
        severity: str,
        group_col: str,
    ) -> None:
        if df.empty:
            return
        temp = df.copy()
        temp.insert(0, "severity", severity)
        temp.insert(0, "worksheet", worksheet)
        temp = temp.rename(columns={group_col: "record"})
        frames.append(temp)

    add(
        result["warning_project"],
        "projectMetadata",
        "WARNING",
        TERM_NAME_COL,
    )
    add(
        result["error_project"],
        "projectMetadata",
        "ERROR",
        TERM_NAME_COL,
    )
    add(
        result["warning_sample"],
        "sampleMetadata",
        "WARNING",
        SAMP_NAME_COL,
    )
    add(
        result["error_sample"],
        "sampleMetadata",
        "ERROR",
        SAMP_NAME_COL,
    )

    if not frames:
        return pd.DataFrame(
            columns=[
                "worksheet",
                "severity",
                "record",
                "loc",
                "type",
                "msg",
                "input",
                "output",
            ]
        )

    combined = pd.concat(frames, ignore_index=True, sort=False)
    preferred = [
        "worksheet",
        "severity",
        "record",
        "loc",
        "type",
        "msg",
        "input",
        "output",
    ]
    for col in preferred:
        if col not in combined.columns:
            combined[col] = None
    return combined[preferred]


def make_summary(
    input_path: Path,
    checklist_path: Path,
    result: dict[str, Any],
    issues: pd.DataFrame,
    outputs: list[str],
) -> dict[str, Any]:
    """Create the machine-readable validation summary."""
    project_errors = len(result["error_project"])
    project_warnings = len(result["warning_project"])
    sample_errors = len(result["error_sample"])
    sample_warnings = len(result["warning_sample"])

    errors = project_errors + sample_errors
    warnings_count = project_warnings + sample_warnings

    status = "FAIL" if errors else ("WARN" if warnings_count else "PASS")

    return {
        "validator": "FAIRe-fier batch wrapper",
        "input_file": input_path.name,
        "checklist_file": checklist_path.name,
        "status": status,
        "errors": errors,
        "warnings": warnings_count,
        "projectMetadata": {
            "errors": project_errors,
            "warnings": project_warnings,
            "validated": bool(not result["output_project"].empty),
        },
        "sampleMetadata": {
            "errors": sample_errors,
            "warnings": sample_warnings,
            "validated": bool(not result["output_sample"].empty),
        },
        "message": result["message"],
        "outputs": outputs,
        "issue_rows": len(issues),
        "scope_note": (
            "This FAIRe-fier code validates projectMetadata and sampleMetadata. "
            "experimentRunMetadata, taxaRaw, taxaFinal and separate OTU/ASV result "
            "files require additional workflow validation."
        ),
    }


def run_batch(
    input_path: Path,
    checklist_path: Path,
    outdir: Path,
) -> dict[str, Any]:
    """Main programmatic entry point, usable by Nextflow or other Python code."""
    outdir.mkdir(parents=True, exist_ok=True)

    df_project_input, df_sample_input = read_worksheets(input_path)
    _, df_project_rules, df_sample_rules = load_checklist(checklist_path)

    result = validate_metadata(
        df_project_input,
        df_sample_input,
        df_project_rules,
        df_sample_rules,
    )

    issues = issue_table(result)

    issues_path = outdir / "validation_issues.tsv"
    issues.to_csv(issues_path, sep="\t", index=False)

    # Also create convenient separated issue files.
    result["warning_project"].to_csv(
        outdir / "projectMetadata_warnings.tsv",
        sep="\t",
        index=False,
    )
    result["error_project"].to_csv(
        outdir / "projectMetadata_errors.tsv",
        sep="\t",
        index=False,
    )
    result["warning_sample"].to_csv(
        outdir / "sampleMetadata_warnings.tsv",
        sep="\t",
        index=False,
    )
    result["error_sample"].to_csv(
        outdir / "sampleMetadata_errors.tsv",
        sep="\t",
        index=False,
    )

    outputs = [
        "validation_summary.json",
        "validation_issues.tsv",
        "projectMetadata_warnings.tsv",
        "projectMetadata_errors.tsv",
        "sampleMetadata_warnings.tsv",
        "sampleMetadata_errors.tsv",
    ]

    has_errors = (
        not result["error_project"].empty
        or not result["error_sample"].empty
    )
    has_warnings = (
        not result["warning_project"].empty
        or not result["warning_sample"].empty
    )

    # FAIRe-fier Shiny behaviour: clean workbook only where validated outputs exist.
    if (
        not has_errors
        and not result["output_project"].empty
        and not result["output_sample"].empty
    ):
        write_validated_workbook(
            outdir / "fairefier_metadata.xlsx",
            result,
        )
        outputs.append("fairefier_metadata.xlsx")

    # Produce a revision workbook whenever warnings or errors exist.
    if has_warnings or has_errors:
        write_revision_workbook(
            outdir / "fairefier_warn_error.xlsx",
            result,
        )
        outputs.append("fairefier_warn_error.xlsx")

    summary = make_summary(
        input_path,
        checklist_path,
        result,
        issues,
        outputs,
    )

    (outdir / "validation_summary.json").write_text(
        json.dumps(summary, indent=2, default=str),
        encoding="utf-8",
    )

    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run FAIRe-fier projectMetadata/sampleMetadata validation "
            "without the Shiny UI."
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Input .xlsx/.xls workbook containing FAIRe metadata sheets.",
    )
    parser.add_argument(
        "--checklist",
        required=True,
        type=Path,
        help="FAIRe checklist workbook containing the 'checklist' sheet.",
    )
    parser.add_argument(
        "--outdir",
        required=True,
        type=Path,
        help="Directory for validation outputs.",
    )
    parser.add_argument(
        "--fail-on-errors",
        action="store_true",
        help=(
            "Return exit code 2 when data validation status is FAIL. "
            "Default is exit 0 for a completed validator run."
        ),
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()

    try:
        summary = run_batch(
            args.input.resolve(),
            args.checklist.resolve(),
            args.outdir.resolve(),
        )
    except BatchInputError as exc:
        args.outdir.mkdir(parents=True, exist_ok=True)
        summary = {
            "validator": "FAIRe-fier batch wrapper",
            "input_file": args.input.name,
            "checklist_file": args.checklist.name,
            "status": "SYSTEM_ERROR",
            "errors": 0,
            "warnings": 0,
            "message": str(exc),
            "outputs": ["validation_summary.json"],
        }
        (args.outdir / "validation_summary.json").write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(summary, indent=2))
        return 1
    except Exception as exc:
        # Unexpected implementation/runtime error: preserve clear distinction
        # from ordinary metadata-validation failure.
        args.outdir.mkdir(parents=True, exist_ok=True)
        summary = {
            "validator": "FAIRe-fier batch wrapper",
            "input_file": args.input.name,
            "checklist_file": args.checklist.name,
            "status": "SYSTEM_ERROR",
            "errors": 0,
            "warnings": 0,
            "message": f"{type(exc).__name__}: {exc}",
            "outputs": ["validation_summary.json"],
        }
        (args.outdir / "validation_summary.json").write_text(
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
