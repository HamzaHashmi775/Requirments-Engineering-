"""Result tables as images, laid out like the paper's Tables 4-6 (+ two extension tables).

Reads only the result files (no Claude calls) and writes, to results/figures/:
  table4_passk.png          Pass@K: original and Δ = combined - original (paper Table 4)
  table5_conflict.png       Conflict rate, original vs combined (paper Table 5)
  table6_recognition.png    Recognition: Pre / Rec / Una / Det / Loc / Tac (paper Table 6)
  table7_localization.png   Extension: localization per injected ambiguity type
  table8_per_task.png       Extension: per-requirement pass@1 and conflict
plus the .html source of each. PNGs are rendered with headless Edge or Chrome (Windows paths).

Usage (from the project root):  python src/make_tables.py
"""

import json
import struct
import subprocess
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "figures"
MODELS = {"claude-opus-5-5": "Claude-Opus-5.5", "claude-sonnet-5-5": "Claude-Sonnet-5.5"}
SUBSETS = {"heval": ("Orchid-HEval", ROOT / "results"), "bcb": ("Orchid-BCB", ROOT / "results" / "bcb")}
# tasks whose original tests do not match their prompt (see CLAUDE.md), marked in Table 8
MISMATCH = {"R6": "bool excluded", "B6": "DictWriter", "B7": "mocked isfile", "B8": "message text",
            "B11": "file name", "B12": "mocked glob"}
BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe"]

CSS = """
body { margin: 0; padding: 24px; background: #fff; color: #000; font-family: "Times New Roman", Times, serif; }
.wrap { display: inline-table; padding: 18px 22px; }
sup { line-height: 0; }
.cap { font-size: 15px; text-align: center; margin: 0 0 8px; }
.cap b { font-weight: bold; }
table { border-collapse: collapse; font-size: 14px; }
th, td { padding: 3px 9px; text-align: center; white-space: nowrap; }
td.l, th.l { text-align: left; }
thead tr:first-child th { border-top: 1.6px solid #000; }
thead tr:last-child th { border-bottom: 0.9px solid #000; }
tbody tr:last-child td { border-bottom: 1.6px solid #000; }
th.grp { border-bottom: 0.6px solid #000; }
tr.sec td { font-style: italic; text-align: left; border-top: 0.6px solid #000; border-bottom: 0.6px solid #000; }
td.neg { color: #b00000; }
td.pos { color: #006400; }
.note { display: table-caption; caption-side: bottom; font-size: 12px; padding-top: 6px; }
"""


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def pct(x) -> str:
    return "–" if x is None else f"{100 * x:.2f}"


def delta(o, c) -> str:
    if o is None or c is None:
        return "<td>–</td>"
    d = 100 * (c - o)
    cls = "neg" if d < -0.005 else "pos" if d > 0.005 else ""
    return f'<td class="{cls}">{d:+.2f}</td>'


def page(caption: str, table: str, note: str = "") -> str:
    return (f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>"
            f"<div class='wrap'><p class='cap'>{caption}</p>{table}"
            + (f"<div class='note'>{note}</div>" if note else "") + "</div></body></html>")


def table4(summ: dict) -> str:
    groups = [("Orchid-HEval", summ["heval"], "overall"), ("Orchid-HEval (valid)", summ["heval"], "valid_only"),
              ("Orchid-BCB", summ["bcb"], "overall"), ("Orchid-BCB (valid)", summ["bcb"], "valid_only")]
    head = ("<thead><tr><th class='l' rowspan='2'>Models</th>"
            + "".join(f"<th class='grp' colspan='2'>{g}</th>" for g, _, _ in groups) + "</tr><tr>"
            + "<th>Orig.</th><th>Δ Comb.</th>" * len(groups) + "</tr></thead>")
    body = []
    for k in (1, 3, 5):
        body.append(f"<tr class='sec'><td colspan='{1 + 2 * len(groups)}'>Pass@{k} (%)</td></tr>")
        for m, name in MODELS.items():
            cells = []
            for _, s, kind in groups:
                o, c = ((s["overall"]["original"], s["overall"]["combined"]) if kind == "overall"
                        else (s["valid_only"][m]["original"], s["valid_only"][m]["combined"]))
                o, c = o.get(f"{m}|pass@{k}"), c.get(f"{m}|pass@{k}")
                cells.append(f"<td>{pct(o)}</td>{delta(o, c)}")
            body.append(f"<tr><td class='l'>{name}</td>{''.join(cells)}</tr>")
    n_valid = "; ".join(f"{MODELS[m]}: HEval {len(summ['heval']['valid_only'][m]['tasks'])}/6, "
                        f"BCB {len(summ['bcb']['valid_only'][m]['tasks'])}/12" for m in MODELS)
    note = ("Δ Comb. = pass@k(combined) − pass@k(original) in percentage points (negative = drop), as in the paper. "
            "Each requirement combines two ambiguity types; n = 5 samples per model and variant. "
            f"<i>Valid</i>: only tasks the model solves from the original prompt in ≥ 4/5 samples ({n_valid}).")
    return page("<b>Table 4:</b> Pass@K of LLMs on original and combined-ambiguity requirements.",
                f"<table>{head}<tbody>{''.join(body)}</tbody></table>", note)


