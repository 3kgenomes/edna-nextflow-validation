# FAIRe-fier + Nextflow integration test

This version keeps two validation layers separate:

```text
CHECK_INPUT
    |
PROFILE_FAIRE
    |
    +-----------------------------+
    |                             |
CHECK_STAGE                FAIRE_FIER_VALIDATE
(structural/lifecycle)     (real FAIRe checklist)
    |                             |
    +-------------+---------------+
                  |
            PACKAGE_RESULTS
```

`CHECK_STAGE` currently checks the lab-return structure, including the
`experimentRunMetadata`, `taxaRaw`, and `taxaFinal` areas.

`FAIRE_FIER_VALIDATE` runs the supplied FAIRe-fier validation logic against
`projectMetadata` and `sampleMetadata`.

A FAIRe validation result of `FAIL` does NOT terminate Nextflow. The Python
wrapper exits normally after a completed validator run, and the data-validation
status is written to `validation_summary.json`.

## Test

From the project root:

```bash
nextflow run main.nf \
  --input data/OcOm_2518_MOCK_LAB_RETURN_VALID.xlsx \
  --stage lab_return \
  --outdir results_faire
```

Expected Nextflow process completion:

```text
CHECK_INPUT          completed
PROFILE_FAIRE        completed
CHECK_STAGE          completed
FAIRE_FIER_VALIDATE completed
PACKAGE_RESULTS      completed
```

The structural fixture should still pass the lightweight structural check:

```bash
cat results_faire/03_stage_check/stage_summary.json
```

The real FAIRe-fier result is here:

```bash
cat results_faire/04_fairefier/fairefier_results/validation_summary.json
```

With the current synthetic OcOm fixture, FAIRe-fier is expected to report
`FAIL`, because the fixture was designed to satisfy the earlier structural
integration test rather than the complete FAIRe checklist.

Inspect the most common FAIRe issues with:

```bash
python - <<'PY'
import pandas as pd

f = "results_faire/04_fairefier/fairefier_results/validation_issues.tsv"
df = pd.read_csv(f, sep="\t")

print("\nIssue counts by worksheet/severity:")
print(df.groupby(["worksheet", "severity"]).size())

print("\nMost frequent terms/messages:")
print(
    df.groupby(["worksheet", "loc", "msg"])
      .size()
      .sort_values(ascending=False)
      .head(20)
)
PY
```

## Output structure

```text
results_faire/
├── 01_input/
├── 02_profile/
├── 03_stage_check/
├── 04_fairefier/
│   └── fairefier_results/
│       ├── validation_summary.json
│       ├── validation_issues.tsv
│       ├── projectMetadata_warnings.tsv
│       ├── projectMetadata_errors.tsv
│       ├── sampleMetadata_warnings.tsv
│       ├── sampleMetadata_errors.tsv
│       └── fairefier_warn_error.xlsx   # when warnings/errors exist
├── 05_package/
│   └── edna_engine_test_bundle/
├── trace.tsv
├── timeline.html
├── nextflow_report.html
└── workflow_dag.html
```

## Current development boundary

The integrated FAIRe-fier code validates only:
- projectMetadata
- sampleMetadata

The existing structural/lab-return module remains responsible for:
- experimentRunMetadata
- taxaRaw
- taxaFinal

Separate OTU/ASV result-file validation can be added once a real lab-return
example of those files is available.
