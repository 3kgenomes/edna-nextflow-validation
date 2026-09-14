#!/usr/bin/env python3
import argparse, json
from pathlib import Path
from xlsx_reader import read_xlsx

EXPECTED_SHEETS = [
    "README", "projectMetadata", "sampleMetadata",
    "experimentRunMetadata", "taxaRaw", "taxaFinal"
]

def nonempty(x):
    return str(x).strip() != ""

def profile_project(rows):
    out = {"project_id": None, "assays": [], "bioinformatics_terms_populated": 0}
    if not rows:
        return out
    for r in rows[1:]:
        r = r + [""] * (12 - len(r))
        section = str(r[1]).strip() if len(r) > 1 else ""
        term = str(r[2]).strip() if len(r) > 2 else ""
        if term == "project_id" and len(r) > 3:
            out["project_id"] = r[3] or None
        if term == "assay_name":
            out["assays"] = [x for x in r[4:] if nonempty(x)]
        if section == "Bioinformatics" and len(r) > 3 and nonempty(r[3]):
            out["bioinformatics_terms_populated"] += 1
    return out

def profile_tabular(rows, header_row_index=2, id_field=None):
    if len(rows) <= header_row_index:
        return {"rows": 0, "fields": 0, "headers": []}
    headers = [str(x).strip() for x in rows[header_row_index]]
    count = 0
    id_idx = headers.index(id_field) if id_field in headers else None
    for r in rows[header_row_index+1:]:
        padded = r + [""] * (len(headers) - len(r))
        if id_idx is not None:
            if nonempty(padded[id_idx]):
                count += 1
        elif any(nonempty(x) for x in padded):
            count += 1
    return {"rows": count, "fields": len(headers), "headers": headers}

def experiment_bioinfo(rows):
    if len(rows) < 3:
        return {"rows": 0, "bioinformatics_fields": {}, "rows_complete": 0}
    headers = [str(x).strip() for x in rows[2]]
    wanted = ["input_read_count", "output_read_count", "output_otu_num", "otu_num_tax_assigned"]
    idx = {h: headers.index(h) for h in wanted if h in headers}
    data = []
    samp_idx = headers.index("samp_name") if "samp_name" in headers else None
    for r in rows[3:]:
        padded = r + [""] * (len(headers) - len(r))
        if samp_idx is not None and nonempty(padded[samp_idx]):
            data.append(padded)
    counts = {h: sum(1 for r in data if nonempty(r[i])) for h, i in idx.items()}
    rows_complete = sum(1 for r in data if idx and all(nonempty(r[i]) for i in idx.values()))
    return {"rows": len(data), "bioinformatics_fields": counts, "rows_complete": rows_complete}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", default="faire_workbook_profile.json")
    args = ap.parse_args()

    sheets = read_xlsx(args.input)
    project = profile_project(sheets.get("projectMetadata", []))
    sample = profile_tabular(sheets.get("sampleMetadata", []), 2, "samp_name")
    exp = experiment_bioinfo(sheets.get("experimentRunMetadata", []))
    taxa_raw = profile_tabular(sheets.get("taxaRaw", []), 2, "seq_id")
    taxa_final = profile_tabular(sheets.get("taxaFinal", []), 2, "seq_id")

    result = {
        "file_name": Path(args.input).name,
        "sheets_present": list(sheets.keys()),
        "missing_expected_sheets": [s for s in EXPECTED_SHEETS if s not in sheets],
        "project_id": project["project_id"],
        "assays": project["assays"],
        "project_bioinformatics_terms_populated": project["bioinformatics_terms_populated"],
        "sample_metadata": {"sample_rows": sample["rows"], "field_count": sample["fields"]},
        "experiment_run_metadata": exp,
        "taxa_raw_rows": taxa_raw["rows"],
        "taxa_final_rows": taxa_final["rows"]
    }

    Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
