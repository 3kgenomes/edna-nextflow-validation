# Nextflow v5 prototype: merged dataset readiness

This version adds a single canonical readiness result after the three validation
layers complete.

```text
CHECK_INPUT
    |
PROFILE_FAIRE
    |
    +----------------------+-------------------------+
    |                      |                         |
CHECK_STAGE        FAIRE_FIER_VALIDATE          CONTEXT_QC
    |                      |                         |
    +----------------------+-------------------------+
                           |
                   MERGE_VALIDATION
                           |
                    PACKAGE_RESULTS
```

## Canonical result for Sciansa

The main file for Sciansa/FastAPI to consume is:

```text
06_readiness/readiness_results/dataset_readiness.json
```

The prototype readiness policy is deliberately conservative:

- `READY` = all three checks PASS
- `REVIEW_REQUIRED` = no FAIL, but at least one WARN
- `NOT_READY` = at least one FAIL
- `SYSTEM_ERROR` = a validation summary could not be interpreted

`ready_for_publication` is true only for `READY`.

A validation FAIL is a DATA status, not a Nextflow process failure.

## Test with the current structurally/contextually clean fixture

```bash
rm -rf results_readiness

nextflow run main.nf \
  --input data/OcOm_2518_MOCK_LAB_RETURN_VALID.xlsx \
  --stage lab_return \
  --outdir results_readiness
```

Expected processes:

```text
CHECK_INPUT
PROFILE_FAIRE
CHECK_STAGE
FAIRE_FIER_VALIDATE
CONTEXT_QC
MERGE_VALIDATION
PACKAGE_RESULTS
```

Inspect the single readiness result:

```bash
cat results_readiness/06_readiness/readiness_results/dataset_readiness.json
```

Because the current synthetic workbook still fails the real FAIRe checklist,
the expected readiness is `NOT_READY` even though structural QC and Context QC
pass.

## Targeted contextual-error fixture

```bash
rm -rf results_readiness_errors

nextflow run main.nf \
  --input data/OcOm_2518_MOCK_CONTEXT_QC_ERRORS.xlsx \
  --stage lab_return \
  --outdir results_readiness_errors
```

Then inspect:

```bash
cat results_readiness_errors/06_readiness/readiness_results/dataset_readiness.json
```

## Outputs

```text
results_*/
├── 01_input/
├── 02_profile/
├── 03_stage_check/
├── 04_fairefier/
├── 05_context_qc/
├── 06_readiness/
│   └── readiness_results/
│       ├── dataset_readiness.json   <- canonical API/Sciansa result
│       ├── dataset_readiness.tsv
│       └── dataset_readiness.md
├── 07_package/
│   └── edna_engine_prototype_bundle/
├── trace.tsv
├── timeline.html
├── nextflow_report.html
└── workflow_dag.html
```
