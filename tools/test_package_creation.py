from pathlib import Path

from app.packages.package_extractor import PackageExtractor
from app.packages.package_reader import PackageReader
from app.packages.package_service import PackageService


def main() -> None:
    test_root = Path("test_data/package_test")
    test_root.mkdir(parents=True, exist_ok=True)

    world_file = test_root / "world.db"
    meta_file = test_root / "world.fwl"

    world_file.write_text("fake world data")
    meta_file.write_text("fake metadata")

    output_path = Path("test_data/output/TestWorld.sspkg")

    PackageService.create_package(
        game_id="valheim",
        project_name="TestWorld",
        root_path=test_root,
        save_files=[world_file, meta_file],
        output_path=output_path,
        created_by="Jake",
    )

    info = PackageReader.read(output_path)
    print(info)

    extracted_path = PackageExtractor.extract(output_path)
    print(f"Extracted package to: {extracted_path}")


if __name__ == "__main__":
    main()