# SPDX-License-Identifier: MIT
"""Offline release SBOM and audit evidence; invoked before package hashing."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def create(root: Path, release: Path, version: str):
    inputs=json.loads((root/'docs/DEPENDENCY_MANIFEST.json').read_text(encoding='utf-8'))
    groups=inputs['groups']
    names=set(groups['runtime']+groups['ocr']+groups['build'])
    packages=[item for item in inputs['packages'] if canonicalize_name(item['name']) in names]
    components=[]; dependencies=[]
    for item in packages:
        name=canonicalize_name(item['name']);ref=f'pkg:pypi/{name}@{item["version"]}'
        components.append({'type':'library','bom-ref':ref,'name':item['name'],'version':item['version'],
            'purl':ref,'licenses':[{'license':{'name':item['license'][:1200]}}],
            'externalReferences':[{'type':'distribution','url':item['url'],
                                   'hashes':[{'alg':'SHA-256','content':item['sha256']}]}],
            'properties':[{'name':'nishokuchou:usage','value':','.join(k for k,v in groups.items() if name in v and k in ('runtime','build','ocr'))}]})
        children=[]
        for value in item['requires_dist']:
            requirement=Requirement(value);child=canonicalize_name(requirement.name)
            if child in names and (requirement.marker is None or requirement.marker.evaluate({'extra':''})):
                target=next(p for p in packages if canonicalize_name(p['name'])==child)
                children.append(f'pkg:pypi/{child}@{target["version"]}')
        dependencies.append({'ref':ref,'dependsOn':sorted(set(children))})
    components.append({'type':'framework','bom-ref':'runtime:cpython','name':'CPython Windows x64','version':inputs['python'],
                       'externalReferences':[{'type':'distribution','url':inputs['python_download'],
                        'hashes':[{'alg':'SHA-256','content':inputs['python_installer_sha256']}]}],
                       'licenses':[{'license':{'name':'Python Software Foundation and bundled runtime notices'}}]})
    for path in sorted(release.rglob('*.dll')):
        relative=path.relative_to(release).as_posix()
        components.append({'type':'file','bom-ref':'file:'+relative,'name':relative,
                           'hashes':[{'alg':'SHA-256','content':hashlib.sha256(path.read_bytes()).hexdigest()}],
                           'properties':[{'name':'nishokuchou:provenance','value':
                            'project source' if path.name=='nkc_galgame_translator_core.dll' else
                            'Tesserocr wheel; see licenses and third_party_sources' if 'tesserocr' in relative else
                            'CPython or package wheel; see licenses and dependency manifest'}]})
    app_ref='application:NKC_Galgame_Translator'
    dependencies.append({'ref':app_ref,'dependsOn':[c['bom-ref'] for c in components]})
    sbom={'bomFormat':'CycloneDX','specVersion':'1.6','version':1,
          'metadata':{'component':{'type':'application','bom-ref':app_ref,'name':'NKC_Galgame_Translator','version':version,
                      'licenses':[{'license':{'id':'MIT'}}]}},
          'components':components,'dependencies':dependencies}
    (release/'SBOM.cdx.json').write_text(json.dumps(sbom,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    shutil.copy2(root/'reports/dependency-audit.json',release/'DEPENDENCY_AUDIT.json')
    hardening=json.loads((root/'reports/native-hardening.json').read_text(encoding='utf-8'))
    if not all(hardening.values()):raise RuntimeError('Native hardening evidence failed')
    shutil.copy2(root/'reports/native-hardening.json',release/'docs/NATIVE_HARDENING.json')
    (release/'RELEASE_METADATA.json').write_text(json.dumps({'schema':1,'version':version,'platform':'Windows x86-64',
        'python':inputs['python'],'native_abi':2,'private_configuration_included':False,
        'code_signed':False,'sbom':'SBOM.cdx.json','dependency_audit':'DEPENDENCY_AUDIT.json',
        'documentation':{'status':'current','version':version,
                         'refreshed_for_this_release':True,'teacher_presentation_included':False},
        'optional_cuda':{'included':False,'archive':f'NKC_Galgame_Translator-{version}-cuda-addon.zip',
                         'manifest':'CUDA_DEPENDENCY_MANIFEST.json',
                         'dependency_audit_scope':'Not covered by the base Python advisory scan'},
        'limitations':['No blanket prompt-injection or zero-vulnerability guarantee.',
                       'Python advisory scan does not cover every bundled native library.',
                       'SHA256 detects changes relative to a trusted manifest; it is not a publisher signature.']},indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    create(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3])
