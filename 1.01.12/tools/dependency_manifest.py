# SPDX-License-Identifier: MIT
"""Record exact Windows build inputs from pip --report and installed metadata.

Requires existing build/install-report.json and build/ocr-install-report.json.
Never installs dependencies, contacts a network, or reads user configuration.
"""
import importlib.metadata as metadata
import json
import hashlib
import ssl
import sqlite3
import pyexpat
import tkinter
from pathlib import Path
import sys
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]


def main():
    records = {}
    for name in ('install-report.json', 'ocr-install-report.json'):
        for item in json.loads((ROOT/'build'/name).read_text(encoding='utf-8'))['install']:
            info = item['metadata']
            records[canonicalize_name(info['name'])] = {
                'name': info['name'], 'version': info['version'],
                'url': item['download_info']['url'],
                'sha256': item['download_info']['archive_info']['hashes']['sha256'],
                'requires_dist': info.get('requires_dist', []),
                'license': info.get('license_expression') or info.get('license') or 'See bundled notices',
            }

    def closure(names):
        found = set()
        pending = list(names)
        while pending:
            name = canonicalize_name(pending.pop())
            if name in found: continue
            item = records[name]
            found.add(name)
            for spec in item['requires_dist']:
                requirement = Requirement(spec)
                if requirement.marker is None or requirement.marker.evaluate({'extra': ''}):
                    pending.append(requirement.name)
        return found

    groups = {'runtime': closure(['httpx','Pillow']),
              'build': closure(['PyInstaller']),
              'test': closure(['pytest','pywin32']),
              'audit': closure(['pip-audit']), 'docs': closure(['markdown-it-py']), 'ocr': {'tesserocr'}}
    for group, names in groups.items():
        lines = ['# Windows x64 / CPython 3.14.10; exact verified wheels.',
                 '# Install using pip --require-hashes --only-binary=:all:.']
        for name in sorted(names):
            item = records[name]
            lines.append(f'{item["name"]}=={item["version"]} --hash=sha256:{item["sha256"]}')
        (ROOT/f'requirements-{group}.lock').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    manifest = {'schema':1, 'platform':'Windows x86-64', 'python':'3.14.10',
                'python_download':'https://www.python.org/ftp/python/3.14.10/python-3.14.10-amd64.exe',
                'python_installer_sha256':'92480239264744fe0386a1bd8275786fefa126e3129e56a68e22b52c73329965',
                'groups':{name:sorted(values) for name,values in groups.items()},
                'packages':[records[name] for name in sorted(set.union(*groups.values()))]}
    manifest['runtime']={'openssl':ssl.OPENSSL_VERSION,'sqlite':sqlite3.sqlite_version,
                         'expat':pyexpat.EXPAT_VERSION,'tcl':tkinter.Tcl().eval('info patchlevel'),
                         'tk_abi':str(tkinter.TkVersion)}
    manifest['native_build']={'compiler':'MSVC 19.43.34809.0 x64','windows_sdk':'10.0.26100.0',
                             'abi':2,'flags':['/O2','/MT','/GS','/sdl','/guard:cf','/DYNAMICBASE','/NXCOMPAT','/HIGHENTROPYVA','/GUARD:CF']}
    manifest['ocr_models']=[{'file':f'models/tessdata/{name}.traineddata',
                            'source':f'https://github.com/tesseract-ocr/tessdata_fast/blob/main/{name}.traineddata',
                            'sha256':hashlib.sha256((ROOT/f'models/tessdata/{name}.traineddata').read_bytes()).hexdigest()}
                           for name in ('eng','jpn')]
    (ROOT/'docs/DEPENDENCY_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'groups':{name:len(values) for name,values in groups.items()},'packages':len(manifest['packages'])}))


if __name__ == '__main__': main()
