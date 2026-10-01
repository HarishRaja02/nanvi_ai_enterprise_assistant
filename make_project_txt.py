from pathlib import Path

PROJECT = Path(__file__).parent
OUTPUT = PROJECT / "project_for_deepseek.txt"

EXCLUDE_DIRS = {
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".next",
}

EXCLUDE_FILES = {
    ".env",
    "project_for_deepseek.txt",
}

EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx",
    ".html", ".css", ".scss",
    ".json", ".yaml", ".yml",
    ".md", ".txt",
    ".sql", ".toml",
    ".ini", ".cfg",
}

with open(OUTPUT, "w", encoding="utf-8") as out:

    for file in PROJECT.rglob("*"):

        if not file.is_file():
            continue

        if file.name in EXCLUDE_FILES:
            continue

        if any(part in EXCLUDE_DIRS for part in file.parts):
            continue

        if file.suffix.lower() not in EXTENSIONS:
            continue

        relative = file.relative_to(PROJECT)

        print(f"Adding: {relative}")

        out.write("\n\n")
        out.write("=" * 80)
        out.write(f"\nFILE: {relative}\n")
        out.write("=" * 80)
        out.write("\n\n")

        try:
            content = file.read_text(encoding="utf-8")
            out.write(content)
        except Exception as e:
            out.write(f"[Could not read file: {e}]")

print("\nDONE!")
print(f"Created: {OUTPUT}")