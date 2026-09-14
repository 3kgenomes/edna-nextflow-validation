# Modular eDNA Metadata Validation Workflow

A prototype Nextflow workflow for validating environmental DNA (eDNA) metadata before downstream publication or repository conversion.

The workflow combines three complementary validation layers:

1. **Structural / lab-return QC** — checks whether expected workbook content is present for the selected workflow stage.
2. **FAIRe-fier validation** — runs the FAIRe-fier rules against `projectMetadata` and `sampleMetadata`.
3. **Contextual QC** — performs project-specific plausibility checks such as coordinate range/hemisphere validation and measurement-unit normalization.

The results are merged into a single machine-readable **dataset readiness** result that can be consumed by Nextflow users, APIs, Sciansa, or a future web interface.

> **Prototype status:** This repository is an early working prototype intended for testing and integration. It does not yet perform repository submission or final publication.

---

## Workflow

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

### Validation layers

**CHECK_STAGE**

Performs lightweight structural checks appropriate to the selected workflow stage. For a `lab_return` workbook, the current prototype checks items such as:

- `project_id`
- experiment/run metadata
- bioinformatics count fields
- `taxaRaw`
- `taxaFinal`

This is a structural workflow check and does not replace FAIRe validation.

**FAIRE_FIER_VALIDATE**

Runs the FAIRe-fier validation logic outside the Shiny interface.

Current scope:

```text
projectMetadata
sampleMetadata
```

The validator reports FAIRe checklist errors and warnings and can create the familiar FAIRe-fier revision workbook.

**CONTEXT_QC**

Performs configurable plausibility and normalization checks that are outside the scope of schema validation.

Current checks include:

- latitude/longitude numeric validation
- global coordinate ranges
- expected hemisphere
- configurable project bounding box
- allowed measurement units
- unit normalization
- implausible measurement warnings

The contextual rules are configured in:

```text
tools/context_qc/context_qc_config.json
```

For example, the current development configuration checks a broad southern Australian marine region and applies different `samp_size` rules depending on the collection method:

```text
Niskin / water sampling -> volume, normalized to L
Tow sampling            -> distance, normalized to km
```

---

# Requirements

The prototype has been tested with:

```text
Nextflow 24.04.2
Python 3
```

Python packages used by the included tools include:

```text
pandas
numpy
openpyxl
pydantic
```

The included FAIRe-fier code follows the dependencies in its original `requirements.txt`.

If Nextflow cannot access `www.nextflow.io`, you may see an update-check message such as:

```text
curl: (7) Failed to connect to www.nextflow.io ...
```

This does not prevent a locally installed Nextflow version from running the workflow.

---

# Quick start

Clone the repository and move into the project directory:

```bash
git clone <REPOSITORY_URL>
cd <REPOSITORY_NAME>
```

Check your Nextflow installation:

```bash
nextflow -version
```

Run the workflow with the included example workbook:

```bash
nextflow run main.nf \
  --input data/OcOm_2518_MOCK_LAB_RETURN_VALID.xlsx \
  --stage lab_return \
  --outdir results_readiness
```

A successful workflow execution should show seven processes:

```text
CHECK_INPUT
PROFILE_FAIRE
CHECK_STAGE
FAIRE_FIER_VALIDATE
CONTEXT_QC
MERGE_VALIDATION
PACKAGE_RESULTS
```

---

# Main output

The main result for users and external applications is:

```text
results_readiness/
└── 06_readiness/
    └── readiness_results/
        └── dataset_readiness.json
```

View it with:

```bash
cat results_readiness/06_readiness/readiness_results/dataset_readiness.json
```

Example:

```json
{
  "pipeline_status": "SUCCESS",
  "dataset_readiness": "NOT_READY",
  "ready_for_publication": false,
  "review_required": true,
  "checks": {
    "structural_qc": {
      "status": "PASS",
      "errors": 0,
      "warnings": 0
    },
    "faire_qc": {
      "status": "FAIL",
      "errors": 971,
      "warnings": 41
    },
    "context_qc": {
      "status": "PASS",
      "errors": 0,
      "warnings": 0
    }
  }
}
```

