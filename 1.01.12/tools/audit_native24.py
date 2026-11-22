# SPDX-License-Identifier: MIT
from pathlib import Path
from datetime import datetime, timezone
import hashlib,json
import pefile

root=Path(__file__).resolve().parents[1]
path=root/'native/bin/nkc_galgame_translator_core.dll'
pe=pefile.PE(str(path));flags=pe.OPTIONAL_HEADER.DllCharacteristics
exports={e.name.decode() for e in pe.DIRECTORY_ENTRY_EXPORT.symbols if e.name}
load=pe.DIRECTORY_ENTRY_LOAD_CONFIG.struct
result=dict(version=root.name,dll_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    x64=pe.FILE_HEADER.Machine==0x8664,dynamic_base=bool(flags&0x40),nx_compat=bool(flags&0x100),
    high_entropy_va=bool(flags&0x20),guard_cf=bool(flags&0x4000),
    cf_instrumented=bool(load.GuardFlags&0x100),security_cookie=bool(load.SecurityCookie),
    verified_at=datetime.now(timezone.utc).isoformat(),evidence_origin='Fresh PE headers, load configuration and export inspection')
for name in ('gl_ocr_bgra','gl_overlay_fixed','gl_overlay_options','gl_overlay_anchored','gl_overlay_styled','gl_font_supports'):
    result[name]=name in exports
assert all(result.values()),result
(root/'reports/native-hardening.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
old=json.loads((root.parent/'0.01.23/reports/dependency-audit.json').read_text(encoding='utf-8'))
old['reverified_for_version']='0.01.24'
old['provenance']='Unchanged Python dependency lockfiles; inherited advisory results from0.01.23, not a new vulnerability-database query.'
for name in ('requirements-runtime.lock','requirements-ocr.lock','requirements-build.lock'):
    assert (root/name).read_bytes()==(root.parent/'0.01.23'/name).read_bytes()
(root/'reports/dependency-audit.json').write_text(json.dumps(old,indent=2),encoding='utf-8')
print(json.dumps(result))
