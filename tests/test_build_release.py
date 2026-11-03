from pathlib import Path
import zipfile

from scripts import build_release


def test_release_uses_only_approved_public_files(tmp_path: Path, monkeypatch) -> None:
    source = build_release.ROOT
    approved = [path.relative_to(source) for path in build_release.public_files()]
    for relative in approved:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source / relative).read_bytes())
    (tmp_path / "astrbot_plugin_rolecard_runtime" / "private_theme.py").write_text("PRIVATE", encoding="utf-8")
    (tmp_path / "private-card.zip").write_bytes(b"PRIVATE")
    (tmp_path / "runtime.sqlite3").write_bytes(b"PRIVATE")
    monkeypatch.setattr(build_release, "ROOT", tmp_path)

    archive_path = build_release.build_release()

    with zipfile.ZipFile(archive_path) as archive:
        assert set(archive.namelist()) == {path.as_posix() for path in approved}
        assert archive.read("metadata.yaml") == (source / "metadata.yaml").read_bytes()
        assert "astrbot_plugin_rolecard_runtime/ejs_bridge.cjs" in archive.namelist()
        assert "astrbot_plugin_rolecard_runtime/mvu.py" in archive.namelist()
