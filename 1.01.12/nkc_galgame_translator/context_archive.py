# SPDX-License-Identifier: MIT
"""Lossless local event storage and bounded extractive AI reference context.

The caller serializes SQLite access with the engine lock. Compression is zlib
storage compression plus prompt excerpt selection, NOT an AI-written summary.
Full events are append-only; prompts never recursively include previous prompts.
"""
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
import re
from pathlib import Path
import tempfile
import zlib
from .literal_rules import redact_credentials

MAX_EVENT_BYTES = 1024 * 1024
CHINA_TIME = timezone(timedelta(hours=8))


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def _term_matches(source, text):
    """Literal terminology lookup, not a translation rule or replacement."""
    left = r'(?<![A-Za-z0-9_])' if source and source[0].isascii() and (source[0].isalnum() or source[0]=='_') else ''
    right = r'(?![A-Za-z0-9_])' if source and source[-1].isascii() and (source[-1].isalnum() or source[-1]=='_') else ''
    return bool(source and re.search(left+re.escape(source)+right, text, re.IGNORECASE | re.ASCII))


def scope_key(scope, identity=None):
    # Explicit profile names intentionally share reference history. Unnamed
    # games use the selected executable identity rather than one global bucket.
    discriminator = identity[0] if not scope[0] and identity else None
    return hashlib.sha256(_json(['context-v1', scope, discriminator]).encode('utf-8')).hexdigest()


def decode_event(blob):
    if not isinstance(blob, bytes) or len(blob) > MAX_EVENT_BYTES:
        raise ValueError('Invalid compressed archive event')
    decoder = zlib.decompressobj()
    raw = decoder.decompress(blob, MAX_EVENT_BYTES + 1)
    if len(raw) > MAX_EVENT_BYTES or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError('Invalid compressed archive event')
    item = json.loads(raw)
    if (not isinstance(item, dict) or item.get('schema') != 1 or
            any(not isinstance(item.get(key), str) for key in
                ('source', 'translation', 'context', 'prompt_context', 'model', 'created_at'))):
        raise ValueError('Invalid archive event schema')
    if any(0xD800 <= ord(ch) <= 0xDFFF for key in
           ('source', 'translation', 'context', 'prompt_context', 'model', 'created_at') for ch in item[key]):
        raise ValueError('Invalid archive text encoding')
    return item


