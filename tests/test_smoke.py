from importlib.metadata import version
from pathlib import Path

from verify_migration import iter_project_files


def test_package_is_importable_with_version():
    import airt

    assert airt.__version__ == version("airt")


def test_migration_file_scan_ignores_generated_runtime_directories(tmp_path):
    (tmp_path / "src" / "airt").mkdir(parents=True)
    (tmp_path / ".venv" / "Lib").mkdir(parents=True)
    (tmp_path / "reports").mkdir()
    (tmp_path / "src" / "airt" / "module.py").write_text("pass", encoding="utf-8")
    (tmp_path / ".venv" / "Lib" / "generated.py").write_text("pass", encoding="utf-8")
    (tmp_path / "reports" / "report.json").write_text("{}", encoding="utf-8")

    scanned = {path.relative_to(tmp_path) for path in iter_project_files(tmp_path)}

    assert Path("src/airt/module.py") in scanned
    assert Path(".venv/Lib/generated.py") not in scanned
    assert Path("reports/report.json") not in scanned
