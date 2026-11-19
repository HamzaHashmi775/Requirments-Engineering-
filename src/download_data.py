"""Download the raw datasets into data/raw/ (standard library only).

Usage (from the project root):  python src/download_data.py [--force]
"""

import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"

SOURCES = {
    # Orchid-HEval: original prompts, reference solutions, tests, single-type variants
    "orchid_heval.jsonl": "https://huggingface.co/datasets/SII-YDD/Orchid/resolve/main/Orchid-HEval/data.jsonl",
    # Orchid-BCB: first 164 BigCodeBench tasks with the same four single-type variants
    "orchid_bcb.jsonl": "https://huggingface.co/datasets/SII-YDD/Orchid/resolve/main/Orchid-BCB/data.jsonl",
    # HumanEval+: extra test inputs (base_input + plus_input) used by the paper's protocol
    "HumanEvalPlus-v0.1.10.jsonl.gz": "https://github.com/evalplus/humanevalplus_release/releases/download/v0.1.10/HumanEvalPlus.jsonl.gz",
}


def main() -> None:
    force = "--force" in sys.argv
    RAW.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        path = RAW / name
        if path.exists() and not force:
            print(f"skip   {name} (exists)")
        else:
            print(f"fetch  {name}")
            urllib.request.urlretrieve(url, path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        print(f"       {path.stat().st_size:>9} bytes  sha256={digest[:16]}")


if __name__ == "__main__":
    main()
