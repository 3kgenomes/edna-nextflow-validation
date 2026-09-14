process CHECK_STAGE {
    tag "${params.stage}"
    publishDir "${params.outdir}/03_stage_check", mode: 'copy'

    input:
    path profile

    output:
    path "stage_report.tsv", emit: report
    path "stage_summary.json", emit: summary

    script:
    """
    python3 ${projectDir}/bin/check_stage.py \
      --profile "${profile}" \
      --stage "${params.stage}" \
      --report stage_report.tsv \
      --summary stage_summary.json
    """
}
