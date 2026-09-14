process FAIRE_FIER_VALIDATE {
    tag "${workbook.simpleName}"
    publishDir "${params.outdir}/04_fairefier", mode: 'copy'

    input:
    path workbook

    output:
    path "fairefier_results", emit: results

    script:
    """
    python ${projectDir}/tools/fairefier/fairefier_batch.py \
      --input "${workbook}" \
      --checklist "${params.fairefier_checklist}" \
      --outdir fairefier_results
    """
}
