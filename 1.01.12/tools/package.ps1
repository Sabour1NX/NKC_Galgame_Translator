# SPDX-License-Identifier: MIT
<#
Build an offline, redistributable Windows x64 onedir release from installed tools.
Prerequisites: 64-bit Python, PyInstaller, requirements.txt, Pillow, compiled
native DLLs, vendor/ocr tesserocr wheel and models/tessdata eng+jpn models.
This script never installs packages, downloads files, requests elevation, or
copies private configuration, caches, screenshots, reports, or game assets.

Usage: powershell -NoProfile -File .\tools\package.ps1 -Python python
       Add -SkipBuild to refresh public files, licenses and archives after a
       successful EXE build. It does not refresh embedded Python application code.
Outputs: dist/NKC_Galgame_Translator/ and dist/NKC_Galgame_Translator-major.xx.xx-windows-x64.zip
         dist/NKC_Galgame_Translator-major.xx.xx-source.zip
#>
[CmdletBinding()]
param([string]$Python = '', [switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not $Python) {
    $localPython = Join-Path $projectRoot 'vendor\python\python.exe'
    $Python = if (Test-Path -LiteralPath $localPython) { $localPython } else { (Get-Command python.exe -ErrorAction Stop).Source }
}
$version = Split-Path -Leaf $projectRoot
if ($version -notmatch '^\d+\.\d{2}\.\d{2}$') { throw 'Project folder must follow major.xx.xx version naming.' }
$distRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot 'dist'))
$workRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot 'build\package'))
$releaseRoot = [IO.Path]::GetFullPath((Join-Path $distRoot 'NKC_Galgame_Translator'))
# PyInstaller --noconfirm may replace its output folders. Resolve and validate
# every output root before invoking it; no computed path may escape this version.
foreach ($outputPath in @($distRoot, $workRoot, $releaseRoot)) {
    if (-not $outputPath.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Packaging output escaped the version directory.'
    }
    $cursor = $outputPath
    while ($cursor -and $cursor.Length -ge $projectRoot.Length) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Refusing packaging through reparse point: $cursor" }
        }
        $cursor = Split-Path -Parent $cursor
    }
}

$requiredFiles = @('main.py', 'config\example.json', 'native\bin\nkc_galgame_translator_core.dll',
    'tools\ocr_helper.py', 'assets\taiji.ico', 'assets\taiji.png', 'assets\taiji.svg',
    'models\tessdata\eng.traineddata', 'models\tessdata\jpn.traineddata', 'models\tessdata\LICENSE')
foreach ($relative in $requiredFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $relative) -PathType Leaf)) { throw "Missing prerequisite: $relative" }
}
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'vendor\ocr\tesserocr') -PathType Container)) {
    throw 'Missing official tesserocr Windows x64 wheel in vendor/ocr.'
}
$preflight = @'
import hashlib, importlib.util, importlib.metadata as metadata, json, pathlib, struct, sys
root = pathlib.Path(sys.argv[1])
if sys.platform != 'win32' or struct.calcsize('P') != 8:
    raise SystemExit('Packaging requires Windows x64 Python.')
if sys.version_info[:3] != (3,14,10):
    raise SystemExit('This release is locked/tested on official CPython 3.14.10 x64. Use the documented isolated build runtime.')
for name in ('PyInstaller', 'httpx', 'PIL', 'tkinter'):
    if importlib.util.find_spec(name) is None:
        raise SystemExit(f'Missing build dependency: {name}; install it separately before packaging.')
example = json.loads((root / 'config/example.json').read_text(encoding='utf-8-sig'))
if example.get('api_key') not in ('', 'YOUR_API_KEY', None):
    raise SystemExit('config/example.json contains a private key; packaging refused.')
sys.path.insert(0, str(root / 'vendor/ocr'))
import tesserocr
inputs = json.loads((root/'docs/DEPENDENCY_MANIFEST.json').read_text(encoding='utf-8'))
names = set(inputs['groups']['runtime'] + inputs['groups']['build'] + inputs['groups']['ocr'])
from packaging.utils import canonicalize_name
for item in inputs['packages']:
    if canonicalize_name(item['name']) in names and metadata.version(item['name']) != item['version']:
        raise SystemExit(f'Build dependency does not match lock: {item["name"]}')
