# Quick test guide

Run these from the project root.

## 1. Valid synthetic lab return

```bash
nextflow run main.nf \
  --input data/OcOm_2518_MOCK_LAB_RETURN_VALID.xlsx \
  --stage lab_return \
  --outdir results_valid
```

Expected structural integration result:

- `stage = lab_return`
- `status = PASS`
- `errors = 0`
- `warnings = 0`

## 2. Synthetic lab return with deliberate errors

```bash
nextflow run main.nf \
  --input data/OcOm_2518_MOCK_LAB_RETURN_WITH_ERRORS.xlsx \
  --stage lab_return \
  --outdir results_errors
```

Expected structural integration result:

- `status = FAIL`
- missing `project_id` -> ERROR
- no `output_read_count` values -> WARNING
- no `taxaFinal` records -> WARNING

The error fixture was created specifically to exercise the current starter workflow.
These are structural tests only; they do not replace FAIRe-fier.

## Where to look after each run

```text
results_*/
├── 01_input/
├── 02_profile/
│   └── faire_workbook_profile.json
├── 03_stage_check/
│   ├── stage_report.tsv
│   └── stage_summary.json
├── 04_package/
│   └── edna_engine_test_bundle/
├── trace.tsv
├── timeline.html
├── nextflow_report.html
└── workflow_dag.html
```

Start by comparing `stage_summary.json` and `stage_report.tsv` between the two runs.
