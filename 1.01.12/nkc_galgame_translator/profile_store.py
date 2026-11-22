# SPDX-License-Identifier: MIT
"""Persistent named context sessions. Caller holds its engine SQLite lock.

SQL is authoritative. Display names never become paths. Persistent leases
reject deletion while another engine/process is writing or translating.
"""

from .i18n import ui_source
from contextlib import contextmanager
from datetime import datetime, timezone
import ctypes
import hashlib
import json
import os
import time
import unicodedata
import uuid


def profile_id(name):
    return hashlib.sha256(('profile-v1\0'+name).encode('utf-8')).hexdigest()


def _stamp(seconds):
    return datetime.fromtimestamp(seconds,timezone.utc).isoformat(timespec='milliseconds') if seconds else None


def _process_token(pid):
    if os.name!='nt':
        try:os.kill(pid,0);return 'alive'
        except ProcessLookupError:return None
        except PermissionError:return 'unknown'
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)]
    kernel.GetProcessTimes.restype=wintypes.BOOL
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:return None if ctypes.get_last_error()==87 else 'unknown'
    try:
        values=[wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle,*[ctypes.byref(v) for v in values]):return 'unknown'
        return str((values[0].dwHighDateTime<<32)|values[0].dwLowDateTime)
    finally:kernel.CloseHandle(handle)


