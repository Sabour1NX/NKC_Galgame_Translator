# SPDX-License-Identifier: MIT
"""Read-only, offline verification of the final Windows release and source ZIP.

Run with vendor/python/python.exe after tools/package.ps1 has finished. The only
output written is reports/package-verification.json. Never extracts or executes
the release. An optional CycloneDX validator uses its installed, local schemas;
--require-schema makes missing optional validation dependencies a failure.
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
import stat
import sys
import zipfile


CHUNK = 1024 * 1024
MAX_FILES = 100_000
MAX_MEMBER = 1024 * 1024 * 1024
MAX_TOTAL = 5 * 1024 * 1024 * 1024
HEX256 = re.compile(r"[0-9a-f]{64}\Z")
# libssh2 contains public FIDO security-key algorithm names beginning with sk-.
# Exempt only exact OpenSSH names and the suffix of the public SPDX Asterisk
# linking-protocols exception identifier, never arbitrary shared prefixes.
PRIVATE_TOKEN = re.compile(
    rb"sk-(?!(?:ecdsa-sha2-nistp256|ssh-ed25519)(?:-cert-v01)?@openssh\.com)"
    rb"(?!linking-protocols-exception(?:[^A-Za-z0-9_-]|$))[A-Za-z0-9_-]{16,}")
# Cryptography libraries legitimately contain parser/header constants. A private
# key payload must include actual base64 material after the PEM header.
PRIVATE_KEY = re.compile(
    rb"-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----[\r\n \t]+[A-Za-z0-9+/]{32,}")
TEXT_SUFFIXES = {'.iss', '.py', '.ps1', '.cpp', '.h', '.md', '.html', '.svg', '.json',
                 '.txt', '.csv', '.tsv', '.tmx', '.yaml', '.yml', '.toml', '.lock'}
LOCK_GROUPS = ('runtime', 'build', 'ocr', 'test', 'audit', 'docs')
SOURCE_SUFFIXES = {
    'nkc_galgame_translator': {'.py'}, 'nkc_galgame_translator/resources': {'.json', '.txt'}, 'native': {'.cpp', '.h', '.ps1', '.cmake'},
    'tools': {'.py', '.ps1', '.cjs', '.json', '.iss', '.isl'}, 'tests': {'.py'},
    'docs': {'.md', '.html', '.svg', '.json', '.css', '.js'},
    'docs/examples': {'.csv', '.tsv', '.json', '.tmx', '.txt'},
    'assets': {'.ico', '.png', '.svg', '.bmp'}, 'assets/fonts': {'.otf', '.txt'},
}
SOURCE_FILES = {
    'main.py', 'requirements.txt', 'pytest.ini', 'Start.ps1', 'README.md', 'README.zh-CN.md', 'README.ja.md', 'Preview-Setup.cmd', 'Preview-Setup.ps1',
    *('docs/screenshots/' + name for name in ('setup-en.png','chart-en.png','api-en.png','game-en.png')),
    'CHANGELOG.md', 'LICENSE', 'COPYING', 'THIRD_PARTY_NOTICES.md', '.gitignore',
    'config/example.json', *(f'requirements-{group}.lock' for group in LOCK_GROUPS),
    'requirements-cuda.lock', 'CUDA_DEPENDENCY_MANIFEST.json',
    'models/cuda/manifest.json', 'models/cuda/LICENSE',
}
REQUIRED_SOURCE = {
    'nkc_galgame_translator/profile_ui.py', 'nkc_galgame_translator/scrolling.py', 'nkc_galgame_translator/hotkeys.py', 'nkc_galgame_translator/profile_store.py',
    'nkc_galgame_translator/cuda_ocr.py', 'tools/cuda_ocr_helper.py', 'tools/setup_cuda_ocr.py', 'tools/package_cuda.py',
    'requirements-cuda.lock', 'CUDA_DEPENDENCY_MANIFEST.json', 'models/cuda/manifest.json', 'models/cuda/LICENSE',
    'nkc_galgame_translator/vision.py', 'nkc_galgame_translator/vision_core.py', 'nkc_galgame_translator/game_identity.py',
    'nkc_galgame_translator/i18n.py', 'nkc_galgame_translator/language_setup.py', 'nkc_galgame_translator/ui_catalog.py',
    'nkc_galgame_translator/agreement_en.py', 'nkc_galgame_translator/agreement_ja.py',
    'nkc_galgame_translator/resources/license.mit.txt', 'nkc_galgame_translator/resource_usage.py',
    'docs/PROJECT_MANUAL.en.html', 'docs/PROJECT_MANUAL.ja.html', 'docs/USER_AGREEMENT.en.md',
    'main.py', 'tools/package.ps1', 'tools/verify_release.py', 'tools/installer.py', 'tools/build_installer.ps1',
    'tools/install_strings.json', 'nkc_galgame_translator/resources/ui_catalog.json',
    'assets/fonts/SourceHanSansSC-Regular.otf', 'assets/fonts/SourceHanSansSC-Medium.otf', 'assets/fonts/OFL.txt',
    'docs/Greeting_cn.html', 'docs/Greeting.en.html', 'docs/Greeting.ja.html',
    'native/core.cpp', 'native/core.h', 'config/example.json',
    'LICENSE', 'THIRD_PARTY_NOTICES.md',
    'docs/PROJECT_MANUAL.html', 'docs/RELEASE.md', 'docs/TEST_REPORT.json',
    'docs/DEPENDENCY_MANIFEST.json', 'docs/INPUT_INTERFACES.md',
    'vendor/runtime-notices/provenance.json',
    'third_party_sources/libiconv-1.18/libiconv-1.18.tar.gz',
    'third_party_sources/libiconv-1.18/COPYING.LIB',
    'third_party_sources/libiconv-1.18/info/recipe/parent/CMakeLists.txt.patch',
    'third_party_sources/libiconv-1.18/info/recipe/parent/config.h.patch',
    'third_party_sources/libiconv-1.18/info/recipe/parent/configure.cmake.patch',
    'third_party_sources/certifi-2026.10.23/certifi-2026.10.23.tar.gz',
    'third_party_sources/certifi-2026.10.23/MPL-2.0.txt',
    *(f'requirements-{group}.lock' for group in LOCK_GROUPS),
}
REQUIRED_RELEASE = {
    'tools/cuda_ocr_helper.py', 'tools/setup_cuda_ocr.py', 'tools/ocr_helper.py',
    'requirements-cuda.lock', 'CUDA_DEPENDENCY_MANIFEST.json', 'models/cuda/manifest.json', 'models/cuda/LICENSE',
    'docs/USER_AGREEMENT.ja.md',
    'docs/PROJECT_MANUAL.en.html', 'docs/PROJECT_MANUAL.ja.html', 'docs/USER_AGREEMENT.en.md',
    'NKC_Galgame_Translator.exe', 'tools/ocr_helper/ocr_helper.exe',
    'native/bin/nkc_galgame_translator_core.dll', 'assets/taiji.ico',
    'models/tessdata/eng.traineddata', 'models/tessdata/jpn.traineddata',
    'docs/PROJECT_MANUAL.html', 'docs/RELEASE.md', 'docs/TEST_REPORT.json',
    'docs/DEPENDENCY_MANIFEST.json', 'docs/NATIVE_HARDENING.json',
    'LICENSE', 'THIRD_PARTY_NOTICES.md', 'SHA256SUMS.txt',
    'SBOM.cdx.json', 'RELEASE_METADATA.json', 'DEPENDENCY_AUDIT.json',
    'licenses/components.json', 'licenses/MIT.txt',
    '_internal/nkc_galgame_translator/resources/license.mit.txt',
    'licenses/tessdata-Apache-2.0.txt', 'licenses/runtime-upstream/provenance.json',
}


class VerificationError(Exception):
    """Only fixed codes and public relative paths may be reported."""

    def __init__(self, code: str, path: str | None = None):
        self.code, self.path = code, path
        super().__init__(code)


def require(value: object, code: str, path: str | None = None) -> None:
    if not value:
        raise VerificationError(code, path)


def relative_name(value: str) -> str:
    """Reject aliases/traversal on Windows without accessing the filesystem."""
    require(isinstance(value, str) and bool(value), 'invalid_relative_path')
    require(not any(ord(c) < 32 for c in value), 'control_character_in_path')
    require(not any(c in value for c in '\\:*?"<>|'), 'unsafe_windows_path')
    parts = value.split('/')
    require(all(p and p not in {'.', '..'} and not p.endswith((' ', '.'))
                for p in parts), 'noncanonical_relative_path')
    reserved = {'con', 'prn', 'aux', 'nul', 'conin$', 'conout$',
                *(f'com{n}' for n in '123456789¹²³'),
                *(f'lpt{n}' for n in '123456789¹²³')}
    require(not any(p.split('.')[0].casefold() in reserved for p in parts),
            'reserved_windows_path')
    return value


def reject_private_name(name: str) -> None:
    parts = name.casefold().split('/')
    base = parts[-1]
    require(not any(p in {'reports', '.git', '.pytest_cache', '__pycache__'}
                    for p in parts), 'private_or_generated_directory', name)
    require(base not in {'local.json', 'credentials.bin', '.env'} and
            not base.startswith(('local.json.', '.local.json', 'credentials.bin.',
                                 '.credentials.bin', '.env.')) and
            not (base.startswith('credentials') and base.endswith('.bin')) and
            not base.endswith(('.sqlite', '.sqlite3', '.db', '.db-wal', '.db-shm',
                               '.sqlite-wal', '.sqlite-shm', '.sqlite3-wal', '.sqlite3-shm')),
            'private_payload_name', name)


def digest_file(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def tree_files(base: Path) -> dict[str, Path]:
    require(base.is_dir(), 'missing_release_directory')
    found: dict[str, Path] = {}
    folded: set[str] = set()
    for folder, dirs, files in os.walk(base, followlinks=False):
        for name in dirs + files:
            path = Path(folder) / name
            info = path.lstat()
            rel = relative_name(path.relative_to(base).as_posix())
            require(not stat.S_ISLNK(info.st_mode) and
                    not (getattr(info, 'st_file_attributes', 0) & 0x400),
                    'release_reparse_point', rel)
            require(rel.casefold() not in folded, 'case_alias_in_release', rel)
            folded.add(rel.casefold())
            if name in files:
                require(stat.S_ISREG(info.st_mode), 'nonregular_release_file', rel)
                reject_private_name(rel)
                require(info.st_size <= MAX_MEMBER, 'file_too_large', rel)
                found[rel] = path
    require(len(found) <= MAX_FILES, 'too_many_release_files')
    require(sum(p.stat().st_size for p in found.values()) <= MAX_TOTAL,
            'release_too_large')
    return found


def parse_sums(path: Path) -> dict[str, str]:
    require(path.is_file(), 'missing_hash_manifest', path.name)
    result: dict[str, str] = {}
    folded: set[str] = set()
    for line in path.read_text(encoding='utf-8').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)
        require(match is not None, 'invalid_hash_manifest_line', path.name)
        checksum, name = match.groups()
        relative_name(name)
        require(name.casefold() not in folded, 'duplicate_hash_manifest_path', name)
        folded.add(name.casefold())
        result[name] = checksum
    require(bool(result), 'empty_hash_manifest', path.name)
    return result


def zip_hashes(path: Path, prefix: str) -> dict[str, str]:
    """Hash every decompressed member; ZipExtFile checks CRC on complete reads."""
    require(path.is_file(), 'missing_release_archive', path.name)
    result: dict[str, str] = {}
    folded: set[str] = set()
    total = 0
    with zipfile.ZipFile(path) as archive:
        require(len(archive.infolist()) <= MAX_FILES, 'too_many_zip_members', path.name)
        for entry in archive.infolist():
            name = relative_name(entry.filename.rstrip('/') if entry.is_dir() else entry.filename)
            require(name == prefix or name.startswith(prefix + '/'),
                    'unexpected_zip_prefix', path.name)
            require(name.casefold() not in folded, 'case_duplicate_zip_member', path.name)
            folded.add(name.casefold())
            mode = (entry.external_attr >> 16) & 0xFFFF
            kind = stat.S_IFMT(mode)
            require(kind in (0, stat.S_IFDIR if entry.is_dir() else stat.S_IFREG),
                    'nonregular_zip_member', path.name)
            require(not entry.flag_bits & 1, 'encrypted_zip_member', path.name)
            if entry.is_dir():
                continue
            require(name != prefix, 'file_at_zip_root', path.name)
            rel = name[len(prefix) + 1:]
            reject_private_name(rel)
            total += entry.file_size
            require(entry.file_size <= MAX_MEMBER and total <= MAX_TOTAL,
                    'zip_size_limit', path.name)
            hasher = hashlib.sha256()
            with archive.open(entry) as stream:
                while data := stream.read(CHUNK):
                    hasher.update(data)
            result[rel] = hasher.hexdigest()
    require(bool(result), 'empty_release_archive', path.name)
    # A file cannot also be a parent directory, even if one side was implicit.
    all_files = {name.casefold() for name in result}
    for name in result:
        parts = name.casefold().split('/')
        require(not any('/'.join(parts[:i]) in all_files for i in range(1, len(parts))),
                'zip_file_directory_collision', path.name)
    return result


def same_hashes(actual: dict[str, str], expected: dict[str, str], code: str) -> None:
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    require(not missing, code + '_missing', missing[0] if missing else None)
    require(not extra, code + '_extra', extra[0] if extra else None)
    for name, checksum in expected.items():
        require(actual[name] == checksum, code + '_hash_mismatch', name)


def json_file(path: Path):
    # Report no JSON text or arbitrary exception strings, which may contain keys.
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate_json_key', path.name)
            result[key] = value
        return result
    require(path.stat().st_size <= 16 * CHUNK, 'oversized_json', path.name)
    return json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=object_pairs)


def source_inventory(root: Path) -> dict[str, str]:
    paths = {root / name for name in SOURCE_FILES if (root / name).is_file()}
    for folder, suffixes in SOURCE_SUFFIXES.items():
        base = root / folder
        for path in base.rglob('*'):
            if path.is_file() and path.suffix.lower() in suffixes and not any(
                    p in {'__pycache__', 'bin', 'build', 'build-memory', 'teacher-review27'}
                    for p in path.relative_to(base).parts):
                paths.add(path)
    for folder in ('third_party_sources', 'vendor/runtime-notices'):
        for path in tree_files(root / folder).values():
            paths.add(path)
    return {path.relative_to(root).as_posix(): digest_file(path) for path in sorted(paths)}


def scan_payload(files: dict[str, Path], root: Path) -> dict:
    scanned = text_count = 0
    # Only look for this build's private path, not arbitrary example Windows paths.
    private_roots = {str(root), str(root).replace('\\', '/'), str(root).replace('\\', '\\\\')}
    markers = [value.encode('utf-8').lower() for value in private_roots]
    for name, path in files.items():
        tail = b''
        text_file = path.suffix.lower() in TEXT_SUFFIXES
        with path.open('rb') as stream:
            while block := stream.read(CHUNK):
                data = tail + block
                require(not PRIVATE_TOKEN.search(data), 'possible_api_key', name)
                require(not PRIVATE_KEY.search(data), 'possible_private_key', name)
                if text_file:
                    require(not any(marker in data.lower() for marker in markers),
                            'private_workspace_path', name)
                tail = data[-4096:]
        scanned += 1
        text_count += text_file
    for name, path in files.items():
        if name.endswith('/config/example.json') or name == 'config/example.json':
            config = json_file(path)
            require(config.get('api_key') in ('', 'YOUR_API_KEY', None),
                    'credential_in_example_config', name)
            require(not config.get('credential_id'), 'credential_id_in_example_config', name)
    return {'files_scanned': scanned, 'text_files_checked_for_private_build_path': text_count,
            'checks': ['private file/directory names', 'API-key-shaped tokens',
                       'PEM private keys', 'private workspace path in text', 'example config'],
            'limit': 'Heuristic content scanning cannot prove absence of every possible secret.'}


def canonical_package(name: str) -> str:
    return re.sub(r'[-_.]+', '-', name).lower()


def verify_dependencies(root: Path, release: Path, source_prefix: str) -> dict:
    manifest = json_file(release / 'docs/DEPENDENCY_MANIFEST.json')
    packages = {canonical_package(item['name']): item for item in manifest['packages']}
    count = 0
    for group in LOCK_GROUPS:
        filename = f'requirements-{group}.lock'
        path = release / source_prefix / filename
        parsed = {}
        for line in path.read_text(encoding='utf-8').splitlines():
            if not line.strip() or line.startswith('#'):
                continue
            match = re.fullmatch(r'([A-Za-z0-9_.-]+)==([^\s]+) --hash=sha256:([0-9a-f]{64})', line)
            require(match is not None, 'invalid_or_unpinned_lock', filename)
            name, version, checksum = match.groups()
            name = canonical_package(name)
            require(name not in parsed, 'duplicate_locked_package', filename)
            require(name in packages and version == packages[name]['version'] and
                    checksum == packages[name]['sha256'], 'lock_manifest_disagreement', filename)
            parsed[name] = checksum
            count += 1
        require(set(parsed) == set(manifest['groups'][group]), 'lock_group_disagreement', filename)
    for model in manifest['ocr_models']:
        name = relative_name(model['file'])
        require(digest_file(release / name) == model['sha256'], 'ocr_model_hash_mismatch', name)
    return {'lockfiles': len(LOCK_GROUPS), 'pinned_entries': count,
            'ocr_models': len(manifest['ocr_models'])}


def verify_notices(release: Path, files: dict[str, Path], hashes: dict[str, str]) -> dict:
    base = release / 'licenses/runtime-upstream'
    provenance = json_file(base / 'provenance.json')
    for record in provenance['records']:
        name = relative_name(record['file'])
        path = base / name
        require(digest_file(path) == record['sha256'] and path.stat().st_size == record['bytes'],
                'runtime_notice_provenance_mismatch', name)
    audit = json_file(base / 'ocr-bundled-license-audit.json')
    for dll in audit['dlls']:
        name = relative_name(dll['dll'])
        matches = [key for key in files if key.startswith('tools/ocr_helper/') and
                   key.endswith('/tesserocr.libs/' + name)]
        require(bool(matches), 'missing_bundled_ocr_dll', name)
        require(all(hashes[key] == dll['sha256'] for key in matches),
                'ocr_dll_provenance_mismatch', name)
        for notice in dll['notices']:
            suffix = '/licenses/' + relative_name(notice['path'])
            matches = [key for key in files if key.startswith('licenses/tesserocr-') and key.endswith(suffix)]
            require(bool(matches) and all(hashes[key] == notice['sha256'] for key in matches),
                    'ocr_dll_license_missing_or_changed', name)
    sources = release / 'third_party_sources'
    count = 0
    for path in sorted(sources.glob('*/provenance.json')):
        record = json_file(path)
        source_name = record.get('source_filename') or record['source_url'].rsplit('/', 1)[-1]
        source_name = relative_name(source_name)
        source_path = path.parent / source_name
        checksum = record.get('source_sha256') or record['sha256']
        size = record.get('source_bytes') or record['bytes']
        require(digest_file(source_path) == checksum and source_path.stat().st_size == size,
                'third_party_source_hash_mismatch', source_name)
        for additional in record.get('additional_original_files', []):
            name = relative_name(additional['file'])
            require(digest_file(path.parent / name) == additional['sha256'],
                    'third_party_original_file_changed', name)
        count += 1
    require(count >= 2, 'missing_third_party_source_provenance')
    return {'runtime_notice_records': len(provenance['records']),
            'ocr_dll_license_mappings': len(audit['dlls']), 'corresponding_source_archives': count}


def verify_sbom(release: Path, hashes: dict[str, str], require_schema: bool) -> dict:
    sbom_path = release / 'SBOM.cdx.json'
    sbom = json_file(sbom_path)
    require(sbom.get('bomFormat') == 'CycloneDX' and sbom.get('specVersion') == '1.6' and
            type(sbom.get('version')) is int and sbom['version'] >= 1,
            'invalid_sbom_version')
    components = sbom.get('components')
    require(isinstance(components, list) and bool(components), 'missing_sbom_components')
    refs = {sbom['metadata']['component']['bom-ref']}
    file_hashes = {}
    for component in components:
        ref = component['bom-ref']
        require(isinstance(ref, str) and ref not in refs, 'duplicate_sbom_reference')
        refs.add(ref)
        if component['type'] == 'file':
            name = relative_name(component['name'])
            digests = [item['content'] for item in component.get('hashes', []) if item['alg'] == 'SHA-256']
            require(len(digests) == 1 and HEX256.fullmatch(digests[0]), 'invalid_sbom_file_hash', name)
            require(name in hashes and hashes[name] == digests[0], 'sbom_file_hash_mismatch', name)
            require(name not in file_hashes, 'duplicate_sbom_file', name)
            file_hashes[name] = digests[0]
    require(set(file_hashes) == {name for name in hashes if name.lower().endswith('.dll')},
            'sbom_dll_inventory_incomplete')
    for dependency in sbom['dependencies']:
        require(dependency['ref'] in refs and all(ref in refs for ref in dependency.get('dependsOn', [])),
                'unresolved_sbom_dependency')
    manifest = json_file(release / 'docs/DEPENDENCY_MANIFEST.json')
    expected_packages = {canonical_package(item['name']): item for item in manifest['packages']}
    wanted = set().union(*(manifest['groups'][group] for group in ('runtime', 'build', 'ocr')))
    seen_packages = set()
    for component in components:
        if component.get('type') != 'library':
            continue
        name = canonical_package(component['name'])
        require(name in wanted and name not in seen_packages, 'unexpected_sbom_package')
        expected = expected_packages[name]
        require(component['version'] == expected['version'], 'sbom_package_version_mismatch')
        downloads = [item for item in component.get('externalReferences', []) if item['type'] == 'distribution']
        require(len(downloads) == 1 and downloads[0]['url'] == expected['url'] and
                {'alg': 'SHA-256', 'content': expected['sha256']} in downloads[0].get('hashes', []),
                'sbom_package_distribution_mismatch')
        seen_packages.add(name)
    require(seen_packages == wanted, 'sbom_package_inventory_incomplete')
    status = {'components': len(components), 'verified_dll_hashes': len(file_hashes),
              'structure_and_references': 'passed', 'official_schema': 'not_available'}
    try:
        from cyclonedx.exception import MissingOptionalDependencyException
        from cyclonedx.schema import SchemaVersion
        from cyclonedx.validation.json import JsonStrictValidator
        validator = JsonStrictValidator(SchemaVersion.V1_6)
        error = validator.validate_str(sbom_path.read_text(encoding='utf-8'))
        require(error is None, 'cyclonedx_1_6_schema_invalid')
        status['official_schema'] = 'passed'
        status['validator'] = 'cyclonedx-python-lib ' + importlib.metadata.version('cyclonedx-python-lib')
        status['schema_source'] = 'installed CycloneDX 1.6 schema; local reference registry; no network'
    except ImportError:
        status['schema_unavailable_reason'] = 'CycloneDX optional JSON validation dependencies not installed'
    except Exception as exc:
        if 'MissingOptionalDependencyException' in locals() and isinstance(exc, MissingOptionalDependencyException):
            status['schema_unavailable_reason'] = 'CycloneDX optional JSON validation dependencies not installed'
        else:
            raise
    require(not require_schema or status['official_schema'] == 'passed', 'required_schema_validator_unavailable')
    return status


def verify_embedded_modules(release: Path) -> dict:
    from PyInstaller.archive.readers import CArchiveReader
    archive = CArchiveReader(str(release / 'NKC_Galgame_Translator.exe'))
    pyz_names = [name for name in archive.toc if name.upper().endswith('.PYZ')]
    require(len(pyz_names) == 1, 'missing_or_ambiguous_embedded_pyz')
    pyz = archive.open_embedded_archive(pyz_names[0])
    required = {'nkc_galgame_translator.app', 'nkc_galgame_translator.config_store', 'nkc_galgame_translator.security',
                'nkc_galgame_translator.input_paths', 'nkc_galgame_translator.translation', 'nkc_galgame_translator.context_archive', 'nkc_galgame_translator.ocr_regions',
                'nkc_galgame_translator.dictionary_import', 'nkc_galgame_translator.pipeline', 'nkc_galgame_translator.ocr',
                'nkc_galgame_translator.native', 'nkc_galgame_translator.settings_ui', 'nkc_galgame_translator.tracking', 'nkc_galgame_translator.ocr_quality',
                'nkc_galgame_translator.translatability','nkc_galgame_translator.selection_regions','nkc_galgame_translator.font_style',
                'nkc_galgame_translator.context_agent', 'nkc_galgame_translator.cuda_ocr',
                'nkc_galgame_translator.profile_ui', 'nkc_galgame_translator.scrolling', 'nkc_galgame_translator.hotkeys', 'nkc_galgame_translator.profile_store'}
    require(required <= set(pyz.toc), 'missing_embedded_application_modules')
    require(not any(name == 'tesserocr' or name.startswith('tesserocr.') for name in pyz.toc),
            'ocr_library_in_gui_process')
    return {'required_modules': len(required), 'present': True,
            'gui_imports_tesserocr': False, 'executed_release_code': False}


def verify(root: Path, report: dict, require_schema: bool = False) -> None:
    version = root.name
    require(re.fullmatch(r'\d+\.\d{2}\.\d{2}', version), 'invalid_version_directory')
    report['version'] = version
    release = root / 'dist/NKC_Galgame_Translator'
    files = tree_files(release)
    require(not any('teacher-review27' in name.split('/') for name in files),
            'cancelled_teacher_presentation_in_release')
    require(not any(name.startswith(('vendor/cuda/', 'vendor/python/', 'runtime/')) or
                    name.startswith('models/cuda/') and name.endswith('.onnx') for name in files),
            'optional_cuda_runtime_in_standard_release')
    require(REQUIRED_RELEASE <= set(files), 'missing_required_release_artifact',
            next(iter(sorted(REQUIRED_RELEASE - set(files))), None))
    license_text = (release / 'LICENSE').read_text(encoding='utf-8-sig')
    require(license_text.startswith('MIT License\n') and 'Copyright (c)' in license_text and
            'Permission is hereby granted' in license_text and 'THE SOFTWARE IS PROVIDED' in license_text,
            'incomplete_mit_license', 'LICENSE')
    require(all(path.read_bytes() == (release / 'LICENSE').read_bytes() for path in (
        root / 'LICENSE', release / 'licenses/MIT.txt', release / '_internal/nkc_galgame_translator/resources/license.mit.txt',
        root / 'nkc_galgame_translator/resources/license.mit.txt')),
        'project_license_mismatch', 'LICENSE')
    report['checks']['mit_license'] = {'status': 'passed', 'sha256': digest_file(root / 'LICENSE')}
    hashes = {name: digest_file(path) for name, path in files.items()}
    manifest = parse_sums(release / 'SHA256SUMS.txt')
    same_hashes({name: value for name, value in hashes.items() if name != 'SHA256SUMS.txt'},
                manifest, 'release_manifest')
    report['checks']['release_manifest'] = {'status': 'passed', 'files': len(manifest)}

    source_name = f'NKC_Galgame_Translator-{version}'
    binary_zip = root / 'dist' / f'{source_name}-windows-x64.zip'
    source_zip = root / 'dist' / f'{source_name}-source.zip'
    expected_archives = {path.name: digest_file(path) for path in (binary_zip, source_zip)}
    same_hashes(expected_archives, parse_sums(root / 'dist' / f'{source_name}-SHA256SUMS.txt'),
                'archive_manifest')
    binary_hashes = zip_hashes(binary_zip, 'NKC_Galgame_Translator')
    same_hashes(binary_hashes, hashes, 'binary_zip')
    source_hashes = zip_hashes(source_zip, source_name)
    require(REQUIRED_SOURCE <= set(source_hashes), 'missing_required_source_artifact',
            next(iter(sorted(REQUIRED_SOURCE - set(source_hashes))), None))
    same_hashes(source_hashes, source_inventory(root), 'source_workspace')
    source_prefix = 'source/' + source_name
    bundled_source = {name[len(source_prefix) + 1:]: checksum for name, checksum in hashes.items()
                      if name.startswith(source_prefix + '/')}
    same_hashes(bundled_source, source_hashes, 'bundled_source')
    # Direct documentation/source copies and the separately located notices must
    # agree with the verified source, not merely with a self-consistent manifest.
    for name, checksum in source_hashes.items():
        if name in hashes:
            require(hashes[name] == checksum, 'public_source_copy_mismatch', name)
    notice_source = {name[len('vendor/runtime-notices/'):]: checksum
                     for name, checksum in source_hashes.items()
                     if name.startswith('vendor/runtime-notices/')}
    notice_release = {name[len('licenses/runtime-upstream/'):]: checksum
                      for name, checksum in hashes.items()
                      if name.startswith('licenses/runtime-upstream/')}
    same_hashes(notice_release, notice_source, 'runtime_notice_copy')
    report['source_matches_workspace'] = True
    report['checks']['archives'] = {'status': 'passed', 'crc_all_members': True,
        'path_and_case_collisions': 'passed', 'binary_files': len(binary_hashes),
        'source_files': len(source_hashes), 'source_matches_workspace': True,
        'bundled_source_matches_source_zip': True,
        'sha256': expected_archives}
    report['checks']['private_payload_scan'] = scan_payload(files, root)
    report['private_payloads_absent'] = True
    report['checks']['dependencies'] = verify_dependencies(root, release, source_prefix)
    report['checks']['notices_and_sources'] = verify_notices(release, files, hashes)
    report['checks']['sbom'] = verify_sbom(release, hashes, require_schema)
    report['checks']['embedded_modules'] = verify_embedded_modules(release)
    report['passed'] = True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1],
                        help='Version directory; defaults to the project containing this script.')
    parser.add_argument('--require-schema', action='store_true',
                        help='Fail if optional official CycloneDX JSON validation is unavailable.')
    args = parser.parse_args()
    root = args.root.resolve()
    report = {'schema': 1, 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'passed': False, 'checks': {}, 'errors': [],
              'source_matches_workspace': False, 'private_payloads_absent': False,
              'scope': 'Offline artifact checks; no application execution or API calls',
              'limitations': ['Checksums are integrity evidence, not a publisher signature.',
                              'Verification does not certify license compatibility or absence of all vulnerabilities.']}
    try:
        verify(root, report, args.require_schema)
    except VerificationError as exc:
        error = {'code': exc.code}
        if exc.path:
            error['public_relative_path'] = exc.path
        report['errors'].append(error)
    except Exception as exc:
        # Never include exception messages/tracebacks: OS errors can expose private paths.
        report['errors'].append({'code': 'unexpected_verification_error', 'exception_type': type(exc).__name__})
    output = root / 'reports/package-verification.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'report': 'reports/package-verification.json',
                      'errors': report['errors']}, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
