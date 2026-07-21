import argparse
from dataclasses import dataclass
import os
import plistlib
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path
import time

from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import Callable


PydanticConfig = ConfigDict(extra="allow", serialize_by_alias=True, validate_by_alias=False)


def random_guid() -> int:
    return secrets.randbelow(9_000_000_000) + 1_000_000_000


class FileData(BaseModel):
    model_config = PydanticConfig

    url: str = Field(serialization_alias="_CFURLString", validation_alias="_CFURLString")
    url_type: int = Field(serialization_alias="_CFURLStringType", validation_alias="_CFURLStringType")


class TileData(BaseModel):
    model_config = PydanticConfig

    file_data: FileData = Field(serialization_alias="file-data", validation_alias="file-data")
    file_label: str = Field(serialization_alias="file-label", validation_alias="file-label")
    file_type: int = Field(serialization_alias="file-type", validation_alias="file-type")


class Tile(BaseModel):
    model_config = PydanticConfig

    guid: int = Field(serialization_alias="GUID", validation_alias="GUID")
    tile_data: TileData = Field(serialization_alias="tile-data", validation_alias="tile-data")
    tile_type: str = Field(serialization_alias="tile-type", validation_alias="tile-type")

    def is_supported(self) -> bool:
        return self.tile_type == "file-tile" and self.tile_data.file_type == 41 and self.tile_data.file_data.url_type == 15

    def update_path(self, new_path: Path) -> None:
        assert self.is_supported(), "Tile is not supported"

        self.guid = random_guid()
        self.tile_data.file_label = new_path.stem
        self.tile_data.file_data.url = new_path.as_uri()

    def get_application_path(self) -> Path | None:
        if not self.is_supported():
            return None
            
        return Path.from_uri(self.tile_data.file_data.url)

    @staticmethod
    def from_application_path(application: Path) -> "Tile":
        return Tile(
            guid=random_guid(),
            tile_type="file-tile",
            tile_data=TileData(
                file_label=application.stem,
                file_type=41,
                file_data=FileData(
                    url=application.as_uri(),
                    url_type=15,
                ),
            ),
        )


class Dock(BaseModel):
    model_config = PydanticConfig

    persistent_apps: list[Tile] = Field(serialization_alias="persistent-apps", validation_alias="persistent-apps")

    def find_persistent_app_by_path(self, path: Path) -> tuple[int, Tile] | None:
        for index, tile in enumerate(self.persistent_apps):
            tile_path = tile.get_application_path()
            if tile_path != path:
                continue

            return (index, tile)

        return None

    @staticmethod
    def read_plist(path: Path) -> "Dock":
        with path.open("rb") as f:
            data = plistlib.load(f)

        return Dock.model_validate(data, by_alias=True)

    def write_plist(self, path: Path, fmt: plistlib.PlistFormat) -> None:
        data = self.model_dump()

        with path.open("wb") as f:
            plistlib.dump(data, f, fmt=fmt, sort_keys=False)


@dataclass
class DockMutation:
    description: str
    action: Callable[[Dock], bool]

    @staticmethod
    def create_removal_mutation(app_path: Path) -> "DockMutation":
        def removal_action(dock: Dock) -> bool:
            location = dock.find_persistent_app_by_path(app_path)
            if location is None:
                return False

            index, _ = location
            dock.persistent_apps.pop(index)

            return True

        return DockMutation(
            f"removing from the dock: {app_path}",
            removal_action,
        )

    @staticmethod
    def create_addition_mutation(app_path: Path) -> "DockMutation":
        def addition_action(dock: Dock) -> bool:
            location = dock.find_persistent_app_by_path(app_path)
            if location is not None:
                return False

            app_tile = Tile.from_application_path(app_path)
            dock.persistent_apps.append(app_tile)

            return True

        return DockMutation(
            f"adding to the dock: {app_path}",
            addition_action,
        )

    @staticmethod
    def create_replacement_mutation(old_app_path: Path, new_app_path: Path) -> "DockMutation":
        def replacement_action(dock: Dock) -> bool:
            current_location = dock.find_persistent_app_by_path(old_app_path)
            if current_location is None:
                return DockMutation.create_addition_mutation(new_app_path).action(dock)

            if old_app_path == new_app_path:
                return False

            _, current_tile = current_location
            current_tile.update_path(new_app_path)
            return True

        return DockMutation(
            f"updating in the dock: {old_app_path} -> {new_app_path}",
            replacement_action,
        )

class ScriptArguments(BaseModel):
    dock_plist: Path
    old_applications: Path | None
    new_applications: Path
    old_home_path: Path
    new_home_path: Path
    restart_dock: bool
    dry_run: bool


def parse_arguments() -> ScriptArguments:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dock-plist", type=Path, required=True)
    parser.add_argument("--old-applications", type=Path, required=False)
    parser.add_argument("--new-applications", type=Path, required=True)
    parser.add_argument("--old-home-path", type=Path, required=True)
    parser.add_argument("--new-home-path", type=Path, required=True)
    parser.add_argument("--restart-dock", action="store_true")
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    return ScriptArguments.model_validate(vars(args))

def resolve_app_path(home_path: Path, app_name: str) -> Path:
    app_local_path = home_path / "Applications" / app_name
    return app_local_path.resolve(strict=True)

def create_plan(
    old_home_path: Path,
    new_home_path: Path,
    old_apps: set[str],
    new_apps: set[str],
) -> list[DockMutation]:
    planned_steps = list[DockMutation]()

    removed_apps = old_apps - new_apps
    added_apps = new_apps - old_apps
    kept_apps = new_apps & old_apps

    for app_name in removed_apps:
        app_path = resolve_app_path(old_home_path, app_name)
        planned_steps.append(DockMutation.create_removal_mutation(app_path))

    for app_name in added_apps:
        app_path = resolve_app_path(new_home_path, app_name)
        planned_steps.append(DockMutation.create_addition_mutation(app_path))

    for app_name in kept_apps:
        old_app_path = resolve_app_path(old_home_path, app_name)
        new_app_path = resolve_app_path(new_home_path, app_name)
        planned_steps.append(DockMutation.create_replacement_mutation(old_app_path, new_app_path))

    return planned_steps

def read_apps_manifest(path: Path) -> set[str]:
    with open(path, "r") as f:
        return set(line.strip() for line in f.readlines() if line)


def main() -> None:
    args = parse_arguments()

    dock = Dock.read_plist(args.dock_plist)

    old_apps = set() if args.old_applications is None else read_apps_manifest(args.old_applications)
    new_apps = read_apps_manifest(args.new_applications)

    plan = create_plan(
        args.old_home_path,
        args.new_home_path,
        old_apps,
        new_apps,
    )

    changed = False
    for step in plan:
        print(step.description)

        if not args.dry_run:
            step_changed = step.action(dock)
            changed = changed or step_changed

    if not args.dry_run and changed:
        temporary_fd, temporary_path = tempfile.mkstemp(
            dir=args.dock_plist.parent,
            prefix=f"{args.dock_plist.name}.",
        )

        try:
            os.close(temporary_fd)

            dock.write_plist(Path(temporary_path), fmt=plistlib.FMT_BINARY)
            os.replace(temporary_path, args.dock_plist)

            if args.restart_dock:
                time.sleep(1)
                subprocess.run(["/usr/bin/killall", "Dock"], check=True)
                subprocess.run(["/usr/bin/killall", "Dock"], check=True)
        finally:
            try:
              os.unlink(temporary_path)
            except:
              pass


if __name__ == "__main__":
    main()
