process CONTEXT_QC {
    tag "${workbook.simpleName}"
    publishDir "${params.outdir}/05_context_qc", mode: 'copy'

    input:
    path workbook

    output:
    path "context_qc_results", emit: results

    script:
    """
    python ${projectDir}/tools/context_qc/context_qc.py \
      --input "${workbook}" \
      --config "${params.context_qc_config}" \
      --outdir context_qc_results
    """
}
