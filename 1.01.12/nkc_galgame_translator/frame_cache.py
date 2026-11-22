# SPDX-License-Identifier: MIT
"""Bounded exact-image OCR memoization, never a translation cache."""
from collections import OrderedDict
from copy import deepcopy



class FrameCache:
    def __init__(self,max_bytes=128*1024*1024,max_entries=16):
        self.max_bytes=max_bytes;self.max_entries=max_entries
        self.entries=OrderedDict();self.bytes=0;self.hits=0;self.misses=0

    def key(self,pixels,scope):return scope,hash(pixels)

    def get(self,key,pixels):
        entry=self.entries.get(key)
        if entry is None or entry[0]!=pixels:
            self.misses+=1;return None
        self.hits+=1;self.entries.move_to_end(key)
        return deepcopy(entry[1])

    def put(self,key,pixels,result):
        # Keep RGB bytes to verify equality even if hashes collide. Include a
        # conservative result budget: output is capped to 64k OCR characters.
        charge=len(pixels)+1024*1024
        if charge>self.max_bytes:return
        previous=self.entries.pop(key,None)
        if previous:self.bytes-=previous[2]
        self.entries[key]=(pixels,deepcopy(result),charge);self.bytes+=charge
        while self.bytes>self.max_bytes or len(self.entries)>self.max_entries:
            _,entry=self.entries.popitem(last=False);self.bytes-=entry[2]

    def clear(self):self.entries.clear();self.bytes=0
