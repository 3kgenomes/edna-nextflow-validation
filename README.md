# eDNA Nextflow starter v2

This version is aligned to the **actual OcOm FAIRe-style workbooks** supplied for development.

It understands that:

- `projectMetadata` is a vertical term/value table;
- `sampleMetadata` has requirement levels in row 1, sections in row 2, field names in row 3, and samples from row 4;
- `experimentRunMetadata` contains run-level sequencing fields plus the four bioinformatics count fields:
  `input_read_count`, `output_read_count`, `output_otu_num`, `otu_num_tax_assigned`;
- `taxaRaw` and `taxaFinal` contain taxonomic output records.

## Two workflow states

### Pre-lab
Use when the workbook is being sent to the lab:

```bash
nextflow run main.nf \
  --input /path/to/OcOm_2518_metadata.xlsx \
  --stage pre_lab \
  --outdir results_pre_lab
```

The workflow checks workbook structure, project ID, and that sample rows exist.
It does **not** require lab-return fields.

### Lab return
Use after sequencing/bioinformatics results have been added:

```bash
nextflow run main.nf \
  --input data/OcOm_2518_MOCK_LAB_RETURN_DO_NOT_PUBLISH.xlsx \
  --stage lab_return \
  --outdir results_lab_return
```

The structural check additionally looks for:
- experiment/run rows;
- values in the four run-level bioinformatics metrics;
- taxaRaw records;
- taxaFinal records.

## Important

These checks are deliberately lightweight. They test the integration contract and lifecycle stage.
They are **not a replacement for FAIRe-fier**.

The next production module should be `FAIRE_FIER_VALIDATE`, replacing the structural check with the real FAIRe-fier validation logic.

## Unknown piece

The attached workbooks refer to separate `otuRaw` and `otuFinal` files for each assay/run, but no example of those returned files was supplied. Their exact schema should therefore be confirmed with the lab before building that adapter.
