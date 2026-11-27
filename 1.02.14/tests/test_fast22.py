from nkc_galgame_translator.frame_cache import FrameCache
from nkc_galgame_translator.translation import TranslationEngine
from concurrent.futures import ThreadPoolExecutor
import threading,time
import httpx

def test_exact_cache_checks_bytes_even_hash_collision_and_copies_nested_geometry():
    cache=FrameCache();key=('forced-collision',)
    cache.put(key,b'first',{'lines':[{'text':'one','_source_ink':[1,2,3,4]}]})
    assert cache.get(key,b'second') is None
    a=cache.get(key,b'first');a['lines'][0]['_source_ink'][0]=90
    assert cache.get(key,b'first')['lines'][0]['_source_ink'][0]==1

def test_exact_cache_evicts_by_memory_and_count_and_language_isolated():
    cache=FrameCache(max_bytes=2*1024*1024+10,max_entries=2)
    for n in range(3):cache.put(cache.key(bytes([n]),('en',)),bytes([n]),{'lines':[]})
    assert len(cache.entries)==2 and cache.bytes<=cache.max_bytes
    assert cache.get(cache.key(b'\0',('en',)),b'\0') is None
    assert cache.get(cache.key(b'\2',('ja',)),b'\2') is None
    cache.clear();assert cache.bytes==0 and not cache.entries

def test_shared_translation_streams_before_request_finishes(tmp_path,monkeypatch):
    entered=threading.Event();release=threading.Event();follower=threading.Event();calls=[]
    with TranslationEngine({'api_key':'synthetic-test','max_requests':2},tmp_path/'test.db',
                           client=httpx.Client(transport=httpx.MockTransport(lambda _:None))) as engine:
        def request(scope,masked,context,on_chunk):
            calls.append(1);on_chunk('\u6b22\u8fce');entered.set()
            assert release.wait(3);on_chunk('\u6b22\u8fce\u56de\u6765');return '\u6b22\u8fce\u56de\u6765'
        monkeypatch.setattr(engine,'_request',request)
        with ThreadPoolExecutor(2) as pool:
            first=pool.submit(engine.translate,'game','en','zh-Hans','Welcome back')
            try:
                assert entered.wait(2)
                def chunk(text):
                    if text=='\u6b22\u8fce':follower.set()
                second=pool.submit(engine.translate,'game','en','zh-Hans','Welcome back',chunk)
                assert follower.wait(2), 'Duplicate object waited until the final response'
                assert not first.done() and not second.done()
            finally:release.set()
            assert first.result() == second.result() == '\u6b22\u8fce\u56de\u6765'
        assert len(calls)==1 and not engine._flight_chunks

def test_confirmation_credits_ocr_time_only_with_second_frame_evidence():
    from nkc_galgame_translator.pipeline import Pipeline
    from nkc_galgame_translator.tracking import ObjectTracker
    class Engine:
        def translate(self,*a,**k):return '\u4f60\u597d'
    class Core:
        def hide_overlay(self):pass
    p=Pipeline(Core(),Engine(),lambda _:None,settle=1)
    p._scope=('g','en','zh-Hans','')
    lines=[{'text':'Welcome back','x':0,'y':0,'w':150,'h':24,'source_lang':'en'}]
    try:
        tracks=p.tracker.update(lines,origin=(0,0)).tracks
        p._apply_objects_locked(tracks,p.generation,captured_at=time.monotonic()-2)
        p._schedule();assert not p._inflight
        p._apply_objects_locked(tracks,p.generation,confirmation=True)
        p._schedule();assert len(p._inflight)==1
    finally:p.stop();p.join();p.pool.shutdown(wait=True)
