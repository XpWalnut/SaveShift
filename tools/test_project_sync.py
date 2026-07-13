from pathlib import Path
from tempfile import TemporaryDirectory

from app.database.models.project import Project
from app.services.save_file_service import SaveFileService


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def list_relative_files(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)

        project_root = temp_root / "project"
        source_root = temp_root / "source"

        write_file(project_root / "A.txt", "old A")
        write_file(project_root / "B.txt", "old B should be deleted")
        write_file(project_root / "folder" / "C.txt", "old C")

        write_file(source_root / "A.txt", "new A")
        write_file(source_root / "folder" / "C.txt", "new C")
        write_file(source_root / "D.txt", "new D")

        project = Project(
            installed_game_id=1,
            name="Test Project",
            local_path=str(project_root),
        )

        SaveFileService.synchronize_project(
            project=project,
            source_directory=source_root,
        )

        actual_files = list_relative_files(project_root)
        expected_files = {
            "A.txt",
            "folder/C.txt",
            "D.txt",
        }

        assert actual_files == expected_files
        assert (project_root / "A.txt").read_text() == "new A"
        assert (project_root / "folder" / "C.txt").read_text() == "new C"
        assert (project_root / "D.txt").read_text() == "new D"
        assert not (project_root / "B.txt").exists()

        print("Project synchronization test passed.")


if __name__ == "__main__":
    main()