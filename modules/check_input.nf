process CHECK_INPUT {
    tag "${workbook.simpleName}"
    publishDir "${params.outdir}/01_input", mode: 'copy'

    input:
    path workbook

    output:
    path workbook, emit: workbook
    path "input_manifest.tsv", emit: manifest

    script:
    """
    case "${workbook}" in
      *.xlsx) ;;
      *) echo "ERROR: Current integration test expects .xlsx" >&2; exit 2 ;;
    esac

    printf "file_name\tbytes\tsha256\n" > input_manifest.tsv
    printf "%s\t%s\t%s\n" \
      "${workbook}" \
      "\$(wc -c < "${workbook}")" \
      "\$(sha256sum "${workbook}" | cut -d' ' -f1)" \
      >> input_manifest.tsv
    """
}
