import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path


def app(home, name, bundle_id):
    path = home / "Applications" / name / "Contents"
    path.mkdir(parents=True)
    with (path / "Info.plist").open("wb") as f:
        plistlib.dump({"CFBundleIdentifier": bundle_id}, f)
    return path.parent


def tile(path, guid, extra=None):
    tile = {
        "GUID": guid,
        "tile-data": {
            "file-data": {
                "_CFURLString": path.as_uri(),
                "_CFURLStringType": 0,
            },
            "file-label": "Zed",
            "file-type": 41,
        },
        "tile-type": "file-tile",
    }
    if extra is not None:
        tile["tile-data"].update(extra)
    return tile


with tempfile.TemporaryDirectory() as directory:
    directory = Path(directory)
    old_home = directory / "old"
    new_home = directory / "new"
    old_zed = app(old_home, "Zed.app", "dev.zed.Zed")
    new_zed = app(new_home, "Zed.app", "dev.zed.Zed")
    unmanaged_zed = directory / "unmanaged" / "Zed.app"

    source = directory / "dock.plist"
    old_apps = directory / "old-applications"
    new_apps = directory / "new-applications"
    old_apps.write_text("Zed.app\n")
    new_apps.write_text("Zed.app\n")

    with source.open("wb") as f:
        plistlib.dump(
            {
                "persistent-apps": [
                    tile(unmanaged_zed, 1),
                    tile(old_zed, 2, {"dock-extra": "preserve"}),
                ]
            },
            f,
        )

    source_before_dry_run = source.read_bytes()
    dry_run = subprocess.run(
        [
            sys.argv[1],
            "--dock-plist",
            str(source),
            "--old-applications",
            str(old_apps),
            "--new-applications",
            str(new_apps),
            "--old-home-path",
            str(old_home),
            "--new-home-path",
            str(new_home),
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert f"Would replace: {old_zed} -> {new_zed}" in dry_run.stdout
    assert source.read_bytes() == source_before_dry_run

    with source.open("rb") as f:
        dry_run_tiles = plistlib.load(f)["persistent-apps"]
    assert dry_run_tiles[1]["tile-data"]["file-data"]["_CFURLString"] == old_zed.as_uri()

    subprocess.run(
        [
            sys.argv[1],
            "--dock-plist",
            str(source),
            "--old-applications",
            str(old_apps),
            "--new-applications",
            str(new_apps),
            "--old-home-path",
            str(old_home),
            "--new-home-path",
            str(new_home),
        ],
        check=True,
    )

    with source.open("rb") as f:
        tiles = plistlib.load(f)["persistent-apps"]

    assert len(tiles) == 2
    assert tiles[0]["GUID"] == 1
    unmanaged_url = tiles[0]["tile-data"]["file-data"]["_CFURLString"]
    assert unmanaged_url == unmanaged_zed.as_uri()
    assert tiles[1]["GUID"] == 2
    assert tiles[1]["tile-data"]["dock-extra"] == "preserve"
    managed_url = tiles[1]["tile-data"]["file-data"]["_CFURLString"]
    assert managed_url == new_zed.as_uri()

    invalid_source = directory / "invalid-dock.plist"
    with invalid_source.open("wb") as f:
        plistlib.dump({"persistent-apps": [tile(new_zed, "invalid")]}, f)

    invalid = subprocess.run(
        [
            sys.argv[1],
            "--dock-plist",
            str(invalid_source),
            "--old-applications",
            str(old_apps),
            "--new-applications",
            str(new_apps),
            "--old-home-path",
            str(old_home),
            "--new-home-path",
            str(new_home),
        ],
        capture_output=True,
        text=True,
    )
    assert invalid.returncode != 0
