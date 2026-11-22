# SPDX-License-Identifier: MIT
"""Find exact text that must survive localization, without guessing prose."""
from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True)
class Literal:
    start: int
    end: int
    credential: bool = False


_PASSWORD = re.compile(
    r'(?:(?<![A-Za-z0-9_])(?:pass(?:word|code|phrase)|access code|unlock code|pin(?: code)?)'
    '(?![A-Za-z0-9_])|\u5bc6\u7801|\u5bc6\u78bc|\u53e3\u4ee4|\u901a\u5173\u5bc6\u8bed|\u30d1\u30b9\u30ef\u30fc\u30c9|\u6697\u8a3c\u756a\u53f7|\u5408\u8a00\u8449)'
    '[ \\t]*(?P<marker>[:\uff1a=\uff1d]|is\\b|\u306f|\u4e3a|\u70ba|\u662f)[ \\t]*', re.I)
_SPELL = re.compile(
    r'(?:(?<![A-Za-z0-9_])(?:spell|incantation|chant|magic words)(?![A-Za-z0-9_])'
    '|\u546a\u6587|\u5492\u8bed|\u5492\u8a9e|\u5492\u6587|\u8a60\u5531|\u541f\u5531)[ \\t]*(?P<marker>[:\uff1a=\uff1d]|is\\b|\u306f|\u4e3a|\u70ba|\u662f)?[ \\t]*'
    r'|(?<![A-Za-z0-9_])(?:cast|recite|chant)[ \t]+(?:the spell[ \t]+)?', re.I)
_QUOTE_PAIRS = {'"':'"', "'":"'", '“':'”', '‘':'’', '\u300c':'\u300d', '\u300e':'\u300f', '\u300a':'\u300b',
                '«':'»', '`':'`', '\u3010':'\u3011', '\uff3b':'\uff3d'}
_BARE = re.compile('[^\\s"\u201c\u201d\u300c\u300d\u300e\u300f\u300a\u300b\u3010\u3011\uff3b\uff3d\uff0c\u3001\u3002\uff1b]+')

# Keep exact brand/protocol/API spellings. Capitalization alone is not a
# reason to preserve ordinary text such as "START GAME" or "Graphics".
_NAMES = (
    'AMD FidelityFX Super Resolution','Intel Xe Super Sampling','NVIDIA DLSS','NVIDIA Reflex','NVIDIA RTX',
    'FidelityFX Super Resolution','Unreal Engine','ONNX Runtime','Shader Model','Steam Deck',
    'DirectStorage','DirectX','Direct3D','GameStream','PhysX','FidelityFX','FreeSync','G-SYNC',
    'Vulkan','OpenGL','OpenCL','WebGPU','MetalFX','GeForce','Radeon','Win32','DXGI','CUDA',
    'TensorRT','cuDNN','cuBLAS','NVIDIA','DLSS','DLAA','FSR','XeSS','NVENC','NVDEC','AV1',
    'TCP/IP','OpenXR','HDR10+','HDR10','Dolby Vision','HDMI','DisplayPort','USB-C','NVMe',
    'Unicode','UTF-8','UTF-16','UTF-32','WASAPI','XInput','WASD','CPU','GPU','API','RAM','VRAM',
)
_TECH = re.compile(
    r'(?<![A-Za-z0-9_])(?:'
    + '|'.join(map(re.escape,sorted(_NAMES,key=len,reverse=True)))
    + r')(?:[ \t]+v?\d+(?:\.\d+){0,2})?(?![A-Za-z0-9_])'
    r'|(?<![A-Za-z0-9_])(?:(?:DXGI|D3D12?|VK|GL)_\w{2,96}|(?:vk|gl|cu)[A-Z][A-Za-z0-9]{3,64})(?![A-Za-z0-9_])'
)


def _quoted_end(text,start):
    if start>=len(text) or text[start] not in _QUOTE_PAIRS:
        return None
    end=text.find(_QUOTE_PAIRS[text[start]],start+1,min(len(text),start+513))
    if end>start+1 and not {'\r','\n'}.intersection(text[start:end]):
        return end+1
    return None


