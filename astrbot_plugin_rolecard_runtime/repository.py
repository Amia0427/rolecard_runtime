from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from .package_loader import RoleCardPackage, _find_legacy_root, _find_manifest_root, _safe_archive_files, load_directory, load_json, load_zip


class PackageRepository:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.packages: dict[str, RoleCardPackage] = {}
        self.diagnostics: list[dict[str, str]] = []
        self.reload()

    def reload(self) -> None:
        self.packages = {}
        self.diagnostics = []
        for path in self.root.iterdir():
            if path.is_dir():
                try:
                    package = load_directory(path)
                except ValueError as exc:
                    self.diagnostics.append({"path": str(path), "reason": str(exc)})
                    continue
                self.packages[package.package_id] = package

    def get(self, package_id: str) -> RoleCardPackage | None:
        return self.packages.get(package_id)

    def list(self) -> list[RoleCardPackage]:
        return sorted(self.packages.values(), key=lambda package: package.display_name)

    def import_zip(self, data: bytes, source: str = "") -> RoleCardPackage:
        package = load_zip(data, source)
        if package.package_id in self.packages:
            raise ValueError(f"卡包已存在，拒绝覆盖：{package.package_id}")
        files = _safe_archive_files(data)
        manifest_root = _find_manifest_root(files)
        package_root = manifest_root or _find_legacy_root(files)
        if package_root:
            prefix = package_root + "/"
            files = {
                name[len(prefix):]: content
                for name, content in files.items()
                if name.startswith(prefix)
            }
        target = self.root / package.package_id
        staging = Path(tempfile.mkdtemp(prefix=f"{package.package_id}-", dir=self.root))
        try:
            for name, content in files.items():
                path = staging / Path(name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            staging.rename(target)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        self.packages[package.package_id] = load_directory(target)
        return self.packages[package.package_id]

    def import_json(self, data: bytes, source: str = "") -> RoleCardPackage:
        package = load_json(data, source)
        if package.package_id in self.packages:
            raise ValueError(f"卡包已存在，拒绝覆盖：{package.package_id}")
        staging = Path(tempfile.mkdtemp(prefix=f"{package.package_id}-", dir=self.root))
        try:
            (staging / "character.json").write_bytes(data)
            target = self.root / package.package_id
            staging.rename(target)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        self.packages[package.package_id] = load_directory(target)
        return self.packages[package.package_id]

    def import_file(self, data: bytes, source: str = "") -> RoleCardPackage:
        if Path(source).suffix.lower() == ".json":
            return self.import_json(data, source)
        return self.import_zip(data, source)

    def import_directory(self, source: Path) -> RoleCardPackage:
        package = load_directory(source)
        if package.package_id in self.packages:
            raise ValueError(f"卡包已存在，拒绝覆盖：{package.package_id}")
        target = self.root / package.package_id
        shutil.copytree(source, target)
        self.packages[package.package_id] = load_directory(target)
        return self.packages[package.package_id]

    def delete(self, package_id: str) -> bool:
        package = self.packages.pop(package_id, None)
        if package is None:
            return False
        target = self.root / package_id
        if target.exists():
            shutil.rmtree(target)
        return True