A successful Nextflow process does **not** mean that the dataset passed validation.

For example:

```text
pipeline_status   = SUCCESS
dataset_readiness = NOT_READY
```

means that the workflow executed correctly and identified metadata problems that require correction.

---

# Dataset readiness states

The merged readiness result currently uses four states:

| Status | Meaning |
|---|---|
| `READY` | All validation layers passed. |
| `REVIEW_REQUIRED` | No validation layer failed, but one or more warnings require review. |
| `NOT_READY` | At least one validation layer failed. |
| `SYSTEM_ERROR` | One or more validation results could not be interpreted or the merge step failed. |

`ready_for_publication` is only `true` when the overall state is `READY`.

The current policy intentionally requires warnings to be reviewed before a dataset is marked publication-ready.

---

# Test datasets

The repository includes example workbooks for testing different parts of the workflow.

## 1. Structurally/contextually valid mock lab-return workbook

```text
data/OcOm_2518_MOCK_LAB_RETURN_VALID.xlsx
```

Run:

```bash
nextflow run main.nf \
  --input data/OcOm_2518_MOCK_LAB_RETURN_VALID.xlsx \
  --stage lab_return \
  --outdir results_readiness
```

Expected behavior:

```text
Structural QC : PASS
Context QC    : PASS
FAIRe QC      : currently FAILS against the full FAIRe checklist
Overall       : NOT_READY
```

This is expected. The workbook was originally created for structural workflow testing rather than as a fully FAIRe-compliant reference dataset.

## 2. Mock lab-return workbook with structural errors

```text
data/OcOm_2518_MOCK_LAB_RETURN_WITH_ERRORS.xlsx
```

Run:

```bash
nextflow run main.nf \
  --input data/OcOm_2518_MOCK_LAB_RETURN_WITH_ERRORS.xlsx \
  --stage lab_return \
  --outdir results_readiness_lab_errors
```

This fixture deliberately includes problems such as:

```text
missing project_id
missing output_read_count
incomplete bioinformatics count information
missing taxaFinal records
```

Inspect the structural result:

```bash
cat results_readiness_lab_errors/03_stage_check/stage_summary.json
cat results_readiness_lab_errors/03_stage_check/stage_report.tsv
```

Inspect the merged readiness result:

```bash
cat results_readiness_lab_errors/06_readiness/readiness_results/dataset_readiness.json
```

## 3. Mock contextual-QC errors

```text
data/OcOm_2518_MOCK_CONTEXT_QC_ERRORS.xlsx
```

Run:

```bash
nextflow run main.nf \
  --input data/OcOm_2518_MOCK_CONTEXT_QC_ERRORS.xlsx \
  --stage lab_return \
  --outdir results_context_errors
```

The fixture contains targeted contextual problems such as:

```text
positive latitude where a southern latitude is expected
globally invalid latitude
longitude outside the configured project region
implausible water-volume unit/value combination
missing measurement unit
unsupported measurement unit
```

Inspect the results:

```bash
cat results_context_errors/05_context_qc/context_qc_results/context_qc_summary.json

column -t -s $'\t' \
  results_context_errors/05_context_qc/context_qc_results/context_qc_issues.tsv
```

---

# Output structure

A typical run produces:

```text
results_readiness/
├── 01_input/
├── 02_profile/
├── 03_stage_check/
├── 04_fairefier/
├── 05_context_qc/
├── 06_readiness/
│   └── readiness_results/
│       ├── dataset_readiness.json
│       ├── dataset_readiness.tsv
│       └── dataset_readiness.md
├── 07_package/
│   └── edna_engine_prototype_bundle/
├── trace.tsv
├── timeline.html
├── nextflow_report.html
└── workflow_dag.html
```

