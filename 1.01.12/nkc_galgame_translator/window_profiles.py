# SPDX-License-Identifier: MIT
"""Recommend one window only when identity or profile text supplies evidence."""
from difflib import SequenceMatcher
import ntpath
import re
import unicodedata


def _title(value):
    return ' '.join(re.findall(r'\w+',unicodedata.normalize('NFKC',str(value or '')).casefold()))


def _exe(row):
    return ntpath.basename(row.get('process_path') or row.get('exe_name') or '').casefold()


def matching_window(rows,profile,previous=None):
    previous=previous if isinstance(previous,dict) else {}
    remembered_path=str(previous.get('process_path') or '').casefold()
    remembered_title=_title(previous.get('title'))
    remembered_exe=_exe(previous)
    name=_title(profile)
    aliases={_title(item) for item in re.findall('[\uff08(]([^()\uff08\uff09]+)[)\uff09]',profile)}
    ranked=[]
    for row in rows:
        title=_title(row.get('title'))
        exe=_exe(row)
        path=str(row.get('process_path') or '').casefold()
        # Windows can reuse a PID. Consider it only alongside recorded
        # executable identity or an unchanged title when no path is known.
        score=0.
        if remembered_path and path==remembered_path:
            score=5.
        elif remembered_exe and exe==remembered_exe and remembered_title and title:
            similarity=SequenceMatcher(None,remembered_title,title).ratio()
            if similarity>=.65:score=3.+similarity
        elif remembered_title and title==remembered_title:
            score=2.
        elif not previous and title and name:
            if title==name or (len(title)>=4 and (' '+title+' ') in ' '+name+' '):
                score=2.
            elif exe and _title(ntpath.splitext(exe)[0]) in aliases:
                score=1.5
        if score:
            if type(previous.get('pid')) is int and row['pid']==previous['pid']:
                score+=1.
            if remembered_title and title==remembered_title:
                score+=.4
            ranked.append((score,row))
    ranked.sort(key=lambda item:item[0],reverse=True)
    if not ranked or len(ranked)>1 and ranked[0][0]==ranked[1][0]:
        return None
    return ranked[0][1]
