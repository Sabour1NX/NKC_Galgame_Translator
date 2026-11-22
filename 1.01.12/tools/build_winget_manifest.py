# SPDX-License-Identifier: MIT
"""Generate WinGet manifests for a release using the checked-in package metadata."""
import argparse
import hashlib
import re
from pathlib import Path
from urllib.parse import urlsplit
import zipfile

import yaml


TEMPLATES = Path(__file__).resolve().parents[1] / "winget"


def build(installer, version, url, output):
    if not re.fullmatch(r"\d+\.\d{2}\.\d{2}", version):
        raise ValueError("Expected a version in major.xx.xx format.")
    location = urlsplit(url)
    if location.scheme != "https" or not location.hostname or location.path.split("/")[-1] != installer.name:
        raise ValueError("Use the HTTPS release URL for this installer.")
    if output.resolve() == TEMPLATES.resolve():
        raise ValueError("Choose an output directory separate from the templates.")
    with installer.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest().upper()
    output.mkdir(parents=True, exist_ok=True)
    paths = []
    for template in sorted(TEMPLATES.glob("*.yaml")):
        text = template.read_text(encoding="utf-8")
        manifest = yaml.safe_load(text)
        manifest["PackageVersion"] = version
        for entry in manifest.get("Installers", []):
            entry.update(InstallerUrl=url, InstallerSha256=digest)
        if "LicenseUrl" in manifest:
            manifest["LicenseUrl"] = manifest["PackageUrl"] + "/blob/main/" + version + "/LICENSE"
        path = output / template.name
        path.write_text(text.splitlines()[0] + "\n" + yaml.safe_dump(manifest, sort_keys=False, width=200), encoding="utf-8")
        paths.append(path)
    if len(paths) != 3:
        raise ValueError("Expected a version, installer and locale template.")
    with zipfile.ZipFile(output.parent / "winget-manifest.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, "winget/" + path.name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("installer", type=Path)
    parser.add_argument("version")
    parser.add_argument("url")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build(args.installer, args.version, args.url, args.output)