for item in inputs['ocr_models']:
    if hashlib.sha256((root/item['file']).read_bytes()).hexdigest() != item['sha256']:
        raise SystemExit('OCR model hash does not match release manifest.')
print(f'Build interpreter: Python {sys.version.split()[0]}, x64; tesserocr {tesserocr.__version__}')
'@
$preflight | & $Python - $projectRoot
if ($LASTEXITCODE -ne 0) { throw 'Packaging prerequisites failed.' }
New-Item -ItemType Directory -Force -Path $distRoot,$workRoot,(Join-Path $workRoot 'spec-main'),(Join-Path $workRoot 'spec-helper') | Out-Null
if ($SkipBuild) {
    foreach ($executable in @('NKC_Galgame_Translator.exe','tools\ocr_helper\ocr_helper.exe')) {
        if (-not (Test-Path -LiteralPath (Join-Path $releaseRoot $executable) -PathType Leaf)) {
            throw "-SkipBuild requires an existing complete EXE build: $executable"
        }
    }
}

# Explicit allowlists: do not add the entire project directory as data.
if (-not $SkipBuild) {
$mainArgs = @('-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed',
    '--name','NKC_Galgame_Translator','--distpath',$distRoot,'--workpath',(Join-Path $workRoot 'main'),
    '--specpath',(Join-Path $workRoot 'spec-main'),'--paths',$projectRoot,
    '--icon',(Join-Path $projectRoot 'assets\taiji.ico'),
    '--add-data',((Join-Path $projectRoot 'config\example.json') + ';config'),
    '--add-data',((Join-Path $projectRoot 'assets\taiji.ico') + ';assets'),
    '--add-data',((Join-Path $projectRoot 'nkc_galgame_translator\resources') + ';nkc_galgame_translator/resources'),
    '--add-binary',((Join-Path $projectRoot 'native\bin\nkc_galgame_translator_core.dll') + ';native/bin'),
    '--hidden-import','PIL.Image','--hidden-import','PIL.BmpImagePlugin')
# Keep unrelated packages from a development/Anaconda environment out of the GUI.
foreach ($module in @('tesserocr','PyQt5','PyQt6','PySide2','PySide6','numpy','scipy','pandas','matplotlib','torch','IPython','pytest')) {
    $mainArgs += @('--exclude-module',$module)
}
$mainArgs += (Join-Path $projectRoot 'main.py')
Push-Location -LiteralPath $projectRoot
try {
    & $Python @mainArgs
    if ($LASTEXITCODE -ne 0) { throw 'NKC_Galgame_Translator PyInstaller build failed.' }

    # The MIT image/JSON helper runs as its own process and owns its Apache-2.0
    # Tesseract dependencies. The main application calls it over a pipe.
    $helperDist = Join-Path $releaseRoot 'tools'
    $helperArgs = @('-m','PyInstaller','--noconfirm','--clean','--onedir','--console',
        '--name','ocr_helper','--distpath',$helperDist,'--workpath',(Join-Path $workRoot 'helper'),
        '--specpath',(Join-Path $workRoot 'spec-helper'),
        '--paths',(Join-Path $projectRoot 'vendor\ocr'),
        '--collect-all','tesserocr','--hidden-import','PIL.Image','--hidden-import','PIL.BmpImagePlugin')
    $wheelLibs = Join-Path $projectRoot 'vendor\ocr\tesserocr.libs'
    if (Test-Path -LiteralPath $wheelLibs) {
        $helperArgs += @('--add-data',($wheelLibs + ';tesserocr.libs'))
        foreach ($dependency in Get-ChildItem -LiteralPath $wheelLibs -Filter '*.dll' -File) {
            $helperArgs += @('--add-binary',($dependency.FullName + ';tesserocr.libs'))
        }
    }
    foreach ($module in @('PyQt5','PyQt6','PySide2','PySide6','numpy','scipy','pandas','matplotlib','torch','IPython','pytest')) {
        $helperArgs += @('--exclude-module',$module)
    }
    $helperArgs += (Join-Path $projectRoot 'tools\ocr_helper.py')
    & $Python @helperArgs
    if ($LASTEXITCODE -ne 0) { throw 'Independent OCR helper PyInstaller build failed.' }
} finally { Pop-Location }
}

