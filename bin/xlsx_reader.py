#!/usr/bin/env python3
import re, zipfile
from xml.etree import ElementTree as ET

NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
WB_REL = {"r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}

def _col_index(cell_ref):
    letters = re.match(r"([A-Z]+)", cell_ref).group(1)
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1

def read_xlsx(path):
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("a:si", NS):
                shared.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["a"])))

        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}

        sheets = {}
        for s in wb.findall("a:sheets/a:sheet", NS):
            name = s.attrib["name"]
            rid = s.attrib["{%s}id" % WB_REL["r"]]
            target = rel_map[rid]
            if target.startswith("/"):
                sheet_path = target.lstrip("/")
            elif target.startswith("xl/"):
                sheet_path = target
            else:
                sheet_path = "xl/" + target

            root = ET.fromstring(z.read(sheet_path))
            rows = []
            for row in root.findall(".//a:sheetData/a:row", NS):
                cells = {}
                max_col = -1
                for c in row.findall("a:c", NS):
                    idx = _col_index(c.attrib.get("r", "A1"))
                    max_col = max(max_col, idx)
                    typ = c.attrib.get("t")
                    v = c.find("a:v", NS)
                    is_node = c.find("a:is", NS)
                    val = ""
                    if typ == "s" and v is not None:
                        val = shared[int(v.text)]
                    elif typ == "inlineStr" and is_node is not None:
                        val = "".join(t.text or "" for t in is_node.iter("{%s}t" % NS["a"]))
                    elif v is not None:
                        val = v.text or ""
                    cells[idx] = val
                if max_col >= 0:
                    rows.append([cells.get(i, "") for i in range(max_col + 1)])
            sheets[name] = rows
        return sheets
