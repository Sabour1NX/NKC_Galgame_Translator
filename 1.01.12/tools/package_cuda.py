# SPDX-License-Identifier: MIT
"""Offline optional CUDA add-on; unzip its contents into the application root.

Only installed, allowlisted runtime/model/helper files are copied. No driver,
configuration, API credentials, screenshots or translation history are included.
The staging tree uses ordinary hard links where possible, never symbolic links.
The resulting ZIP is self-contained and does not depend on the build directory.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {'__pycache__', '.pytest_cache', '.git'}
PUBLIC_FILES = ('tools/cuda_ocr_helper.py', 'tools/ocr_helper.py',
                'tools/setup_cuda_ocr.py', 'CUDA_DEPENDENCY_MANIFEST.json',
                'requirements-cuda.lock')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def safe_tree(base, *, standard_library=False):
    """Reject reparse points before traversing; cache/test exclusions are explicit."""
    base = Path(base)
    if not base.is_dir():
        raise ValueError('Missing runtime directory: ' + base.name)
    if base.is_symlink() or getattr(base.lstat(), 'st_file_attributes', 0) & 0x400:
        raise ValueError('Runtime root is a reparse point')
    for folder, dirs, files in os.walk(base, followlinks=False):
        for name in dirs + files:
            item = Path(folder) / name
            attrs = item.lstat()
            if stat.S_ISLNK(attrs.st_mode) or getattr(attrs, 'st_file_attributes', 0) & 0x400:
                raise ValueError('Runtime contains a reparse point')
        dirs[:] = sorted(name for name in dirs if name not in EXCLUDED and
                         not (standard_library and name in {'site-packages', 'test', 'tests', 'idlelib', 'tkinter', 'turtledemo'}))
        for name in sorted(files):
            if name.endswith(('.pyc', '.pyo')):
                continue
            yield Path(folder) / name


def inventory(root):
    root = Path(root).resolve()
    result = {}
    for name in PUBLIC_FILES:
        path = root / name
        if not path.is_file():
            raise ValueError('Missing public CUDA input: ' + name)
        result[name] = path
    for name in ('vendor/cuda', 'models/cuda', 'third_party/cuda'):
        for path in safe_tree(root / name):
            result[path.relative_to(root).as_posix()] = path
    runtime = root / 'vendor/python'
    for path in runtime.iterdir():
        if path.is_file() and (path.suffix.lower() in {'.exe', '.dll'} or path.name == 'LICENSE.txt'):
            result[path.relative_to(root).as_posix()] = path
    for name in ('Lib', 'DLLs'):
        for path in safe_tree(runtime / name, standard_library=(name == 'Lib')):
            result[path.relative_to(root).as_posix()] = path
    required = {'vendor/python/python.exe', 'vendor/python/python314.dll',
                'vendor/python/LICENSE.txt', 'vendor/python/Lib/encodings/__init__.py',
                'models/cuda/manifest.json', 'models/cuda/LICENSE'}
    if not required <= result.keys():
        raise ValueError('Incomplete isolated CPython/model runtime')
    # Reuse the ordinary release path and private-payload validators.
    from verify_release import relative_name, reject_private_name
    for name, path in result.items():
        relative_name(name)
        reject_private_name(name)
        if path.is_symlink() or getattr(path.lstat(), 'st_file_attributes', 0) & 0x400:
            raise ValueError('Public input must be a regular file')
    return dict(sorted(result.items()))


def validate_inputs(root):
    manifest = json.loads((root / 'CUDA_DEPENDENCY_MANIFEST.json').read_text(encoding='utf-8'))
    normalize = lambda value: re.sub(r'[-_.]+', '-', value).lower()
    installed = {normalize(d.metadata['Name']): d.version for d in
                 importlib.metadata.distributions(path=[str(root / 'vendor/cuda')])}
    for item in manifest['packages']:
        if installed.get(normalize(item['name'])) != item['version']:
            raise ValueError('CUDA package version differs from manifest: ' + item['name'])
    models = json.loads((root / 'models/cuda/manifest.json').read_text(encoding='utf-8'))
    for item in models['models'].values():
        name = item['file']
        if Path(name).name != name or digest(root / 'models/cuda' / name) != item['sha256']:
            raise ValueError('CUDA model digest differs from manifest')
    return len(manifest['packages']), len(models['models'])


def checked_output(root, relative):
    """Validate every parent before any replace/delete operation."""
    root = Path(root).resolve()
    path = root / relative
    if root not in path.resolve().parents or path.resolve() != path:
        raise ValueError('Packaging output escaped version directory')
    for parent in (path, *path.parents):
        if parent.exists() and (parent.is_symlink() or getattr(parent.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Refusing output through a reparse point')
        if parent == root:
            break
    return path


def link_or_copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def build(root=ROOT, *, stage_only=False):
    root = Path(root).resolve()
    if not re.fullmatch(r'\d+\.\d{2}\.\d{2}', root.name):
        raise ValueError('Version directory must follow major.xx.xx')
    packages, models = validate_inputs(root)
    files = inventory(root)
    from verify_release import scan_payload
    scan = scan_payload(files, root)
    stage = checked_output(root, 'build/cuda-addon')
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    for name, path in files.items():
        link_or_copy(path, stage / name)
    probe = subprocess.run([str(stage / 'vendor/python/python.exe'), '-I', '-B', '-c',
        'import encodings,ssl,sqlite3,ctypes,hashlib,json,multiprocessing,urllib.request; print("isolated runtime ready")'],
        cwd=stage, capture_output=True, text=True, timeout=30,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if probe.returncode:
        raise RuntimeError('Staged isolated CPython runtime probe failed')
    hashes = {name: digest(path) for name, path in files.items()}
    metadata = {'schema': 1, 'version': root.name, 'platform': 'Windows x86-64',
                'kind': 'optional CUDA OCR add-on', 'packages': packages, 'models': models,
                'private_configuration_included': False, 'network_requests': 0,
                'files': {name: {'sha256': hashes[name], 'bytes': path.stat().st_size}
                          for name, path in files.items()},
                'install': 'Close the application and extract all contents into its root folder.',
                'limitations': ['Requires compatible NVIDIA GPU and driver; not included.',
                    'Package/model integrity and isolated Python are checked; actual CUDA kernels are verified at startup.',
                    'Dependency licenses are supplied; this is not a new vulnerability scan.']}
    (stage / 'CUDA_ADDON_MANIFEST.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    hashes['CUDA_ADDON_MANIFEST.json'] = digest(stage / 'CUDA_ADDON_MANIFEST.json')
    (stage / 'CUDA_ADDON_SHA256SUMS.txt').write_text(''.join(f'{value}  {name}\n' for name, value in sorted(hashes.items())), encoding='utf-8')
    result = {'version': root.name, 'passed': True, 'files': len(files), 'packages': packages,
              'models': models, 'uncompressed_bytes': sum(path.stat().st_size for path in files.values()),
              'isolated_python_probe': 'passed', 'private_payload_scan': scan,
              'network_requests': 0, 'created_at_utc': datetime.now(timezone.utc).isoformat()}
    if not stage_only:
        archive = checked_output(root, f'dist/NKC_Galgame_Translator-{root.name}-cuda-addon.zip')
        archive.parent.mkdir(parents=True, exist_ok=True)
        temporary = checked_output(root, f'dist/NKC_Galgame_Translator-{root.name}-cuda-addon.zip.part')
        archive_names = sorted((*files, 'CUDA_ADDON_MANIFEST.json', 'CUDA_ADDON_SHA256SUMS.txt'))
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as bundle:
            for name in archive_names:
                bundle.write(stage / name, name)
        with zipfile.ZipFile(temporary) as bundle:
            if sorted(bundle.namelist()) != archive_names:
                raise RuntimeError('CUDA ZIP inventory verification failed')
            if bundle.testzip() is not None:
                raise RuntimeError('CUDA ZIP CRC verification failed')
            for name, checksum in hashes.items():
                with bundle.open(name) as stream:
                    if hashlib.file_digest(stream, 'sha256').hexdigest() != checksum:
                        raise RuntimeError('CUDA ZIP SHA-256 verification failed')
        temporary.replace(archive)
        result.update(archive=archive.name, archive_bytes=archive.stat().st_size,
                      sha256=digest(archive), archive_crc='passed', archive_payload_sha256='passed')
        (archive.parent / f'NKC_Galgame_Translator-{root.name}-cuda-addon-SHA256SUMS.txt').write_text(
            f'{result["sha256"]}  {archive.name}\n', encoding='utf-8')
    report = root / 'reports/cuda-addon-package.json'
    report.parent.mkdir(exist_ok=True)
    report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage-only', action='store_true')
    args = parser.parse_args()
    result = build(stage_only=args.stage_only)
    print(json.dumps({key: value for key, value in result.items() if key != 'private_payload_scan'}))


if __name__ == '__main__':
    main()