$screenRoot = Join-Path $releaseRoot 'docs/screenshots'
New-Item -ItemType Directory -Force -Path $screenRoot | Out-Null
foreach ($image in @('setup-en.png','chart-en.png','api-en.png','game-en.png')) {
    Copy-Item -LiteralPath (Join-Path $projectRoot ("docs/screenshots/" + $image)) -Destination $screenRoot -Force
}

# User-editable/runtime data is beside the EXE, not inside PyInstaller _internal.
$publicCopies = @(
    @('config\example.json','config\example.json'),
    @('assets\taiji.ico','assets\taiji.ico'),
    @('assets\taiji.png','assets\taiji.png'),
    @('assets\taiji.svg','assets\taiji.svg'),
    @('assets\fonts\SourceHanSansSC-Regular.otf','assets\fonts\SourceHanSansSC-Regular.otf'),
    @('assets\fonts\SourceHanSansSC-Medium.otf','assets\fonts\SourceHanSansSC-Medium.otf'),
    @('assets\fonts\OFL.txt','assets\fonts\OFL.txt'),
    @('native\bin\nkc_galgame_translator_core.dll','native\bin\nkc_galgame_translator_core.dll'),
    @('models\tessdata\eng.traineddata','models\tessdata\eng.traineddata'),
    @('models\tessdata\jpn.traineddata','models\tessdata\jpn.traineddata'),
    @('models\tessdata\LICENSE','models\tessdata\LICENSE'),
    @('docs\ARCHITECTURE.md','docs\ARCHITECTURE.md'),
    @('tools\ocr_helper.py','tools\ocr_helper.py'),
    @('tools\cuda_ocr_helper.py','tools\cuda_ocr_helper.py'),
    @('tools\setup_cuda_ocr.py','tools\setup_cuda_ocr.py'),
    @('requirements-cuda.lock','requirements-cuda.lock'),
    @('CUDA_DEPENDENCY_MANIFEST.json','CUDA_DEPENDENCY_MANIFEST.json'),
    @('models\cuda\manifest.json','models\cuda\manifest.json'),
    @('models\cuda\LICENSE','models\cuda\LICENSE'))
foreach ($pair in $publicCopies) {
    $destination = Join-Path $releaseRoot $pair[1]
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
    Copy-Item -LiteralPath (Join-Path $projectRoot $pair[0]) -Destination $destination -Force
}
foreach ($doc in @('README.md','README.zh-CN.md','README.ja.md','Preview-Setup.cmd','Preview-Setup.ps1','LICENSE','COPYING','THIRD_PARTY_NOTICES.md','CHANGELOG.md')) {
    $source = Join-Path $projectRoot $doc
    if (Test-Path -LiteralPath $source -PathType Leaf) { Copy-Item -LiteralPath $source -Destination (Join-Path $releaseRoot $doc) -Force }
}
New-Item -ItemType Directory -Force -Path (Join-Path $releaseRoot 'docs') | Out-Null
Get-ChildItem -LiteralPath (Join-Path $projectRoot 'docs') -File | Where-Object {
    $_.Extension -in '.md','.html','.svg','.json','.css','.js'
} | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $releaseRoot ('docs\' + $_.Name)) -Force
}
if (Test-Path -LiteralPath (Join-Path $projectRoot 'docs\en')) {
    $englishDocs = Join-Path $releaseRoot 'docs\en'
    New-Item -ItemType Directory -Force -Path $englishDocs | Out-Null
    Get-ChildItem -LiteralPath (Join-Path $projectRoot 'docs\en') -File | Where-Object {
        $_.Extension -in '.md','.html','.svg','.json','.css','.js'
    } | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $englishDocs -Force }
}
if (Test-Path -LiteralPath (Join-Path $projectRoot 'docs\examples')) {
    $examplesDest = Join-Path $releaseRoot 'docs\examples'
    New-Item -ItemType Directory -Force -Path $examplesDest | Out-Null
    Get-ChildItem -LiteralPath (Join-Path $projectRoot 'docs\examples') -File | Where-Object {
        $_.Extension -in '.csv','.tsv','.json','.tmx','.txt','.md'
    } | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $examplesDest -Force }
}

