process PROFILE_FAIRE {
    tag "${workbook.simpleName}"
    publishDir "${params.outdir}/02_profile", mode: 'copy'

    input:
    path workbook

    output:
    path "faire_workbook_profile.json", emit: profile

    script:
    """
    PYTHONPATH=${projectDir}/bin python3 ${projectDir}/bin/profile_faire.py \
      --input "${workbook}" \
      --output faire_workbook_profile.json
    """
}
