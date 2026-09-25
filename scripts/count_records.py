import os
import csv
from pathlib import Path

def count_records():
    root = Path("C:/CompanyData")
    counts = {}
    for path in root.rglob("*.csv"):
        folder = path.parent.name
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                num_rows = sum(1 for _ in reader)
                counts[folder] = counts.get(folder, 0) + num_rows
        except Exception as e:
            pass

    print("CSV Rows by Folder:")
    for folder, count in sorted(counts.items()):
        print(f"  {folder}: {count} rows")

if __name__ == "__main__":
    count_records()