def _password_value(text,match):
    start=match.end()
    # OCR or a pasted field can put a visibly labeled value on the next line.
    if text[start:start+1]=='\n':
        start+=1
        while text[start:start+1] in (' ', '\t'):
            start+=1
    end=_quoted_end(text,start)
    if end is not None:
        return Literal(start,end,True)
    bare=_BARE.match(text,start)
    if not bare:
        return None
    value=bare[0]
    # "Password is required" is dialog text, not a credential. Bare values
    # after a colon may be plain words; copulas require additional evidence.
    marker=match['marker'].lower()
    field=marker in ':\uff1a=\uff1d'
    sentence=text[bare.end():].split('\n',1)[0].strip()
    if field and (not sentence or sentence[0] in ',;\uff0c\uff1b\u3002'):
        return Literal(start,bare.end(),True)
    if (any(ch.isdigit() or ch in '-_!@#$%^&*' for ch in value)
            or (value[:1].isupper() and value.casefold().rstrip('.,!?;') not in
                {'required','incorrect','invalid','wrong','missing','empty','optional','set','updated'})):
        return Literal(start,bare.end(),True)
    return None


def literal_ranges(text):
    parts=[]
    for match in _PASSWORD.finditer(text):
        item=_password_value(text,match)
        if item is not None:
            parts.append(item)
    for match in _SPELL.finditer(text):
        start=match.end()
        end=_quoted_end(text,start)
        if end is None and match['marker'] in (':','\uff1a','=','\uff1d'):
            # An explicit spell label may contain a multiword chant. Bound it
            # by the physical row or a separate instruction/field separator.
            end=start
            while end<len(text) and end-start<256 and text[end] not in '\r\n;\uff1b\u3002':
                end+=1
            while end>start and text[end-1].isspace():
                end-=1
        if end is not None and end>start:
            parts.append(Literal(start,end))
    parts.extend(Literal(*match.span()) for match in _TECH.finditer(text))
    result=[]
    for item in sorted(parts,key=lambda item:(item.start,not item.credential,-item.end)):
        if not result or item.start>=result[-1].end:
            result.append(item)
        else:
            prior=result[-1]
            result[-1]=Literal(prior.start,max(prior.end,item.end),prior.credential or item.credential)
    return result


def only_literals(text, parts=None):
    parts=literal_ranges(text) if parts is None else parts
    if not parts:
        return False
    offset=0
    gaps=[]
    for item in parts:
        gaps.append(text[offset:item.start])
        offset=item.end
    gaps.append(text[offset:])
    return not any(not char.isspace() and not unicodedata.category(char).startswith('P')
                   for gap in gaps for char in gap)


def redact_credentials(text):
    offset=0
    pieces=[]
    for item in literal_ranges(text):
        if item.credential:
            pieces.extend((text[offset:item.start],'[password omitted]'))
            offset=item.end
    return ''.join((*pieces,text[offset:]))


def separate_literal_values(lines):
    """Protect a single value in the neighboring box of a labeled OCR field."""
    indices=set()
    for index,label in enumerate(lines):
        name=label['text'].strip()
        if not name.endswith((':','\uff1a','=','\uff1d')) or not (_PASSWORD.fullmatch(name) or _SPELL.fullmatch(name)):
            continue
        for other,value in enumerate(lines):
            if other==index or label.get('_selection_id',0)!=value.get('_selection_id',0):
                continue
            h=max(label['h'],value['h'])
            right=value['x']-(label['x']+label['w'])
            down=value['y']-(label['y']+label['h'])
            same_row=0<=right<=1.4*h and abs(label['y']-value['y'])<=h*.35
            next_row=0<=down<=.65*h and abs(label['x']-value['x'])<=h*.5
            if not (same_row or next_row):
                continue
            raw=value['text'].strip()
            if not raw or len(raw)>256 or '\n' in raw:
                continue
            explicit=f'{name} {raw}'
            spans=literal_ranges(explicit)
            if any(span.start==len(name)+1 and span.end==len(explicit) for span in spans):
                indices.add(other)
                break
    return indices
