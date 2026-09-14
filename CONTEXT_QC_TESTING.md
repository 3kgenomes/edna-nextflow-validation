# Nextflow v4: FAIRe-fier + Context QC

The workflow now runs three complementary validation layers:

```text
CHECK_INPUT
    |
PROFILE_FAIRE
    |
    +----------------------+-------------------------+
    |                      |                         |
CHECK_STAGE        FAIRE_FIER_VALIDATE          CONTEXT_QC
structural         FAIRe checklist              project plausibility
lab-return         projectMetadata              coordinates
checks             sampleMetadata               unit normalization
    |                      |                         |
    +----------------------+-------------------------+
                           |
                     PACKAGE_RESULTS
```

## Important fix in FAIRe-fier batch wrapper

`fairefier_batch.py` now:
1. opens the workbook with `with pd.ExcelFile(...)` so the file handle is closed;
2. captures FAIRe `UserWarning` messages while ignoring unrelated runtime/resource warnings.

The spurious `unclosed file <_io.BufferedReader ...>` line should therefore no
longer appear as a metadata warning.

## Context-QC configuration

Edit:

```text
tools/context_qc/context_qc_config.json
```

The current development region is intentionally broad:

```text
latitude  -50 to -10
longitude 110 to 180
expected latitude hemisphere: south
expected longitude hemisphere: east
```

Change this per project when a more appropriate geographic envelope is known.

Measurement QC is conditional on sample collection device:
- `niskin bottle` / `OCD_1L_Water`: `samp_size` is treated as water volume and normalized to L.
- `Tow`: `samp_size` is treated as tow distance and normalized to km.

This matters because the supplied OcOm workbook legitimately uses both L and km
in `samp_size_unit`.

## Test 1: original synthetic lab-return fixture

```bash
rm -rf results_context_valid

nextflow run main.nf \
  --input data/OcOm_2518_MOCK_LAB_RETURN_VALID.xlsx \
  --stage lab_return \
  --outdir results_context_valid
```

Expected Context QC result:

```bash
cat results_context_valid/05_context_qc/context_qc_results/context_qc_summary.json
```

Expected:

```text
status: PASS
errors: 0
warnings: 0
```

Note: FAIRe-fier is still expected to report FAIL on this synthetic workbook
because it does not satisfy the complete FAIRe checklist. Structural/contextual
PASS and FAIRe FAIL are independent results.

## Test 2: targeted context-QC errors

```bash
rm -rf results_context_errors

nextflow run main.nf \
  --input data/OcOm_2518_MOCK_CONTEXT_QC_ERRORS.xlsx \
  --stage lab_return \
  --outdir results_context_errors
```

Expected Context QC result:

```text
status: FAIL
errors: 6
warnings: 1
```

The targeted records contain:
- +35.12345 latitude: southern-hemisphere + bounding-box errors;
- -135 latitude: globally invalid latitude;
- longitude 75: outside configured project region;
- 12 mL water sample: normalized to 0.012 L and flagged as implausibly low;
- sample size with missing unit;
- sample size with unsupported `gallon` unit.

Inspect:

```bash
cat results_context_errors/05_context_qc/context_qc_results/context_qc_summary.json

column -t -s $'\t' \
  results_context_errors/05_context_qc/context_qc_results/context_qc_issues.tsv | head -20
```

Normalization output:

```bash
head \
  results_context_errors/05_context_qc/context_qc_results/context_qc_normalized.tsv
```

## Expected processes

```text
CHECK_INPUT
PROFILE_FAIRE
CHECK_STAGE
FAIRE_FIER_VALIDATE
CONTEXT_QC
PACKAGE_RESULTS
```

## Result directories

```text
results_*/
├── 01_input/
├── 02_profile/
├── 03_stage_check/
├── 04_fairefier/
├── 05_context_qc/
├── 06_package/
├── trace.tsv
├── timeline.html
├── nextflow_report.html
└── workflow_dag.html
```
