# Prototype handoff for Sciansa integration

## What this prototype does

The Nextflow engine accepts one FAIRe-style Excel workbook and runs:

1. workbook/input checks;
2. workbook profiling;
3. structural/lab-return validation;
4. FAIRe-fier validation of `projectMetadata` and `sampleMetadata`;
5. project-specific Context QC for coordinates and measurement units;
6. merged dataset-readiness assessment;
7. packaging of all outputs.

## Recommended Sciansa contract

Sciansa or FastAPI only needs to provide:

```text
input workbook path
output directory
stage = pre_lab | lab_return
```

Example:

```bash
nextflow run main.nf \
  --input /work/uploads/run-001/metadata.xlsx \
  --stage lab_return \
  --outdir /work/results/run-001
```

The primary machine-readable response is:

```text
/work/results/run-001/06_readiness/readiness_results/dataset_readiness.json
```

## Suggested UI interpretation

- `READY`: dataset can proceed to the next publication/conversion step.
- `REVIEW_REQUIRED`: display warnings for human approval/correction.
- `NOT_READY`: display blocking validation layers and their detailed outputs.
- `SYSTEM_ERROR`: treat as workflow/integration failure.

The JSON also includes:
- total errors/warnings;
- status/error/warning counts for each validation layer;
- blocking actions;
- review actions;
- `ready_for_publication` boolean;
- `next_action`.

## Important distinction

A successful Nextflow run can legitimately produce:

```text
pipeline_status = SUCCESS
dataset_readiness = NOT_READY
```

This means the software executed correctly but the metadata requires correction.

That distinction should be preserved in Sciansa rather than converting every
validation failure into a job failure.

## Current prototype boundary

Included:
- structural workbook checks;
- FAIRe-fier project/sample validation;
- coordinate/hemisphere/bounding-box QC;
- conditional measurement-unit normalization and plausibility checks;
- merged readiness result.

Not yet included:
- automatic correction/approval;
- ocean-vs-land geospatial check;
- separate OTU/ASV result-file validation;
- edna2obis / FAIRe2MDT publication conversion;
- repository submission.
