# SPDX-License-Identifier: MIT
"""Boundaries of the public, optional runtime packaging allowlist."""
from pathlib import Path
import importlib.util
import sys

import pytest

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location('cuda_package27', TOOLS / 'package_cuda.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


def put(root, name, text='public'):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def fake_runtime(root):
    for name in (*package.PUBLIC_FILES, 'vendor/cuda/runtime.py', 'models/cuda/manifest.json',
                 'models/cuda/LICENSE', 'third_party/cuda/LICENSE', 'vendor/python/python.exe',
                 'vendor/python/python314.dll', 'vendor/python/LICENSE.txt',
                 'vendor/python/Lib/encodings/__init__.py', 'vendor/python/DLLs/_ssl.pyd'):
        put(root, name)


def test_inventory_excludes_private_configuration_and_developer_runtime(tmp_path):
    fake_runtime(tmp_path)
    for name in ('config/local.json', 'config/credentials.bin', 'data/codebook.sqlite3',
                 'vendor/python/Lib/site-packages/private.py', 'vendor/python/Lib/test/test_os.py',
                 'vendor/python/Lib/encodings/__pycache__/x.pyc', 'vendor/cuda/__pycache__/x.pyc',
                 'vendor/python/tcl/secret.txt', 'vendor/python/Tools/dev.py'):
        put(tmp_path, name)
    result = package.inventory(tmp_path)
    assert 'vendor/python/Lib/encodings/__init__.py' in result
    assert 'vendor/python/DLLs/_ssl.pyd' in result
    assert 'third_party/cuda/LICENSE' in result
    assert not any(key.startswith(('config/', 'data/')) for key in result)
    assert not any(part in {'site-packages', 'test', '__pycache__', 'tcl', 'Tools'}
                   for key in result for part in key.split('/'))


def test_private_payload_inside_allowlisted_dependency_is_rejected(tmp_path):
    fake_runtime(tmp_path)
    put(tmp_path, 'vendor/cuda/credentials.bin')
    with pytest.raises(Exception, match='private_payload_name'):
        package.inventory(tmp_path)


def test_missing_stdlib_prevents_incomplete_addon(tmp_path):
    fake_runtime(tmp_path)
    (tmp_path/'vendor/python/Lib/encodings/__init__.py').unlink()
    with pytest.raises(ValueError, match='Incomplete isolated'):
        package.inventory(tmp_path)


def test_output_must_stay_inside_version_directory(tmp_path):
    root = tmp_path / '0.01.27'
    root.mkdir()
    assert package.checked_output(root, 'build/cuda-addon') == root/'build/cuda-addon'
    with pytest.raises(ValueError, match='escaped'):
        package.checked_output(root, '../other-version')


def test_standard_release_source_inventory_requires_optional_install_descriptors():
    from verify_release import REQUIRED_RELEASE, REQUIRED_SOURCE, SOURCE_FILES
    required = {'requirements-cuda.lock', 'CUDA_DEPENDENCY_MANIFEST.json',
                'models/cuda/manifest.json', 'models/cuda/LICENSE'}
    assert required <= REQUIRED_RELEASE & REQUIRED_SOURCE & SOURCE_FILES
    assert {'tools/cuda_ocr_helper.py', 'tools/setup_cuda_ocr.py'} <= REQUIRED_RELEASE


def test_stage_hardlink_is_standalone_when_source_disappears(tmp_path):
    source, target = tmp_path/'source.bin', tmp_path/'copy/runtime.bin'
    source.write_bytes(b'public runtime')
    package.link_or_copy(source, target)
    source.unlink()
    assert target.read_bytes() == b'public runtime'


def test_public_spdx_identifier_does_not_disable_general_token_scan():
    from verify_release import PRIVATE_TOKEN
    assert not PRIVATE_TOKEN.search(b'Asteri' + b'sk-' + b'linking-protocols-exception')
    assert PRIVATE_TOKEN.search(b'sk-' + b'a' * 32)
    assert PRIVATE_TOKEN.search(b'sk-' + b'linking-protocols-exception-more')


def test_zip_includes_only_allowlisted_files_even_if_probe_adds_cache(tmp_path, monkeypatch):
    import json
    import zipfile
    from types import SimpleNamespace
    root = tmp_path / '0.01.27'
    fake_runtime(root)
    monkeypatch.setattr(package, 'validate_inputs', lambda value: (28, 2))
    def probe(argv, **kwargs):
        assert '-B' in argv
        put(root/'build/cuda-addon', 'vendor/python/Lib/__pycache__/probe.pyc')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(package.subprocess, 'run', probe)
    result = package.build(root)
    with zipfile.ZipFile(root/'dist'/result['archive']) as archive:
        assert not any('__pycache__' in name for name in archive.namelist())
        manifest = json.loads(archive.read('CUDA_ADDON_MANIFEST.json'))
        assert set(archive.namelist()) == set(manifest['files']) | {
            'CUDA_ADDON_MANIFEST.json', 'CUDA_ADDON_SHA256SUMS.txt'}
    assert result['archive_crc'] == result['archive_payload_sha256'] == 'passed'
