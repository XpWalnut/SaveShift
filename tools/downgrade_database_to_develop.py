import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.migrations.downgrade import (
    DatabaseDowngradeError,
    downgrade_database_to_develop,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Safely downgrade a Save Shift schema-4 database to develop schema 3."
    )
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--backup-directory", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = downgrade_database_to_develop(
            args.database,
            args.backup_directory,
        )
    except DatabaseDowngradeError as error:
        print(f"Downgrade aborted: {error}", file=sys.stderr)
        cause = error.__cause__
        if cause is not None:
            print(f"Cause: {type(cause).__name__}: {cause}", file=sys.stderr)
        return 1

    if not result.changed:
        print("The database is already compatible with develop (schema 3).")
        return 0
    print("Database downgraded safely from schema 4 to schema 3.")
    print(f"Verified backup: {result.backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