def table5(summ: dict) -> str:
    head = ("<thead><tr><th class='l' rowspan='2'>Models</th>"
            + "".join(f"<th class='grp' colspan='2'>{SUBSETS[s][0]} (%)</th>" for s in summ) + "</tr><tr>"
            + "<th>Original</th><th>Combined</th>" * len(summ) + "</tr></thead>")
    rows = [(name, f"{m}|conflict") for m, name in MODELS.items()] + [("Multi-models", "inter_model_conflict")]
    body = []
    for name, key in rows:
        cells = []
        for s in summ.values():
            o, c = s["overall"]["original"][key], s["overall"]["combined"][key]
            cells.append(f"<td>{pct(o)}</td><td>{'<b>' + pct(c) + '</b>' if c > o else pct(c)}</td>")
        body.append(f"<tr><td class='l'>{name}</td>{''.join(cells)}</tr>")
    note = ("Conflict rate = share of sample pairs that behave differently on at least one test. Model rows: intra-model "
            "(5 samples); Multi-models: inter-model (10 samples of both models). * Bold indicates a combined-ambiguity "
            "conflict rate higher than the original requirement.")
    return page("<b>Table 5:</b> Conflict Rate of LLMs on original and combined-ambiguity requirements.",
                f"<table>{head}<tbody>{''.join(body)}</tbody></table>", note)


def table6(rec: dict) -> str:
    cols = ["Pre(%)", "Rec(%)", "Una(%)", "Det(%)", "Loc(%)", "Tac(%)"]
    head = ("<thead><tr><th class='l' rowspan='2'>Models</th>"
            + "".join(f"<th class='grp' colspan='6'>{SUBSETS[s][0]}</th>" for s in rec) + "</tr><tr>"
            + "".join(f"<th>{c}</th>" for c in cols) * len(rec) + "</tr></thead>")
    body = []
    for m, name in MODELS.items():
        cells = []
        for r in rec.values():
            d = r[m]
            lv = d["overall_levels"]
            n = sum(lv.values())
            cells.append(f"<td>{pct(d['precision'])}</td><td>{pct(d['recall'])}</td>"
                         + "".join(f"<td>{pct(lv[k] / n)}</td>" for k in ("unaware", "detection", "localization", "tackling")))
        body.append(f"<tr><td class='l'>{name}</td>{''.join(cells)}</tr>")
    note = ("Pre / Rec: precision and recall of flagging a requirement as ambiguous (original vs combined). "
            "Una / Det / Loc / Tac: share of combined requirements graded Unaware / Detection / Localization / Tackling "
            "(paper's single label = best level over the two injected ambiguities). LLM judge: Claude-Opus-5.5; "
            "all 72 judge grades checked by hand (100% agreement).")
    return page("<b>Table 6:</b> Evaluation of LLM capability of recognizing combined ambiguity in requirements.",
                f"<table>{head}<tbody>{''.join(body)}</tbody></table>", note)


def table7(rec: dict) -> str:
    keys = [(s, m) for s in rec for m in MODELS]
    head = ("<thead><tr><th class='l' rowspan='2'>Ambiguity type</th>"
            + "".join(f"<th class='grp' colspan='2'>{SUBSETS[s][0]}</th>" for s in rec) + "</tr><tr>"
            + "".join(f"<th>{MODELS[m]}</th>" for _, m in keys) + "</tr></thead>")
    body = []
    for t in ("Lexical", "Syntactic", "Semantic", "Vagueness"):
        body.append(f"<tr><td class='l'>{t}</td>" + "".join(f"<td>{rec[s][m]['per_type_localized'][t]}</td>" for s, m in keys) + "</tr>")
    body.append("<tr><td class='l'>Both ambiguities localized</td>"
                + "".join(f"<td>{rec[s][m]['both_localized']}/{rec[s][m]['flagged_combined'].split('/')[1]}</td>" for s, m in keys) + "</tr>")
    note = ("Extension for combined ambiguity: number of injected ambiguities of each type that the model localized "
            "or tackled, out of the requirements containing that type.")
    return page("<b>Table 7:</b> Localization per injected ambiguity type (combined requirements).",
                f"<table>{head}<tbody>{''.join(body)}</tbody></table>", note)