class ContextArchive:
    def __init__(self, db, folder, database_name, max_chars=4096, history_records=2):
        self.db, self.folder = db, Path(folder)
        self.database_name = str(database_name)
        self.max_chars, self.history_records = max_chars, history_records
        self.summary_chars = min(2048,max(128,max_chars//4))
        self.manifest_errors = 0
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS ai_context_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope_key TEXT NOT NULL, created_at TEXT NOT NULL,
                payload BLOB NOT NULL, raw_bytes INTEGER NOT NULL);
            CREATE INDEX IF NOT EXISTS ai_context_events_scope
                ON ai_context_events(scope_key,id DESC);
            CREATE TABLE IF NOT EXISTS ai_context_scopes (
                scope_key TEXT PRIMARY KEY,game TEXT NOT NULL,src_lang TEXT NOT NULL,dst_lang TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS ai_event_totals (
                scope_key TEXT PRIMARY KEY,n INTEGER NOT NULL,stamp TEXT NOT NULL,
                raw INTEGER NOT NULL,packed INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS ai_archive_migrations (name TEXT PRIMARY KEY);
            CREATE INDEX IF NOT EXISTS ai_event_stamps ON ai_context_events(scope_key,created_at);
            CREATE TRIGGER IF NOT EXISTS ai_event_added AFTER INSERT ON ai_context_events BEGIN
                INSERT INTO ai_event_totals VALUES(NEW.scope_key,1,NEW.created_at,NEW.raw_bytes,length(NEW.payload))
                ON CONFLICT(scope_key) DO UPDATE SET n=n+1,stamp=max(stamp,excluded.stamp),
                    raw=raw+excluded.raw,packed=packed+excluded.packed;
            END;
            CREATE TRIGGER IF NOT EXISTS ai_event_removed AFTER DELETE ON ai_context_events BEGIN
                DELETE FROM ai_event_totals WHERE scope_key=OLD.scope_key AND n=1;
                UPDATE ai_event_totals SET n=n-1,raw=raw-OLD.raw_bytes,packed=packed-length(OLD.payload),
                    stamp=CASE WHEN stamp=OLD.created_at THEN
                        (SELECT max(created_at) FROM ai_context_events WHERE scope_key=OLD.scope_key)
                        ELSE stamp END WHERE scope_key=OLD.scope_key;
            END;
            CREATE TABLE IF NOT EXISTS ai_scene_summaries (
                scope_key TEXT PRIMARY KEY,through_id INTEGER NOT NULL,summary TEXT NOT NULL);
        ''')
        # Older event payloads intentionally omit private executable identity.
        # Named profile scopes are still recoverable from their language rows.
        with self.db:
            if self.db.execute("INSERT OR IGNORE INTO ai_archive_migrations VALUES('event_totals_v1')").rowcount:
                self.db.execute("""INSERT OR REPLACE INTO ai_event_totals
                    SELECT scope_key,count(*),max(created_at),sum(raw_bytes),sum(length(payload))
                    FROM ai_context_events GROUP BY scope_key""")
            for scope in self.db.execute('''SELECT game,src_lang,dst_lang FROM translations
                    UNION SELECT game,src_lang,dst_lang FROM glossary
                    UNION SELECT game,src_lang,dst_lang FROM revisions
                    UNION SELECT game,src_lang,dst_lang FROM auto_terms''').fetchall():
                if scope[0]:self._register(scope)

    def _register(self,scope,identity=None):
        self.db.execute('INSERT OR IGNORE INTO ai_context_scopes VALUES(?,?,?,?)',
                        (scope_key(scope,identity),*scope))

    def profile_status(self,game):
        scopes=self.db.execute('''SELECT s.src_lang,s.dst_lang,count(e.id),coalesce(sum(e.raw_bytes),0),
            coalesce(sum(length(e.payload)),0) FROM ai_context_scopes s LEFT JOIN ai_context_events e ON e.scope_key=s.scope_key
            WHERE s.game=? GROUP BY s.src_lang,s.dst_lang ORDER BY s.src_lang,s.dst_lang''',(game,)).fetchall()
        return {'records':sum(r[2] for r in scopes),'raw_bytes':sum(r[3] for r in scopes),
                'compressed_bytes':sum(r[4] for r in scopes),
                'scopes':[{'source_lang':r[0],'target_lang':r[1],'records':r[2]} for r in scopes]}

    def profile_history(self,game,limit=3):
        rows=self.db.execute('''SELECT e.payload FROM ai_context_events e JOIN ai_context_scopes s ON s.scope_key=e.scope_key
            WHERE s.game=? ORDER BY e.id DESC LIMIT ?''',(game,min(64,max(1,int(limit))))).fetchall()
        result=[]
        for (blob,) in rows:
            try:result.append(decode_event(blob))
            except (ValueError,TypeError,UnicodeError,zlib.error,RecursionError):continue
        return result

    def delete_profile(self,game):
        """Caller owns the SQLite transaction; never deletes unnamed scopes."""
        if not game:raise ValueError('A named profile is required')
        keys=[r[0] for r in self.db.execute('SELECT scope_key FROM ai_context_scopes WHERE game=?',(game,))]
        for key in keys:self._safe_directory(key)
        self.db.execute('DELETE FROM ai_context_events WHERE scope_key IN (SELECT scope_key FROM ai_context_scopes WHERE game=?)',(game,))
        self.db.execute('DELETE FROM ai_scene_summaries WHERE scope_key IN (SELECT scope_key FROM ai_context_scopes WHERE game=?)',(game,))
        self.db.execute('DELETE FROM ai_context_scopes WHERE game=?',(game,))
        return keys

    def _safe_directory(self,key):
        if not isinstance(key,str) or not re.fullmatch('[0-9a-f]{64}',key):raise ValueError('Invalid context scope ID')
        root=self.folder.resolve();directory=self.folder/key
        if directory.is_symlink() or directory.resolve().parent!=root:
            raise ValueError('Unsafe context index path')
        if directory.exists() and getattr(directory.stat(),'st_file_attributes',0)&0x400:
            raise ValueError('Context index cannot be a reparse point')
        return directory

    def cleanup_scopes(self,keys):
        # Only our known advisory files are removed. Never recursively follow
        # user-added entries, junctions or symbolic links.
        for key in keys:
            directory=self._safe_directory(key)
            if not directory.exists():continue
            for path in [directory/'updated.json',*directory.glob('.updated-*.tmp')]:
                if path.is_symlink() or (path.exists() and getattr(path.stat(),'st_file_attributes',0)&0x400):
                    raise ValueError('Unsafe context index file')
                path.unlink(missing_ok=True)
            try:directory.rmdir()
            except OSError:
                if not any(directory.iterdir()):raise

    def history(self, scope, identity=None, limit=24):
        limit = min(64, max(1, int(limit)))
        rows = self.db.execute('SELECT payload FROM ai_context_events WHERE scope_key=? '
                               'ORDER BY id DESC LIMIT ?', (scope_key(scope, identity), limit))
        result = []
        for (blob,) in rows:
            try:
                result.append(decode_event(blob))
            except (ValueError, TypeError, UnicodeError, zlib.error, RecursionError):
                # A damaged external record must not poison prompts or prevent
                # new translations. Original data remains available for repair.
                continue
        return result

    def prompt(self, scope, identity, text, context, profile_notes='', *, page_budget=None):
        limit_chars=self.max_chars if page_budget is None else min(self.max_chars,page_budget)
        reference = {'kind': 'bounded_history_excerpts', 'user_context': '',
                     'terms': [], 'recent_translations': []}
        if profile_notes:
            reference['profile_notes']=''
            if context.strip()==profile_notes.strip():context=''
        def append_bounded(field, entry):
            reference[field].append(entry)
            if len(_json(reference)) > limit_chars:
                reference[field].pop()
                return False
            return True

        # Existing dictionaries are reference only. SQL selects actual literal
        # matches without building or importing an expert rule engine.
        seen_terms = set()
        if scope[0]:
            rows = self.db.execute('SELECT source,target FROM glossary '
                'WHERE game=? AND src_lang=? AND dst_lang=? AND instr(lower(?),lower(source))>0 '
                'ORDER BY length(source) DESC,source LIMIT 256', (*scope, text))
            for source, target in rows:
                if not _term_matches(source,text):continue
                # Mark game ownership even when its complete mapping cannot fit;
                # never silently replace it with a conflicting shared term.
                term_key=source.lower()
                if term_key in seen_terms:continue
                seen_terms.add(term_key)
                if len(reference['terms'])>=32:continue
                append_bounded('terms', {'source': source, 'translation': target})

        # Explicitly imported general terms are intentionally shared across
        # games. They are lower priority than a named game's own terminology;
        # unassigned legacy game terms above are still never attributed by guess.
        rows = self.db.execute('SELECT source,target FROM shared_glossary '
            'WHERE src_lang=? AND dst_lang=? AND instr(lower(?),lower(source))>0 '
            'ORDER BY length(source) DESC,source LIMIT 256', (*scope[1:], text))
        for source, target in rows:
            if len(reference['terms']) >= 32:
                break
            if source.lower() in seen_terms or not _term_matches(source,text):
                continue
            if append_bounded('terms', {'source': source, 'translation': target, 'scope': 'shared'}):
                seen_terms.add(source.lower())

        # Explicit matching terminology precedes narrative notes and history.
        # Whole mappings are kept or omitted, never truncated into other names.
        summary = self.db.execute('SELECT summary FROM ai_scene_summaries WHERE scope_key=?',
                                  (scope_key(scope,identity),)).fetchone()
        fields=[]
        if summary and summary[0]:
            reference['scene_summary']=''
            fields.append(('scene_summary',redact_credentials(summary[0])[:self.summary_chars]))
        fields.extend((('profile_notes',profile_notes),('user_context',context)))
        for field,value in fields:
            if field not in reference:continue
            low,high=0,len(value)
            while low<high:
                middle=(low+high+1)//2;reference[field]=value[:middle]
                if len(_json(reference))<=limit_chars:low=middle
                else:high=middle-1
            reference[field]=value[:low]
            if field=='scene_summary' and not low:
                reference.pop(field)

        # Short captions need less history. User-authored notes and explicit
        # terminology keep their own precedence above all automatic content.
        if page_budget is not None or 'scene_summary' in reference:
            return _json(reference)
        remaining = self.max_chars
        limit = min(self.history_records,2 if len(text)<=48 else 4)
        has_space = len(_json(reference))+40<remaining
        history = self.history(scope, identity, limit) if has_space else []
        # Pre-upgrade entries have no executable identity. Never attribute the
        # unnamed legacy book to a currently selected unnamed game.
        if has_space and not history and scope[0]:
            rows = self.db.execute('''SELECT t.source,t.target,coalesce(s.context,'')
                FROM translations t LEFT JOIN translation_scopes s ON t.cache_key=s.cache_key
                WHERE t.game=? AND t.src_lang=? AND t.dst_lang=?
                ORDER BY t.created_at DESC,t.cache_key LIMIT ?''', (*scope, limit))
            history = [{'source': a, 'translation': b, 'context': c} for a,b,c in rows]
        # Fit each recent pair into the remaining reference budget.
        excerpt_chars=max(0,(remaining-len(_json(reference))-40)//(2*max(1,len(history))))
        for item in history:
            excerpt = {'source': redact_credentials(item['source'])[:excerpt_chars],
                       'translation': redact_credentials(item['translation'])[:excerpt_chars]}
            reference['recent_translations'].append(excerpt)
            if len(_json(reference))>remaining:
                reference['recent_translations'].pop()
        return _json(reference)

    def summary_due(self,scope,identity):
        key=scope_key(scope,identity)
        return self.db.execute(
            'SELECT 1 FROM ai_context_events WHERE scope_key=? AND id>coalesce('
            '(SELECT through_id FROM ai_scene_summaries WHERE scope_key=?),0) '
            'ORDER BY id DESC LIMIT 1 OFFSET 5',(key,key)).fetchone() is not None

    def summary_seed(self, scope, identity):
        key=scope_key(scope,identity)
        state=self.db.execute('SELECT through_id,summary FROM ai_scene_summaries WHERE scope_key=?',(key,)).fetchone()
        through, previous = state or (0,'')
        fresh=self.db.execute('SELECT id,payload FROM ai_context_events WHERE scope_key=? AND id>? '
                              'ORDER BY id DESC LIMIT 6',(key,through)).fetchall()
        if len(fresh)<6:
            return None
        excerpts=[]
        excerpt_chars=max(120,min(1024,self.max_chars//12))
        for _,blob in reversed(fresh):
            try:
                event=decode_event(blob)
                excerpts.append([redact_credentials(event['source'])[:excerpt_chars],
                                 redact_credentials(event['translation'])[:excerpt_chars]])
            except (ValueError,TypeError,UnicodeError,zlib.error,RecursionError):
                continue
        if not excerpts:
            return None
        return key,fresh[0][0],_json({'previous_summary':redact_credentials(previous)[:self.summary_chars],'recent_pairs':excerpts})

    def store_summary(self,key,through,summary):
        self.db.execute('INSERT INTO ai_scene_summaries VALUES(?,?,?) ON CONFLICT(scope_key) '
                        'DO UPDATE SET through_id=excluded.through_id,summary=excluded.summary '
                        'WHERE excluded.through_id>ai_scene_summaries.through_id',(key,through,summary[:self.summary_chars]))

    def record(self, scope, identity, source, translation, context, prompt_context, model):
        self._register(scope,identity)
        stamp = datetime.now(CHINA_TIME).isoformat(timespec='milliseconds')
        item = {'schema': 1, 'source': source, 'translation': translation,
                'context': context, 'prompt_context': prompt_context, 'model': model,
                'created_at': stamp}
        raw = _json(item).encode('utf-8')
        if len(raw) > MAX_EVENT_BYTES:
            raise ValueError('Archive event exceeds storage limit')
        self.db.execute('INSERT INTO ai_context_events(scope_key,created_at,payload,raw_bytes) '
                        'VALUES(?,?,?,?)', (scope_key(scope, identity), stamp, zlib.compress(raw, 6), len(raw)))

    def status(self, scope, identity=None):
        key = scope_key(scope, identity)
        totals=self.db.execute('SELECT n,stamp,raw,packed FROM ai_event_totals WHERE scope_key=?',
                               (key,)).fetchone()
        count,updated,raw,packed=totals or (0,None,0,0)
        return {'scope_id': key, 'records': count, 'updated_at': updated,
                'raw_bytes': raw, 'compressed_bytes': packed,
                'directory': str(self.folder / key), 'prompt_max_chars': self.max_chars,
                'compression': 'zlib JSON records + bounded prompt excerpts'}

    def update_manifest(self, scope, identity=None):
        status = self.status(scope, identity)
        directory = self.folder / status['scope_id']
        temporary = None
        try:
            directory.mkdir(parents=True, exist_ok=True)
            # The database is authoritative; this small sidecar is atomically
            # replaced on each successful translation. No source/secret fields.
            metadata = {key: value for key, value in status.items() if key != 'directory'}
            metadata.update(schema=1, database='../../' + self.database_name,
                            table='ai_context_events', timezone='Asia/Shanghai')
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=directory,
                                             prefix='.updated-', suffix='.tmp', delete=False) as handle:
                temporary = handle.name
                json.dump(metadata, handle, ensure_ascii=False, indent=2)
                handle.write('\n')
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, directory / 'updated.json')
            temporary = None
        except OSError:
            self.manifest_errors += 1
        finally:
            if temporary:
                try:
                    Path(temporary).unlink(missing_ok=True)
                except OSError:
                    pass
