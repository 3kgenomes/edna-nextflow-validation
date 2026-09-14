# What the two OcOm files show

## Before the lab
The populated `OcOm_2518` workbook contains:
- project metadata;
- field/sample metadata for many samples;
- PCR/library/bioinformatics method descriptions in `projectMetadata`.

The following result areas are still blank:
- `experimentRunMetadata` rows;
- `taxaRaw`;
- `taxaFinal`.

## Expected lab/bioinformatics return
Based on the workbook structure, the lab-return stage is expected to add:
- sample/assay/run linkage;
- FASTQ filenames/checksums and sequencing-run metadata;
- `input_read_count`;
- `output_read_count`;
- `output_otu_num`;
- `otu_num_tax_assigned`;
- raw taxonomic assignments (`taxaRaw`);
- curated/final taxonomic assignments (`taxaFinal`);
- separate `otuRaw` / `otuFinal` files referenced in the README.

The exact layout of the separate OTU files cannot be derived from the two supplied workbooks and should be confirmed from a real lab-return example.
