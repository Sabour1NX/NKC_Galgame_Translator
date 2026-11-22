# SPDX-License-Identifier: MIT
"""Static checks of the generated offline HTML manuals, not a browser render."""
from collections import Counter
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
import statistics
import math
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.ids=[];self.links=[];self.resources=[];self.scripts=0;self.articles=0
        self.feed(text)

    def handle_starttag(self, tag, attributes):
        attrs=dict(attributes)
        if 'id' in attrs:self.ids.append(attrs['id'])
        if tag=='a' and attrs.get('href'):self.links.append(attrs['href'])
        if tag=='script':self.scripts+=1
        if tag=='article':self.articles+=1
        for key in ('src','data','poster'):
            if attrs.get(key):self.resources.append(attrs[key])
        if tag=='link' and attrs.get('href'):self.resources.append(attrs['href'])


def main():
    files={}
    for name in ('PROJECT_MANUAL.html','PROJECT_MANUAL.en.html','PROJECT_GUIDE.html','PERFORMANCE_REPORT.html','PERFORMANCE_REPORT.en.html','CUSTOMER_GUIDE.html','CUSTOMER_GUIDE.en.html',
                 'teacher-review27/index.html','teacher-review27/performance.html','teacher-review27/performance.en.html','teacher-review27/gallery.html',
                 'teacher-review27/architecture.html','teacher-review27/manual.zh.html','teacher-review27/manual.en.html'):
        path=ROOT/'docs'/name;text=path.read_text(encoding='utf-8');parsed=Document(text)
        missing=[]
        for href in parsed.links:
            url=urlsplit(href)
            if url.scheme or url.netloc:continue
            target=(path.parent/unquote(url.path)).resolve() if url.path else path
            if not target.is_file():missing.append(href);continue
            if url.fragment and target.suffix.lower()=='.html':
                target_ids=parsed.ids if target==path else Document(target.read_text(encoding='utf-8')).ids
                if unquote(url.fragment) not in target_ids:missing.append(href)
        svgs=re.findall(r'<svg\b[\s\S]*?</svg>',text)
        for source in svgs:ET.fromstring(source)
        duplicate=sorted(value for value,count in Counter(parsed.ids).items() if count>1)
        remote=[value for value in parsed.resources if urlsplit(value).scheme not in ('','data') or value.startswith('//')]
        files[name]={'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                     'articles':parsed.articles,'svg':len(svgs),'duplicate_ids':duplicate,
                     'missing_links_or_fragments':missing,'scripts':parsed.scripts,
                     'remote_resources':remote,'svg_xml':'passed'}
    # The default performance entry must describe the current release, not just
    # link to a new report while embedding a historical chapter in the manual.
    version=json.loads((ROOT/'docs/UPDATE.json').read_text(encoding='utf-8'))['version']
    current=json.loads((ROOT/'docs/PERFORMANCE_REPORT.json').read_text(encoding='utf-8'))
    measurement=current.get('measurement_version',current.get('version'))
    entries={'default_report_distribution_current':current.get('distributed_with_version',current.get('version'))==version,
             'measurement_version_honest':current.get('version')==measurement and
                 (measurement==version or current.get('rebenchmarked') is False),
             'baseline_is_0.01.15':current.get('baseline')=='0.01.15'}
    for name in ('PERFORMANCE_REPORT.md','en/PERFORMANCE_REPORT.md'):
        entries[name]=version in (ROOT/'docs'/name).read_text(encoding='utf-8').splitlines()[0]
    for name in ('PROJECT_MANUAL.html','PROJECT_MANUAL.en.html'):
        text=(ROOT/'docs'/name).read_text(encoding='utf-8')
        chapter=re.search(r'<article id="p-performance-report">([\s\S]*?)</article>',text)
        heading=re.search(r'<h1\b[^>]*>([\s\S]*?)</h1>',chapter[1]) if chapter else None
        entries[name+' current performance chapter']=bool(heading and version in heading[1])
        entries[name+' context layer chapter']='id="p-context-agent"' in text
        entries[name+' complete chapter count']=Document(text).articles==18
        entries[name+' current harness contracts']=('ContextAgent' in text and 'font_peers' in text and 'vision_anchors' in text)
        entries[name+' current CUDA/background contracts']=all(token in text for token in
            ('cuda_quality','cuda_memory_mb','pixel_priority','PP-OCRv6-small','ContextAgent.peek','lines[].drawable'))
    for name in ('PERFORMANCE_REPORT.html','PERFORMANCE_REPORT.en.html'):
        text=(ROOT/'docs'/name).read_text(encoding='utf-8')
        title=re.search(r'<title>([\s\S]*?)</title>',text)
        entries[name+' current title']=bool(title and version in title[1])
        if measurement!=version:
            entries[name+' previous measurement notice']=f'data-release-measurement="{measurement}"' in text
        entries[name+' separate current evidence']=all(token in text for token in
            ('id="ocr"','id="accuracy"','needy-caution-full.png','0.01.15','0.01.27'))
        if name=='PERFORMANCE_REPORT.html':
            heading=re.search(r'<h1\b[^>]*>([\s\S]*?)</h1>',text)
            entries['approved_customer_headline']=bool(heading and re.sub(r'<[^>]+>','',heading[1])=='\u54c1\u8d28\u7684\u4f53\u9a8c\uff0c\u66f4\u5c11\u7684\u7b49\u5f85')
    fresh=current.get('offline_ocr',{})
    entries['fresh_paired_comparison']=fresh.get('comparison')==['0.01.15',version] and current.get('rebenchmarked') is True
    entries['offline_requests_zero']=fresh.get('network_used') is False and fresh.get('api_calls')==0
    entries['all_measured_scenes_have_separate_distributions']=all(
        all(s.get(k,{}).get('samples_ms') and len(s[k]['samples_ms'])==s[k]['n'] for k in
            ('cold_constructor_plus_first','warm_revisit','warm_changed_background'))
        and s.get('changed_frame_cache_hits')==0 and s.get('accuracy',{}).get('characters',0)>0
        for release in fresh.get('versions',{}).values() for s in release.get('scenes',{}).values())
    entries['both_versions_four_paired_scenes']=set(fresh.get('versions',{}))=={'0.01.15',version} and all(
        set(release.get('scenes',{}))=={'spacerogue-game.png','status.png','cargo.png','needy-caution-full.png'}
        for release in fresh.get('versions',{}).values())
    entries['statistics_recompute_from_raw_samples']=all(
        math.isclose(d['median_ms'],statistics.median(d['samples_ms']),abs_tol=1e-7)
        and math.isclose(d['min_ms'],min(d['samples_ms']),abs_tol=1e-7)
        and math.isclose(d['max_ms'],max(d['samples_ms']),abs_tol=1e-7)
        for release in fresh.get('versions',{}).values() for s in release.get('scenes',{}).values()
        for k in ('cold_constructor_plus_first','warm_revisit','warm_changed_background') for d in [s[k]])
    entries['teacher_manuals_have_all_18_chapters']=all(files['teacher-review27/'+name]['articles']==18 for name in ('manual.zh.html','manual.en.html'))
    entries['data_schema_is_current']=current.get('schema')==3
    real=current.get('real_api')
    if real and real.get('samples'):
        entries['real_api_callbacks_not_presentation']=real.get('native_paint_measured') is False and real.get('source_crop_box') is None and all(s.get('first_native_paint_ms') is None for s in real['samples'])
        entries['real_api_requests_preserved']=real.get('total_session_requests')==sum(s.get('session_requests',0) for s in real['samples'])
        entries['real_api_same_source_confirmed']=real.get('source_text_identical_across_samples') is True
        entries['real_api_statistics_recompute']=all(math.isclose(x['median_ms'],statistics.median(x['samples_ms']),abs_tol=1e-7) for v in real['versions'].values() for x in v.values())
    passed=all(entries.values()) and all(not any(value[key] for key in ('duplicate_ids','missing_links_or_fragments','scripts','remote_resources')) for value in files.values())
    report={'version':version,'measurement_version':measurement,'method':'HTML parser, local links and SVG XML; no browser render',
            'visual_rendered':False,'files':files,'current_performance_entries':entries,'status':'passed' if passed else 'failed'}
    (ROOT/'reports').mkdir(exist_ok=True)
    (ROOT/'reports/manual-html-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