def table8(summ: dict) -> str:
    head = ("<thead><tr><th class='l' rowspan='2'>Req.</th><th rowspan='2'>Types</th>"
            + "".join(f"<th class='grp' colspan='2'>{n} pass@1 (%)</th>" for n in MODELS.values())
            + "<th class='grp' colspan='2'>Multi-model conflict (%)</th></tr><tr>"
            + "<th>Orig.</th><th>Comb.</th>" * 3 + "</tr></thead>")
    body = []
    for s, (label, _) in SUBSETS.items():
        body.append(f"<tr class='sec'><td colspan='9'>{label}</td></tr>")
        rows = summ[s]["per_task"]
        ids = sorted({r["id"] for r in rows}, key=lambda x: int(x[1:]))
        for rid in ids:
            o = next(r for r in rows if r["id"] == rid and r["variant"] == "original")
            c = next(r for r in rows if r["id"] == rid and r["variant"] == "combined")
            mark = "<sup>†</sup>" if rid in MISMATCH else ""
            cells = "".join(f"<td>{pct(o[f'{m}|pass@1'])}</td>{delta_cell(o[f'{m}|pass@1'], c[f'{m}|pass@1'])}" for m in MODELS)
            body.append(f"<tr><td class='l'>{rid}{mark}</td><td>{o['pair']}</td>{cells}"
                        f"<td>{pct(o['inter_model_conflict'])}</td><td>{pct(c['inter_model_conflict'])}</td></tr>")
    note = ("L = Lexical, S = Syntactic, M = Semantic, V = Vagueness. Red: combined lower than original. "
            "† Test/prompt mismatch in the benchmark (fails on the original prompt too): "
            + "; ".join(f"{k} {v}" for k, v in MISMATCH.items()) + ".")
    return page("<b>Table 8:</b> Per-requirement results (pass@1 and inter-model conflict rate).",
                f"<table>{head}<tbody>{''.join(body)}</tbody></table>", note)


def delta_cell(o, c) -> str:
    cls = "neg" if c is not None and o is not None and c < o - 1e-9 else ""
    return f'<td class="{cls}">{pct(c)}</td>'


def crop_png(path: Path, margin: int = 24) -> None:
    """Trim the white border of an 8-bit RGB/RGBA, non-interlaced PNG (what the browser writes),
    with the standard library only."""
    data = path.read_bytes()
    pos, idat, ihdr = 8, b"", None
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        chunk = data[pos + 8:pos + 8 + n]
        if kind == b"IHDR":
            ihdr = chunk
        elif kind == b"IDAT":
            idat += chunk
        pos += 12 + n
    w, h, depth, ctype = struct.unpack(">IIBB", ihdr[:10])
    if depth != 8 or ctype not in (2, 6) or ihdr[12] != 0:
        return
    bpp = 3 if ctype == 2 else 4
    raw, stride, rows, prev = zlib.decompress(idat), w * bpp, [], bytearray(w * bpp)
    for y in range(h):
        f, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):  # undo the PNG row filter
            a = line[i - bpp] if i >= bpp else 0
            b, c = prev[i], prev[i - bpp] if i >= bpp else 0
            if f == 1: line[i] = (line[i] + a) & 255
            elif f == 2: line[i] = (line[i] + b) & 255
            elif f == 3: line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(line)
        prev = line
    white = bytes([255]) * stride
    ys = [y for y in range(h) if rows[y] != white]
    if not ys:
        return
    xs = [x for x in range(w) if any(rows[y][x * bpp:x * bpp + 3] != b"\xff\xff\xff" for y in ys[::2])]
    x0, x1 = max(xs[0] - margin, 0), min(xs[-1] + margin + 1, w)
    y0, y1 = max(ys[0] - margin, 0), min(ys[-1] + margin + 1, h)
    body = b"".join(b"\x00" + bytes(rows[y][x0 * bpp:x1 * bpp]) for y in range(y0, y1))
    chunk = lambda k, d: struct.pack(">I", len(d)) + k + d + struct.pack(">I", zlib.crc32(k + d))
    new_ihdr = struct.pack(">IIBBBBB", x1 - x0, y1 - y0, 8, ctype, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", new_ihdr)
                     + chunk(b"IDAT", zlib.compress(body, 9)) + chunk(b"IEND", b""))


def render(html: Path, png: Path) -> bool:
    browser = next((b for b in BROWSERS if Path(b).exists()), None)
    if browser is None:
        return False
    # wide viewport; the page is inline-block, so the image is trimmed to the table below
    tmp = png.with_suffix(".full.png")
    subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
                    "--window-size=1400,900", f"--screenshot={tmp}", html.as_uri()],
                   capture_output=True, timeout=120)
    if not tmp.exists():
        return False
    tmp.replace(png)
    crop_png(png)
    return True


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    summ = {s: load(p / "summary.json") for s, (_, p) in SUBSETS.items()}
    rec = {s: load(p / "recognition_summary.json") for s, (_, p) in SUBSETS.items()}
    pages = {"table4_passk": table4(summ), "table5_conflict": table5(summ), "table6_recognition": table6(rec),
             "table7_localization": table7(rec), "table8_per_task": table8(summ)}
    for name, html in pages.items():
        h = OUT / f"{name}.html"
        h.write_text(html, encoding="utf-8")
        print(name, "->", (OUT / f"{name}.png") if render(h, OUT / f"{name}.png") else "html only (no browser)")


if __name__ == "__main__":
    main()
