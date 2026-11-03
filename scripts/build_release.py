"""Build the plugin archive from an explicit public file list."""

from pathlib import Path
import zipfile

import yaml


ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = (
    "main.py",
    "metadata.yaml",
    "_conf_schema.json",
    "requirements.txt",
    "package.json",
    "package-lock.json",
    "README.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "licenses/MagVarUpdate-MIT.txt",
    "examples/manifest.yaml",
    "docs/user-guide.md",
    "docs/ejs-mvu-runtime.md",
    "docs/source-audit-2026-11-03.md",
    "docs/release-acceptance-2026-11-03.md",
)
MODULE_FILES = (
    "__init__.py",
    "audit.py",
    "contract.py",
    "ejs_bridge.cjs",
    "ejs_runtime.py",
    "event_engine.py",
    "generation_self_check.py",
    "handler_binding.py",
    "main.py",
    "mvu.py",
    "package_loader.py",
    "page_api.py",
    "predicate.py",
    "prompt_builder.py",
    "repository.py",
    "state_store.py",
    "status_image.py",
    "assets/OFL.txt",
    "assets/LXGWWenKaiLite-Regular.ttf",
)


def public_files() -> list[Path]:
    paths = [ROOT / name for name in ROOT_FILES]
    paths.extend(ROOT / "astrbot_plugin_rolecard_runtime" / name for name in MODULE_FILES)
    paths.append(ROOT / "pages" / "角色卡面板" / "index.html")
    return sorted(paths)


def build_release() -> Path:
    version = yaml.safe_load((ROOT / "metadata.yaml").read_text(encoding="utf-8"))["version"]
    output = ROOT / "dist" / f"astrbot_plugin_rolecard_runtime-{version}.zip"
    output.parent.mkdir(exist_ok=True)
    files = public_files()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError("发行 ZIP 检查失败")
        print(f"{output.name}: {len(archive.namelist())} files")
    return output


if __name__ == "__main__":
    build_release()
