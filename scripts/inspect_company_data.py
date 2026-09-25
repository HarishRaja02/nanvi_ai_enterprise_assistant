import os
import csv
from pathlib import Path

def inspect():
    root = Path("C:/CompanyData")
    seen_headers = {}
    total_files = 0
    file_types = {}

    for path in root.rglob("*"):
        if path.is_file():
            total_files += 1
            ext = path.suffix.lower()
            file_types[ext] = file_types.get(ext, 0) + 1

            if ext == ".csv":
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        reader = csv.reader(f)
                        header = next(reader, None)
                        if header:
                            folder = path.parent.name
                            key = f"{folder}::{path.stem.split('_')[0]}"
                            if key not in seen_headers:
                                row_sample = next(reader, None)
                                seen_headers[key] = (header, row_sample, str(path))
                except Exception as e:
                    print(f"Error reading {path}: {e}")

    print(f"Total files in C:/CompanyData: {total_files}")
    print(f"File types: {file_types}")
    print("\n--- Discovered CSV Schemas ---")
    for key, (hdr, row, sample_path) in seen_headers.items():
        print(f"\nGroup: {key}")
        print(f"Sample File: {sample_path}")
        print(f"Headers ({len(hdr)}): {hdr}")
        print(f"Row 1: {row}")

if __name__ == "__main__":
    inspect()
