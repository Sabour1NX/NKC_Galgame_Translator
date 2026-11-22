# SPDX-License-Identifier: MIT
"""Short, pixel-evidenced retention for text that dims at a stable position."""
from time import monotonic, perf_counter


def pixels(image, line):
    x,y,w,h=(line[k] for k in ('x','y','w','h'))
    if w*h>12288 or not (0<=x<x+w<=image.width and 0<=y<y+h<=image.height):
        return b''
    with image.crop((x,y,x+w,y+h)) as patch:
        return patch.tobytes()


def fading(original, current, background):
    """Every changing pixel must move toward background, with no new ink."""
    if not original or len(original)!=len(current) or original==current or len(background)!=3:
        return False
    changed=0
    for at in range(0,len(original),3):
        before,after=original[at:at+3],current[at:at+3]
        if before==after:
            continue
        v=[value-bg for value,bg in zip(before,background)]
        delta=[value-bg for value,bg in zip(after,background)]
        energy=sum(value*value for value in v)
        if max(map(abs,v))<22:
            if max(map(abs,delta))>14:
                return False
            continue
        alpha=sum(a*b for a,b in zip(delta,v))/energy
        if not -.12<=alpha<=1.08 or any(abs(a-alpha*b)>13 for a,b in zip(delta,v)):
            return False
        changed+=alpha<.82
    return changed>=8


class FlashHold:
    def __init__(self, timeout=.12):
        self.timeout=timeout
        self.anchors={}

    @staticmethod
    def key(row):
        return row['x'],row['y'],row['w'],row['h'],row['text']

    def recover(self, before, after, missing):
        """Admit a missing row only with same-position fade evidence."""
        now=monotonic()
        deadline_check=perf_counter()+.014
        keep=[]
        for row in missing:
            key=self.key(row)
            reference=self.anchors.pop(key,None)
            if perf_counter()>=deadline_check:
                continue
            if reference is None and len(self.anchors)<48 and not row.get('_flash_hold'):
                reference=(pixels(before,row),now+self.timeout)
            if reference is None:
                continue
            original,deadline=reference
            current=pixels(after,row)
            if original and current==original:
                restored=dict(row)
                restored.pop('_flash_hold',None)
                keep.append(restored)
            elif now<deadline and fading(original,current,row.get('bg',())):
                self.anchors[key]=reference
                keep.append({**row,'_flash_hold':True})
        return keep

    def expire(self,rows):
        now=monotonic()
        self.anchors={key:value for key,value in self.anchors.items() if now<value[1]}
        return [row for row in rows if not row.get('_flash_hold') or self.key(row) in self.anchors]
