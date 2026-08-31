import subprocess
from pathlib import Path


def _run_dry_run(
    project_root: Path,
    script: Path,
    sdk_root: Path,
    content_root: Path,
    configuration_root: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-SteamUsername",
            "test-user",
            "-SteamworksSdkPath",
            str(sdk_root),
            "-ContentRoot",
            str(content_root),
            "-ConfigurationRoot",
            str(configuration_root),
            "-SkipBuild",
            "-DryRun",
        ],
        cwd=project_root,
        capture_output=True,
        check=False,
        text=True,
    )


def _create_fake_sdk(sdk_root: Path) -> None:
    steamcmd = (
        sdk_root
        / "tools"
        / "ContentBuilder"
        / "builder"
        / "steamcmd.exe"
    )
    steamcmd.parent.mkdir(parents=True)
    steamcmd.write_bytes(b"")


def test_steam_upload_dry_run_generates_expected_configuration(
    tmp_path: Path,
) -> None:
    project_root = Path(__file__).resolve().parents[2]
    script = project_root / "tools" / "upload_steam_build.ps1"
    sdk_root = tmp_path / "sdk"
    _create_fake_sdk(sdk_root)
    content_root = tmp_path / "content"
    content_root.mkdir()
    (content_root / "SaveShift.exe").write_bytes(b"test executable")
    configuration_root = tmp_path / "configuration"

    result = _run_dry_run(
        project_root,
        script,
        sdk_root,
        content_root,
        configuration_root,
    )

    assert result.returncode == 0, result.stderr
    assert "nothing was uploaded" in result.stdout

    depot_config = (
        configuration_root / "depot_build_5096901.vdf"
    ).read_text(encoding="utf-8-sig")
    app_config = (
        configuration_root / "app_build_5096900.vdf"
    ).read_text(encoding="utf-8-sig")

    assert '"DepotID" "5096901"' in depot_config
    assert str(content_root.resolve()) in depot_config
    assert '"AppID" "5096900"' in app_config
    assert '"5096901"' in app_config
    assert "test-user" not in depot_config
    assert "test-user" not in app_config


def test_steam_upload_rejects_development_app_id_file(
    tmp_path: Path,
) -> None:
    project_root = Path(__file__).resolve().parents[2]
    script = project_root / "tools" / "upload_steam_build.ps1"
    sdk_root = tmp_path / "sdk"
    _create_fake_sdk(sdk_root)
    content_root = tmp_path / "content"
    content_root.mkdir()
    (content_root / "SaveShift.exe").write_bytes(b"test executable")
    (content_root / "steam_appid.txt").write_text(
        "5096900",
        encoding="utf-8",
    )

    result = _run_dry_run(
        project_root,
        script,
        sdk_root,
        content_root,
        tmp_path / "configuration",
    )

    assert result.returncode != 0
    assert "development-only steam_appid.txt" in (
        result.stdout + result.stderr
    )
