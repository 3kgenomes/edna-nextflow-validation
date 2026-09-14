process MERGE_VALIDATION {
    tag "${params.stage}"
    publishDir "${params.outdir}/06_readiness", mode: 'copy'

    input:
    path structural_summary
    path fairefier_results
    path context_qc_results

    output:
    path "readiness_results", emit: results

    script:
    """
    mkdir -p readiness_results

    python ${projectDir}/bin/merge_validation.py \
      --structural "${structural_summary}" \
      --faire "${fairefier_results}/validation_summary.json" \
      --context "${context_qc_results}/context_qc_summary.json" \
      --outdir readiness_results
    """
}
