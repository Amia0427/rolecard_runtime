"""Build and smoke-test the public example card."""

import json
from pathlib import Path
import sys
import zipfile

import yaml
from jsonschema.validators import validator_for


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astrbot_plugin_rolecard_runtime.package_loader import load_directory, load_json, load_zip


EXAMPLE_ROOT = ROOT / "examples" / "minimal"
SCHEMA_PATH = ROOT / "schemas" / "manifest.schema.json"
LICENSE_PATH = ROOT / "LICENSE"
EXAMPLE_FILES = (
    "manifest.yaml",
    "card/character.json",
    "state/contract.yaml",
    "state/schema.json",
    "state/audit_system_prompt.md",
    "prompts/first_meeting.md",
    "prompts/familiar.md",
    "worldbook/shop.md",
    "runtime/scene.ejs",
    "runtime/event_pool.ejs",
    "events/welcome.md",
    "events/restock.md",
    "greetings/first_mes.md",
    "README.md",
)


def _read_example() -> dict[str, str]:
    files = {}
    for relative in EXAMPLE_FILES:
        files[relative] = (EXAMPLE_ROOT / relative).read_text(encoding="utf-8")
    files["LICENSE"] = LICENSE_PATH.read_text(encoding="utf-8")
    return files


def _validate_manifest(manifest: dict) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    validator_class(schema).validate(manifest)


def _embedded_card(files: dict[str, str]) -> bytes:
    card = json.loads(files["card/character.json"])
    data = card.setdefault("data", {})
    extensions = data.setdefault("extensions", {})
    extensions["astrbot_runtime"] = {"files": files}
    return json.dumps(card, ensure_ascii=False, indent=2).encode("utf-8")


def _write_zip(files: dict[str, str], path: Path) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative, text in files.items():
            archive.writestr(relative, text.encode("utf-8"))
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("示例 ZIP 检查失败")


def build_example() -> tuple[Path, Path]:
    files = _read_example()
    manifest = yaml.safe_load(files["manifest.yaml"])
    _validate_manifest(manifest)
    directory_package = load_directory(EXAMPLE_ROOT)

    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    zip_path = output / "example-card.zip"
    json_path = output / "example-card.json"
    _write_zip(files, zip_path)
    json_path.write_bytes(_embedded_card(files))

    zip_package = load_zip(zip_path.read_bytes(), str(zip_path))
    json_package = load_json(json_path.read_bytes(), str(json_path))
    if {directory_package.package_id, zip_package.package_id, json_package.package_id} != {"example-card"}:
        raise ValueError("示例卡包 ID 不一致")
    return zip_path, json_path


if __name__ == "__main__":
    zip_path, json_path = build_example()
    print(f"{zip_path}")
    print(f"{json_path}")
