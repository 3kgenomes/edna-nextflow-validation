process PACKAGE_RESULTS {
    tag "${params.stage}"
    publishDir "${params.outdir}/07_package", mode: 'copy'

    input:
    path workbook
    path profile
    path stage_report
    path stage_summary
    path fairefier_results
    path context_qc_results
    path readiness_results

    output:
    path "edna_engine_prototype_bundle", emit: bundle

    script:
    """
    mkdir -p edna_engine_prototype_bundle

    cp "${workbook}" edna_engine_prototype_bundle/
    cp "${profile}" edna_engine_prototype_bundle/
    cp "${stage_report}" edna_engine_prototype_bundle/
    cp "${stage_summary}" edna_engine_prototype_bundle/

    cp -r "${fairefier_results}" edna_engine_prototype_bundle/
    cp -r "${context_qc_results}" edna_engine_prototype_bundle/
    cp -r "${readiness_results}" edna_engine_prototype_bundle/
    """
}