The packaged prototype output contains the input workbook and outputs from all validation layers.

---

# Important result files

Structural validation:

```text
03_stage_check/stage_summary.json
03_stage_check/stage_report.tsv
```

FAIRe-fier validation:

```text
04_fairefier/fairefier_results/validation_summary.json
04_fairefier/fairefier_results/validation_issues.tsv
04_fairefier/fairefier_results/fairefier_warn_error.xlsx
```

Contextual QC:

```text
05_context_qc/context_qc_results/context_qc_summary.json
05_context_qc/context_qc_results/context_qc_issues.tsv
05_context_qc/context_qc_results/context_qc_normalized.tsv
```

Combined dataset readiness:

```text
06_readiness/readiness_results/dataset_readiness.json
06_readiness/readiness_results/dataset_readiness.tsv
06_readiness/readiness_results/dataset_readiness.md
```

---

# Running your own workbook

Use:

```bash
nextflow run main.nf \
  --input /path/to/metadata.xlsx \
  --stage lab_return \
  --outdir /path/to/results
```

Currently supported workflow stages are:

```text
pre_lab
lab_return
```

Use a separate output directory for each test run to make comparisons easier.

Example:

```bash
nextflow run main.nf \
  --input my_metadata.xlsx \
  --stage lab_return \
  --outdir results_my_dataset
```

---

# Configuring contextual QC

Edit:

```text
tools/context_qc/context_qc_config.json
```

The configuration controls project-specific rules such as:

```text
expected latitude/longitude range
expected hemisphere
allowed units
unit aliases
canonical units
plausible measurement ranges
sampling-method-specific interpretation of fields
```

The default geographic bounds are development settings and should be replaced with project-appropriate values where possible.

The Context QC module does not silently correct ambiguous values. It reports errors/warnings and writes normalized values separately for review.

---

# Sciansa / API integration

The intended interface for external applications is deliberately small.

Run Nextflow:

```bash
nextflow run main.nf \
  --input /work/uploads/run-001/metadata.xlsx \
  --stage lab_return \
  --outdir /work/results/run-001
```

Then read:

```text
/work/results/run-001/06_readiness/readiness_results/dataset_readiness.json
```

The JSON includes:

```text
pipeline_status
dataset_readiness
ready_for_publication
review_required
total errors/warnings
individual validation-layer status
blocking checks
review checks
next_action
```

External applications should preserve the distinction between workflow execution and data validation.

---

# Current scope

The prototype currently includes:

```text
FAIRe-style workbook input
structural/lab-return checks
FAIRe-fier validation
coordinate plausibility QC
project bounding-box checks
measurement-unit normalization
measurement plausibility checks
merged dataset-readiness result
Nextflow provenance/reporting
```

Not yet implemented:

```text
automatic metadata correction
human approval interface
land/ocean geospatial validation
separate OTU/ASV file validation
edna2obis conversion
FAIRe2MDT conversion
GBIF/OBIS repository submission
production authentication
web portal
```

These are potential future modules rather than requirements for the current validation prototype.

---

# Design principle

The workflow is intentionally modular.

The aim is not to replace existing eDNA community tools with a single monolithic application. Instead, Nextflow acts as an orchestration layer that can connect existing validation, conversion, bioinformatics, and publication tools while preserving reproducibility and provenance.

Future modules can be added without changing the overall validation contract.

---

# Prototype disclaimer

This software is currently a research/development prototype.

The supplied example workbooks contain synthetic or modified records for workflow testing and should **not** be treated as publication-ready datasets.

Always review validation findings before using outputs for scientific publication or submission to external repositories.


## Acknowledgements

This prototype integrates validation functionality from **FAIRe-fier**, developed at CSIRO by Suk Yee Yong. FAIRe-fier is used for validation of FAIRe `projectMetadata` and `sampleMetadata`.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for citation and licensing information.
