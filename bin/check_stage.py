#!/usr/bin/env python3
import argparse, json
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--profile", required=True)
ap.add_argument("--stage", choices=["pre_lab", "lab_return"], required=True)
ap.add_argument("--summary", default="stage_summary.json")
ap.add_argument("--report", default="stage_report.tsv")
args = ap.parse_args()

p = json.loads(Path(args.profile).read_text(encoding="utf-8"))
issues = []

def add(sev, check, message):
    issues.append((sev, check, message))

if p["missing_expected_sheets"]:
    add("ERROR", "workbook_structure", "Missing expected sheet(s): " + ", ".join(p["missing_expected_sheets"]))

if not p.get("project_id"):
    add("ERROR", "project_id", "No project_id was found in projectMetadata")

if p["sample_metadata"]["sample_rows"] == 0:
    add("ERROR", "sampleMetadata", "No populated sample rows were found")

if args.stage == "lab_return":
    exp = p["experiment_run_metadata"]
    if exp["rows"] == 0:
        add("ERROR", "experimentRunMetadata", "No populated experiment/run rows were found")
    else:
        expected = ["input_read_count", "output_read_count", "output_otu_num", "otu_num_tax_assigned"]
        for f in expected:
            n = exp["bioinformatics_fields"].get(f, 0)
            if n == 0:
                add("WARNING", f, f"No values were found for {f}")
        if exp["rows_complete"] == 0:
            add("WARNING", "bioinformatics_counts", "No experiment rows contain all four mock-tested bioinformatics count fields")

    if p["taxa_raw_rows"] == 0:
        add("WARNING", "taxaRaw", "No taxaRaw records were found")
    if p["taxa_final_rows"] == 0:
        add("WARNING", "taxaFinal", "No taxaFinal records were found")

status = "PASS"
if any(x[0] == "ERROR" for x in issues):
    status = "FAIL"
elif issues:
    status = "WARN"

summary = {
    "stage": args.stage,
    "status": status,
    "errors": sum(x[0] == "ERROR" for x in issues),
    "warnings": sum(x[0] == "WARNING" for x in issues),
    "note": "Structural integration check only. This does NOT replace FAIRe-fier validation."
}
Path(args.summary).write_text(json.dumps(summary, indent=2), encoding="utf-8")

with open(args.report, "w", encoding="utf-8") as f:
    f.write("severity\tcheck\tmessage\n")
    for sev, check, msg in issues:
        f.write(f"{sev}\t{check}\t{msg}\n")

print(json.dumps(summary, indent=2))
