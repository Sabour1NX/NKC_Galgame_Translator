# SPDX-License-Identifier: MIT
"""Opt-in background export of completed, captured translation pages."""

from .i18n import ui_source
from collections import OrderedDict
import csv
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
import io
import json
from pathlib import Path
import queue
import re
import threading
import time
import unicodedata

from .config_store import _atomic_write
from .translation_quality import translation_issue

FORMATS=('txt','json','csv')
DEFAULT_WAIT=15


def export_preferences(config):
    enabled=config.get('localization_enabled',False)
    folder=config.get('localization_folder','')
    format_=config.get('localization_format','txt')
    wait=config.get('localization_wait',DEFAULT_WAIT)
    if isinstance(wait,str) and wait.isascii() and wait.isdecimal() and len(wait)<=3:
        wait=int(wait)
    if type(enabled) is not bool or format_ not in FORMATS or type(wait) is not int or not 1<=wait<=120:
        raise ValueError('\u8bf7\u9009\u62e9\u5bfc\u51fa\u683c\u5f0f\uff0c\u9074\u9009\u7b49\u5f85\u987b\u4e3a 1 \u81f3 120 \u79d2\u3002')
    if (not isinstance(folder,str) or any(ord(c)<32 for c in folder) or
            (folder and (not Path(folder).is_absolute() or folder.startswith(('\\\\','//'))))):
        raise ValueError('\u8bf7\u9009\u62e9\u672c\u673a\u6587\u4ef6\u5939\u4fdd\u5b58\u6c49\u5316\u6587\u672c\u3002')
    return dict(localization_enabled=enabled,localization_folder=folder,
                localization_format=format_,localization_wait=wait)


def safe_stem(name):
    clean=re.sub(r'[<>:"/\\|?*.\x00-\x1f]', '_',name).strip()[:88].rstrip(' .')
    return clean or 'Game'


def source_key(text):
    return ''.join(c.casefold() for c in unicodedata.normalize('NFKC',text)
                   if c.isalnum())


@dataclass(frozen=True)
class Line:
    track: int
    original: str
    translated: str
    target: str
    score: tuple


@dataclass
class Selection:
    deadline: float
    timestamp: datetime
    line: Line
    page: int


class Exporter:
    def __init__(self,folder,format_,wait,on_error):
        self.folder=Path(folder)
        self.format=format_
        self.wait=wait
        self.on_error=on_error
        self.queue=queue.Queue(maxsize=12)
        self.worker=threading.Thread(target=self._run,name='localization-export',daemon=True)
        self.worker.start()

    def offer(self,session,name,rows,image):
        try:
            self.queue.put_nowait((session,name,rows,image,datetime.now().astimezone()))
        except queue.Full:
            image.close()
            self.on_error()

    def close(self):
        self.queue.put(None)
        self.worker.join()

    def _run(self):
        pending={}
        seen=OrderedDict()
        pages={}
        files={}
        committed_pages={}
        serial=0
        while True:
            try:
                work=self.queue.get(timeout=.30)
            except queue.Empty:
                work=()
            if work:
                session,name,rows,image,timestamp=work
                group=(session,safe_stem(name),timestamp.date().isoformat())
                serial+=1
                try:
                    with image,io.BytesIO() as stream:
                        image.save(stream,format='PNG',compress_level=2)
                        pages[serial]=stream.getvalue()
                except (OSError,ValueError):
                    self.on_error()
                    continue
                for line in rows:
                    key=source_key(line.original)
                    if not key or not line.translated.strip() or translation_issue(line.original,line.translated,line.target):
                        continue
                    token=(group,key)
                    if token in seen:
                        continue
                    previous=pending.get(token)
                    if previous is None:
                        # A corrected OCR reading may differ slightly while retaining
                        # the physical track. Dissimilar dialogue on that track stays separate.
                        for old_token,possible in reversed(pending.items()):
                            if old_token[0]==group and possible.line.track==line.track:
                                if min(len(key),len(old_token[1]))>=8 and SequenceMatcher(None,key,old_token[1]).ratio()>=.87:
                                    token,previous=old_token,possible
                                break
                    if previous is None:
                        pending[token]=Selection(time.monotonic()+self.wait,timestamp,line,serial)
                    elif line.score>=previous.line.score and line!=previous.line:
                        pending[token]=Selection(previous.deadline,timestamp,line,serial)
            due=OrderedDict()
            now=time.monotonic()
            for token in list(pending):
                if work is not None and pending[token].deadline>now:
                    continue
                item=pending.pop(token)
                due.setdefault(token[0],[]).append((token,item))
            for group,entries in due.items():
                try:
                    path=files.get(group)
                    if path is None:
                        path=self._new_file(group)
                        files[group]=path
                    rows=[]
                    for token,item in entries:
                        shot=(group,item.page)
                        picture=committed_pages.get(shot)
                        if picture is None:
                            picture=path.with_name(f'{path.stem}-page-{item.page:04d}.png')
                            _atomic_write(picture,pages[item.page])
                            committed_pages[shot]=picture
                        rows.append(dict(timestamp=item.timestamp.isoformat(timespec='seconds'),
                                         source=item.line.original,translation=item.line.translated,
                                         screenshot=picture.name))
                    self._write(path,rows)
                    for token,item in entries:
                        seen[token]=True
                        seen[(group,source_key(item.line.original))]=True
                    while len(seen)>4096:
                        seen.popitem(last=False)
                except (OSError,ValueError):
                    self.on_error()
            active={item.page for item in pending.values()}
            for page in pages.keys()-active:
                del pages[page]
            for stamp in list(committed_pages):
                if stamp[1] not in active:
                    del committed_pages[stamp]
            if work is None:
                return

    def _new_file(self,group):
        _,name,day=group
        self.folder.mkdir(parents=True,exist_ok=True)
        for number in range(1,10000):
            suffix='' if number==1 else f'-{number:02d}'
            path=self.folder/f'{name}{day}{suffix}.{self.format}'
            try:
                with path.open('xb'):
                    pass
                return path
            except FileExistsError:
                continue
        raise OSError('No available export filename')

    def _write(self,path,rows):
        if self.format=='json':
            existing=path.read_text('utf-8')
            values=json.loads(existing) if existing else []
            _atomic_write(path,(json.dumps(values+rows,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
        elif self.format=='csv':
            new=path.stat().st_size==0
            with path.open('a',encoding='utf-8-sig' if new else 'utf-8',newline='') as stream:
                writer=csv.writer(stream)
                if new:
                    writer.writerow(('\u65f6\u95f4\u6233',ui_source('Original text'),'\u7ffb\u8bd1','\u622a\u56fe'))
                for row in rows:
                    writer.writerow("'" + value if value.lstrip().startswith(('=','+','-','@')) else value
                                    for value in row.values())
        else:
            with path.open('a',encoding='utf-8',newline='\n') as stream:
                for row in rows:
                    stream.write(f"[{row['timestamp']}]\n\u539f\u6587\uff1a\n{row['source']}\n\n\u7ffb\u8bd1:\n{row['translation']}\n\n")