class ProfileStore:
    def __init__(self,db,archive,error=ValueError,busy_error=RuntimeError):
        self.db,self.archive,self.error,self.busy_error=db,archive,error,busy_error
        self.owner=uuid.uuid4().hex;self.pid=os.getpid();self.process_token=_process_token(self.pid) or 'unknown'
        db.executescript('''
            CREATE TABLE IF NOT EXISTS profile_details (
                game TEXT PRIMARY KEY, profile_id TEXT UNIQUE NOT NULL, notes TEXT NOT NULL DEFAULT '',
                src_lang TEXT NOT NULL DEFAULT 'en',dst_lang TEXT NOT NULL DEFAULT 'zh-Hans',
                created_at REAL NOT NULL,updated_at REAL NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0,active_elapsed_ms REAL NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS profile_lifecycle (
                profile_id TEXT PRIMARY KEY, generation INTEGER NOT NULL DEFAULT 1, deleted INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS profile_activity (
                lease_id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, owner_id TEXT NOT NULL,
                pid INTEGER NOT NULL,process_token TEXT NOT NULL,started_at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS profile_activity_scope ON profile_activity(profile_id);
        ''')

    @contextmanager
    def transaction(self):
        own=not self.db.in_transaction
        if own:self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            if own:self.db.commit()
        except BaseException:
            if own:self.db.rollback()
            raise

    def validate_name(self,name,allow_blank=False):
        if not isinstance(name,str):raise self.error('\u6863\u6848\u540d\u79f0\u5fc5\u987b\u662f\u6587\u672c\u3002')
        name=unicodedata.normalize('NFC',name).strip()
        if len(name)>256:raise self.error(ui_source('Game profile names cannot exceed 256 characters.'))
        if any(unicodedata.category(c) in {'Cc','Cf','Cs'} for c in name):raise self.error('\u6863\u6848\u540d\u79f0\u5305\u542b\u4e0d\u652f\u6301\u7684\u63a7\u5236\u5b57\u7b26\u3002')
        if not name and not allow_blank:raise self.error('\u8bf7\u9009\u62e9\u4e00\u4e2a\u5df2\u547d\u540d\u7684\u6863\u6848\u3002')
        return name

    def assert_alive(self,name):
        if not name:return
        row=self.db.execute('SELECT deleted FROM profile_lifecycle WHERE profile_id=?',(profile_id(name),)).fetchone()
        if row and row[0]:raise self.error('\u8be5\u6863\u6848\u5df2\u5220\u9664\uff0c\u8bf7\u91cd\u65b0\u9009\u62e9\u6863\u6848\uff1b\u91cd\u65b0\u521b\u5efa\u987b\u663e\u5f0f\u4fdd\u5b58\u3002')

    def names(self):
        rows=self.db.execute('''SELECT game FROM game_profiles UNION SELECT game FROM glossary
            UNION SELECT game FROM translations UNION SELECT game FROM revisions UNION SELECT game FROM auto_terms
            UNION SELECT game FROM profile_details''').fetchall()
        names=set()
        for (value,) in rows:
            try:name=self.validate_name(value,True)
            except (ValueError,RuntimeError):continue
            if name:
                row=self.db.execute('SELECT deleted FROM profile_lifecycle WHERE profile_id=?',(profile_id(name),)).fetchone()
                if not row or not row[0]:names.add(name)
        return sorted(names)

    def _ensure(self,name,source=None,target=None):
        self.assert_alive(name)
        row=self.db.execute('SELECT 1 FROM profile_details WHERE game=?',(name,)).fetchone()
        if row:return
        latest=self.db.execute('SELECT src_lang,dst_lang,created_at FROM translations WHERE game=? ORDER BY created_at DESC LIMIT 1',(name,)).fetchone()
        if not latest:latest=self.db.execute('SELECT src_lang,dst_lang,0 FROM glossary WHERE game=? LIMIT 1',(name,)).fetchone()
        completed=self.archive.profile_status(name)['records']
        if not completed:completed=self.db.execute('SELECT count(*) FROM translations WHERE game=?',(name,)).fetchone()[0]
        events=self.archive.profile_history(name,1)
        notes=events[0]['context'][:16384] if events else ''
        if any(unicodedata.category(c) in {'Cc','Cf','Cs'} and c not in '\r\n\t' for c in notes):notes=''
        now=time.time()
        self.db.execute('INSERT OR IGNORE INTO profile_lifecycle(profile_id) VALUES(?)',(profile_id(name),))
        self.db.execute('INSERT INTO profile_details VALUES(?,?,?,?,?,?,?,?,?)',
            (name,profile_id(name),notes,source or (latest[0] if latest else 'en'),target or (latest[1] if latest else 'zh-Hans'),
             now,latest[2] if latest and latest[2] else now,completed,0))

    def get(self,name):
        name=self.validate_name(name,True)
        if not name or name not in self.names():return None
        with self.transaction():self._ensure(name)
        row=self.db.execute('SELECT profile_id,notes,src_lang,dst_lang,created_at,updated_at,completed,active_elapsed_ms FROM profile_details WHERE game=?',(name,)).fetchone()
        archive=self.archive.profile_status(name)
        latest=self.db.execute('SELECT source,target,created_at FROM translations WHERE game=? ORDER BY created_at DESC,cache_key LIMIT 1',(name,)).fetchone()
        excerpts=self.archive.profile_history(name,3)
        latest_source=excerpts[0]['source'] if excerpts else latest[0] if latest else ''
        latest_translation=excerpts[0]['translation'] if excerpts else latest[1] if latest else ''
        latest_time=excerpts[0]['created_at'] if excerpts else _stamp(latest[2]) if latest else None
        summary='\n'.join(item['source'][:160]+' → '+item['translation'][:200] for item in excerpts)[:1200]
        if not summary and latest:summary=(latest[0][:160]+' → '+latest[1][:200])[:1200]
        ai_note=self.db.execute('SELECT summary FROM ai_scene_summaries JOIN ai_context_scopes USING(scope_key) '
                                'WHERE game=? AND src_lang=? AND dst_lang=? ORDER BY through_id DESC LIMIT 1',
                                (name,row[2],row[3])).fetchone()
        active=self.db.execute('SELECT count(*) FROM profile_activity WHERE profile_id=?',(row[0],)).fetchone()[0]
        return {'profile_id':row[0],'name':name,'game':name,'notes':row[1],'summary_note':ai_note[0] if ai_note else '', 'source_lang':row[2],'target_lang':row[3],
            'created_at':_stamp(row[4]),'updated_at':_stamp(row[5]),'latest_source':latest_source,
            'latest_translation':latest_translation, 'latest_translation_at':latest_time,
            'progress':{'completed':row[6],'active_elapsed_ms':row[7],'active_requests':active,'scopes':archive['scopes']},
            'bounded_summary':summary,'summary_kind':'local_recent_excerpts',
            'compression':{'method':'lossless zlib JSON; bounded local excerpts for prompts',
                           'raw_bytes':archive['raw_bytes'],'compressed_bytes':archive['compressed_bytes']}}

    def save(self,name,notes=None,source=None,target=None):
        name=self.validate_name(name)
        if notes is not None:
            if not isinstance(notes,str) or len(notes)>16384 or any(unicodedata.category(c) in {'Cc','Cf','Cs'} and c not in '\r\n\t' for c in notes):
                raise self.error('\u6863\u6848\u8bed\u5883\u8bf4\u660e\u6700\u591a 16384 \u5b57\u7b26\uff0c\u4e0d\u80fd\u5305\u542b\u63a7\u5236\u5b57\u7b26\u3002')
            notes=unicodedata.normalize('NFC',notes).replace('\r\n','\n').strip()
        with self.transaction():
            self.db.execute('INSERT INTO profile_lifecycle(profile_id) VALUES(?) ON CONFLICT(profile_id) DO UPDATE SET generation=generation+deleted,deleted=0',(profile_id(name),))
            self._ensure(name,source,target)
            self.db.execute('INSERT OR IGNORE INTO game_profiles(game) VALUES(?)',(name,))
            self.db.execute('UPDATE profile_details SET notes=coalesce(?,notes),src_lang=coalesce(?,src_lang),dst_lang=coalesce(?,dst_lang),updated_at=? WHERE game=?',
                            (notes,source,target,time.time(),name))
        return self.get(name)

    def notes(self,name):
        row=self.db.execute('SELECT notes FROM profile_details WHERE game=?',(name,)).fetchone()
        return row[0] if row else ''

    def begin(self,scope):
        name=scope[0]
        if not name:return None
        self.validate_name(name)
        lease=uuid.uuid4().hex
        with self.transaction():
            self._ensure(name,*scope[1:])
            self.db.execute('INSERT INTO profile_activity VALUES(?,?,?,?,?,?)',(lease,profile_id(name),self.owner,self.pid,self.process_token,time.time()))
        return lease

    def end(self,lease):
        if lease:
            with self.transaction():self.db.execute('DELETE FROM profile_activity WHERE lease_id=? AND owner_id=?',(lease,self.owner))

    def release_owner(self):
        with self.transaction():self.db.execute('DELETE FROM profile_activity WHERE owner_id=?',(self.owner,))

    def completed(self,scope,elapsed_ms):
        if not scope[0]:return
        self.assert_alive(scope[0]);self._ensure(scope[0],*scope[1:])
        self.db.execute('UPDATE profile_details SET completed=completed+1,active_elapsed_ms=active_elapsed_ms+?,src_lang=?,dst_lang=?,updated_at=? WHERE game=?',
            (max(0.,elapsed_ms),scope[1],scope[2],time.time(),scope[0]))

    def delete(self,name):
        name=self.validate_name(name);identity=profile_id(name)
        with self.transaction():
            for lease,pid,token in self.db.execute('SELECT lease_id,pid,process_token FROM profile_activity WHERE profile_id=?',(identity,)).fetchall():
                alive=_process_token(pid)
                if alive and (alive=='unknown' or token=='unknown' or alive==token):
                    raise self.busy_error('\u8be5\u6863\u6848\u4ecd\u6709\u7ffb\u8bd1\u6216\u8bed\u5883\u4efb\u52a1\u6b63\u5728\u8fdb\u884c\uff0c\u8bf7\u505c\u6b62\u7ffb\u8bd1\u540e\u518d\u5220\u9664\u3002')
                self.db.execute('DELETE FROM profile_activity WHERE lease_id=?',(lease,))
            if name not in self.names():return False
            keys=self.archive.delete_profile(name)
            self.db.execute('DELETE FROM translation_scopes WHERE cache_key IN (SELECT cache_key FROM translations WHERE game=?)',(name,))
            self.db.execute('DELETE FROM shared_cache_scopes WHERE cache_key IN (SELECT cache_key FROM translations WHERE game=?)',(name,))
            for table in ['glossary','revisions','auto_terms','translations','term_index_revisions','warmup_legacy_scopes','game_profiles','profile_details']:
                self.db.execute('DELETE FROM '+table+' WHERE game=?',(name,))
            warmup=hashlib.sha256(json.dumps(['game-warmup-v1','profile:'+name],ensure_ascii=False,separators=(',',':')).encode('utf-8')).hexdigest()
            self.db.execute('DELETE FROM warmup_progress WHERE scope_key=?',(warmup,))
            self.db.execute('INSERT INTO profile_lifecycle(profile_id,generation,deleted) VALUES(?,1,1) ON CONFLICT(profile_id) DO UPDATE SET generation=generation+1,deleted=1',(identity,))
        self.archive.cleanup_scopes(keys)
        return True
