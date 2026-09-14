nextflow.enable.dsl=2

params.input  = null
params.stage  = 'pre_lab'
params.outdir = 'results'
params.fairefier_checklist = "${projectDir}/tools/fairefier/FAIRe_checklist_v1.0.xlsx"
params.context_qc_config   = "${projectDir}/tools/context_qc/context_qc_config.json"

if( !params.input ) {
    error "Missing --input <FAIRe workbook>"
}
if( !['pre_lab','lab_return'].contains(params.stage) ) {
    error "--stage must be pre_lab or lab_return"
}

include { CHECK_INPUT }         from './modules/check_input'
include { PROFILE_FAIRE }       from './modules/profile_faire'
include { CHECK_STAGE }         from './modules/check_stage'
include { FAIRE_FIER_VALIDATE } from './modules/fairefier_validate'
include { CONTEXT_QC }          from './modules/context_qc'
include { MERGE_VALIDATION }    from './modules/merge_validation'
include { PACKAGE_RESULTS }     from './modules/package_results'

workflow {
    input_ch = Channel.fromPath(params.input, checkIfExists: true)

    CHECK_INPUT(input_ch)

    PROFILE_FAIRE(
        CHECK_INPUT.out.workbook
    )

    CHECK_STAGE(
        PROFILE_FAIRE.out.profile
    )

    FAIRE_FIER_VALIDATE(
        CHECK_INPUT.out.workbook
    )

    CONTEXT_QC(
        CHECK_INPUT.out.workbook
    )

    MERGE_VALIDATION(
        CHECK_STAGE.out.summary,
        FAIRE_FIER_VALIDATE.out.results,
        CONTEXT_QC.out.results
    )

    PACKAGE_RESULTS(
        CHECK_INPUT.out.workbook,
        PROFILE_FAIRE.out.profile,
        CHECK_STAGE.out.report,
        CHECK_STAGE.out.summary,
        FAIRE_FIER_VALIDATE.out.results,
        CONTEXT_QC.out.results,
        MERGE_VALIDATION.out.results
    )
}
