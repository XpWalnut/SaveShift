from pathlib import Path

ROOT = Path("../app")

for directory in ROOT.rglob("*"):
    if directory.is_dir():
        init_file = directory / "__init__.py"

        if not init_file.exists():
            init_file.touch()
            print(f"Created {init_file}")

print("Done.")