# License collection, source allowlist and archives run without any network access.
$finalize = @'
import hashlib, importlib.metadata as metadata, json, pathlib, re, shutil, sys, zipfile
from packaging.requirements import Requirement
root, release, version = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
licenses = release / 'licenses'
licenses.mkdir(exist_ok=True)
mit = root / 'LICENSE'
if not mit.is_file() or mit.read_bytes() != (root/'nkc_galgame_translator/resources/license.mit.txt').read_bytes():
    raise SystemExit('Project LICENSE and the bundled agreement license differ.')
shutil.copy2(mit, licenses / 'MIT.txt')

sys.path.insert(0, str(root / 'vendor/ocr'))
requested = ['httpx', 'Pillow', 'tesserocr', 'PyInstaller']
pending, seen, manifest = list(requested), set(), []
license_pattern = re.compile(r'(^|[/\\])(licen[cs]e[^/\\]*|copying[^/\\]*|notice[^/\\]*|copyright[^/\\]*|authors[^/\\]*)$', re.I)
while pending:
    name = pending.pop()
    normalized = re.sub(r'[-_.]+', '-', name).lower()
    if normalized in seen:
        continue
    seen.add(normalized)
    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        raise SystemExit(f'Unable to collect license metadata for required distribution: {name}')
    component = licenses / (normalized + '-' + dist.version)
    component.mkdir(exist_ok=True)
    copied = []
    for item in dist.files or []:
        # Wheel authors may use names such as getopt_LICENSE.txt. Preserve
        # every RECORD entry in the standard dist-info/licenses tree, not only
        # files whose basename starts with LICENSE/COPYING.
        record_path = str(item).replace('\\', '/')
        if license_pattern.search(record_path) or re.search(r'\.dist-info/licenses/', record_path, re.I):
            path = pathlib.Path(dist.locate_file(item))
            if path.is_file():
                relative = pathlib.Path(str(item))
                safe_parts = [part for part in relative.parts if part not in ('.','..')]
                destination = component.joinpath(*safe_parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
                copied.append(destination.relative_to(release).as_posix())
    meta = dist.metadata
    record = {'name':meta.get('Name',name),'version':dist.version,
              'license':meta.get('License-Expression') or meta.get('License') or 'See bundled license notices',
              'home_page':meta.get('Home-page',''),'project_urls':meta.get_all('Project-URL') or [],
              'license_files':copied,
              'scope':'independent OCR helper' if normalized == 'tesserocr' else 'runtime/build dependency'}
    # Metadata preserves attribution even for a package with no separate LICENSE file.
    # Preserve raw metadata. str(email.message.Message) may reparse multiline
    # Description headers and fail with HeaderParseError in valid old wheels.
    raw_metadata = dist.read_text('METADATA') or dist.read_text('PKG-INFO')
    if raw_metadata is None:
        raw_metadata = json.dumps(dict(meta.items()), ensure_ascii=False, indent=2)
    (component / 'METADATA.txt').write_text(raw_metadata, encoding='utf-8')
    manifest.append(record)
    for requirement in dist.requires or []:
        req = Requirement(requirement)
        if req.marker is None or req.marker.evaluate({'extra':''}):
            pending.append(req.name)

# CPython and Tcl/Tk notices are outside wheel metadata in official/Conda installs.
runtime_candidates = [pathlib.Path(sys.base_prefix) / 'LICENSE.txt',
    pathlib.Path(sys.base_prefix) / 'LICENSE_PYTHON.txt',
    pathlib.Path(sys.base_prefix) / 'tcl/tcl8.6/license.terms',
    pathlib.Path(sys.base_prefix) / 'tcl/tk8.6/license.terms',
    pathlib.Path(sys.base_prefix) / 'Library/lib/tcl8.6/license.terms',
    pathlib.Path(sys.base_prefix) / 'Library/lib/tk8.6/license.terms']
runtime = licenses / 'python-tcl-tk'
runtime.mkdir(exist_ok=True)
for index, path in enumerate(runtime_candidates):
    if path.is_file():
        shutil.copy2(path, runtime / f'{index}-{path.parent.name}-{path.name}')
notices = root/'vendor/runtime-notices'
if not (notices/'provenance.json').is_file():
    raise SystemExit('Verified runtime notices/provenance are required for public release.')
shutil.copytree(notices, licenses/'runtime-upstream', dirs_exist_ok=True)
third_party_sources = root/'third_party_sources'
if not third_party_sources.is_dir():
    raise SystemExit('Corresponding third-party source/recipes required; see THIRD_PARTY_NOTICES.md.')
shutil.copytree(third_party_sources, release/'third_party_sources', dirs_exist_ok=True)
shutil.copy2(root / 'models/tessdata/LICENSE', licenses / 'tessdata-Apache-2.0.txt')
(licenses / 'components.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')

# Include complete project sources/build scripts using an explicit public allowlist.
# No wildcard copy of config/, reports/, data/, vendor/, or the workspace root.
source_root = release / 'source' / ('NKC_Galgame_Translator-' + version)
source_root.mkdir(parents=True, exist_ok=True)
allowed = []
for directory, suffixes in [('nkc_galgame_translator',{'.py'}), ('nkc_galgame_translator/resources',{'.json','.txt'}), ('native',{'.cpp','.h','.ps1','.cmake'}),
                            ('tools',{'.py','.ps1','.cjs','.json','.iss','.isl'}), ('tests',{'.py'}), ('docs',{'.md','.html','.svg','.json','.css','.js'}),
                            ('docs/examples',{'.csv','.tsv','.json','.tmx','.txt'}),
                            ('assets',{'.ico','.png','.svg','.bmp'}), ('assets/fonts',{'.otf','.txt'})]:
    base = root / directory
    for path in base.rglob('*'):
        if path.is_file() and path.suffix.lower() in suffixes and not any(
                part in {'__pycache__','bin','build','build-memory','teacher-review27'} for part in path.relative_to(base).parts):
            allowed.append(path)
for name in ('main.py','requirements.txt','requirements-runtime.lock','requirements-build.lock','requirements-ocr.lock',
             'requirements-test.lock','requirements-audit.lock','requirements-docs.lock','requirements-cuda.lock','CUDA_DEPENDENCY_MANIFEST.json','pytest.ini','Start.ps1','README.md','README.zh-CN.md','README.ja.md','Preview-Setup.cmd','Preview-Setup.ps1','CHANGELOG.md',
             'LICENSE','COPYING','THIRD_PARTY_NOTICES.md','.gitignore'):
    if (root / name).is_file():
        allowed.append(root / name)
allowed.extend(root/'docs/screenshots'/name for name in ('setup-en.png','chart-en.png','api-en.png','game-en.png'))
allowed.append(root / 'config/example.json')
allowed.extend(root / name for name in ('models/cuda/manifest.json','models/cuda/LICENSE'))
secret_pattern = re.compile(rb'sk-[A-Za-z0-9_-]{16,}')
for path in allowed:
    if secret_pattern.search(path.read_bytes()):
        raise SystemExit(f'Possible private API credential in public source {path.relative_to(root)}; packaging refused.')
    dest = source_root / path.relative_to(root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)
if not (source_root / 'LICENSE').is_file():
    shutil.copy2(mit, source_root / 'LICENSE')
shutil.copytree(third_party_sources, source_root/'third_party_sources', dirs_exist_ok=True)
shutil.copytree(notices, source_root/'vendor/runtime-notices', dirs_exist_ok=True)

notices = '''NKC_Galgame_Translator distribution notes

Resource usage shows one line per metric. Mountain ridges are optional.

NKC_Galgame_Translator application and native modules: MIT. Corresponding project
source and build scripts are in source/ and the sibling source ZIP.
tools/ocr_helper.py: independent MIT image/JSON utility. Its separate executable
contains tesserocr/Tesseract dependencies with their own notices under licenses/.
The NKC_Galgame_Translator GUI never imports tesserocr. Tessdata files retain Apache-2.0.
PyInstaller has a bootloader exception; see its included license.
Python, Tcl/Tk, Pillow and network/runtime dependencies retain their own licenses.
See licenses/components.json and the original notices for separately
distributed dependencies.

Private API keys, translation caches, screenshots and game files are excluded.
Use the first-run API settings page; without an API, browse saved archives only. API keys
are encrypted with Windows CurrentUser DPAPI in config/credentials.bin; ordinary
config/local.json contains only settings and a credential identifier.
The installed folder must be writable for config and data; do not place it in
Program Files. Run NKC_Galgame_Translator.exe. The OCR utility is invoked without a window.
'''
(release / 'DISTRIBUTION-NOTES.txt').write_text(notices, encoding='utf-8')

sys.path.insert(0,str(root/'tools'))
from release_metadata import create
create(root, release, version)

# Reject forbidden payloads even if an earlier build accidentally left them behind.
for path in release.rglob('*'):
    if path.is_file() and (path.name.lower() in {'local.json','.env','credentials.bin'} or
                          (path.name.lower().startswith('credentials') and path.suffix.lower()=='.bin') or
                          path.name.lower().startswith(('credentials.bin.', '.credentials.bin', '.local.json')) or
                          path.suffix.lower() in {'.sqlite','.sqlite3','.db'}):
        raise SystemExit(f'Private/generated file found in release: {path.relative_to(release)}')
for relative in ('NKC_Galgame_Translator.exe','tools/ocr_helper/ocr_helper.exe','native/bin/nkc_galgame_translator_core.dll',
                 'models/tessdata/eng.traineddata','models/tessdata/jpn.traineddata','assets/taiji.ico'):
    if not (release / relative).is_file():
        raise SystemExit(f'Expected release artifact missing: {relative}')

def archive_tree(folder, destination, prefix):
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                archive.write(path, str(pathlib.PurePosixPath(prefix) / path.relative_to(folder).as_posix()))

source_zip = release.parent / f'NKC_Galgame_Translator-{version}-source.zip'
archive_tree(source_root, source_zip, source_root.name)
hashes = []
for path in sorted(release.rglob('*')):
    if path.is_file() and path.name != 'SHA256SUMS.txt':
        with path.open('rb') as handle:
            digest = hashlib.file_digest(handle, 'sha256').hexdigest()
        hashes.append(digest + '  ' + path.relative_to(release).as_posix())
(release / 'SHA256SUMS.txt').write_text('\n'.join(hashes)+'\n', encoding='utf-8')
binary_zip = release.parent / f'NKC_Galgame_Translator-{version}-windows-x64.zip'
archive_tree(release, binary_zip, 'NKC_Galgame_Translator')
archive_hashes = [hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name for p in (binary_zip,source_zip)]
(release.parent/f'NKC_Galgame_Translator-{version}-SHA256SUMS.txt').write_text('\n'.join(archive_hashes)+'\n',encoding='utf-8')
print(f'Release: {release}')
print(f'Binary ZIP: {binary_zip}')
print(f'Source ZIP: {source_zip}')
print('Private config/cache/report/game files excluded; no network or installation performed.')
'@
$finalize | & $Python - $projectRoot $releaseRoot $version
if ($LASTEXITCODE -ne 0) { throw 'License/source/archive verification failed; do not distribute the output.' }
