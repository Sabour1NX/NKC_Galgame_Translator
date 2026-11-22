# SPDX-License-Identifier: MIT
"""Explicit, project-local installation of the optional CUDA OCR runtime.

Does not change system Python, PATH or the GPU driver. Run with the packaged
CPython 3.14 x64 host. Every wheel/model is pinned to a SHA-256 digest.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.metadata
import json
import os
import runpy
import shutil
import sys
import urllib.request
import urllib.parse

PIP={'file':'pip-26.3-py3-none-any.whl',
     'url':'https://files.pythonhosted.org/packages/07/25/ee8c38ae72d66b844ce8eb9711ba905dba21ca1a8a0c960057c41cd23337/pip-26.3-py3-none-any.whl',
     'sha256':'f3b60b20ffaadd4415ed7957212a38ac63fa4c5fa375bd0f4a797777940fad13'}


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def download(item,path,max_bytes=512*1024*1024):
    if path.is_file() and digest(path)==item['sha256']:return
    url=urllib.parse.urlsplit(item['url'])
    if url.scheme!='https' or url.hostname not in {'files.pythonhosted.org','www.modelscope.cn'}:
        raise ValueError('Unsupported package source')
    path.parent.mkdir(parents=True,exist_ok=True)
    part=path.with_suffix(path.suffix+'.part')
    try:
        request=urllib.request.Request(item['url'],headers={'User-Agent':'Nishokuchou-CUDA-Setup/0.01.27'})
        with urllib.request.urlopen(request,timeout=120) as response,part.open('wb') as stream:
            count=0
            for chunk in iter(lambda:response.read(1024*1024),b''):
                count+=len(chunk)
                if count>max_bytes:raise ValueError('Download exceeds size limit')
                stream.write(chunk)
        if digest(part)!=item['sha256']:raise ValueError('SHA-256 mismatch: '+path.name)
        part.replace(path)
    finally:
        if part.exists():part.unlink()


def verify(root):
    manifest=json.loads((root/'CUDA_DEPENDENCY_MANIFEST.json').read_text(encoding='utf-8'))
    found={d.metadata['Name'].lower().replace('_','-'):d.version for d in importlib.metadata.distributions(path=[str(root/'vendor/cuda')])}
    missing=[i['name'] for i in manifest['packages'] if found.get(i['name'].lower().replace('_','-'))!=i['version']]
    models=json.loads((root/'models/cuda/manifest.json').read_text(encoding='utf-8'))
    for item in models['models'].values():
        path=root/'models/cuda'/item['file']
        if not path.is_file() or digest(path)!=item['sha256']:missing.append(item['file'])
    if missing:raise RuntimeError('Missing or mismatched CUDA files: '+', '.join(missing))
    print('CUDA runtime files and model digests verified. Actual GPU execution is checked on first OCR.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models-only',action='store_true')
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    if args.verify:verify(root);return 0
    if os.name!='nt' or sys.version_info[:2]!=(3,14) or sys.maxsize<2**32:
        raise RuntimeError('Use the bundled Windows x86-64 CPython 3.14 interpreter')
    if not args.models_only:
        wheel=root/'vendor/cuda-bootstrap'/PIP['file'];download(PIP,wheel,8*1024*1024)
        sys.path.insert(0,str(wheel))
        sys.argv=['pip','install','--disable-pip-version-check','--target',str(root/'vendor/cuda'),
                  '--upgrade','--no-deps','--only-binary=:all:','--require-hashes',
                  '-r',str(root/'requirements-cuda.lock')]
        try:runpy.run_module('pip',run_name='__main__')
        except SystemExit as exc:
            if exc.code:raise RuntimeError('CUDA wheel installation failed') from exc
    manifest=json.loads((root/'models/cuda/manifest.json').read_text(encoding='utf-8'))
    for item in manifest['models'].values():
        path=root/'models/cuda'/item['file']
        bundled=root/'vendor/cuda/rapidocr/models'/item['file']
        if not path.exists() and bundled.is_file() and digest(bundled)==item['sha256']:
            shutil.copy2(bundled,path)
        download(item,path)
    verify(root)
    return 0


if __name__=='__main__':raise SystemExit(main())
