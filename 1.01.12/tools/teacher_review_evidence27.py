# SPDX-License-Identifier: MIT
"""Measured-data adapter for build_teacher_review27; no requests or private files."""
import hashlib
import io
import json
from pathlib import Path
import re

SCENES=['spacerogue-game.png','status.png','cargo.png','needy-caution-full.png']
LABELS=['Space Rogue / story','Space Rogue / status','Space Rogue / cargo','NEEDY / Japanese']
VERSIONS=('0.01.15','0.01.27')

def plots(h,data,kind):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'svg.fonttype':'none','svg.hashsalt':'teacher-review27',
        'axes.spines.top':False,'axes.spines.right':False,'axes.spines.left':False,
        'axes.edgecolor':'#cedbd5','axes.labelcolor':'#426065','text.color':'#18333e',
        'xtick.color':'#536b70','ytick.color':'#536b70','figure.facecolor':'white'})
    if kind=='accuracy':
        fig,ax=plt.subplots(figsize=(11.6,4.6),layout='constrained')
        for vi,version in enumerate(VERSIONS):
            values=[data['versions'][version]['scenes'][s]['accuracy']['character_accuracy_percent'] for s in SCENES]
            y=[i+(vi-.5)*.28 for i in range(4)]
            ax.barh(y,values,height=.25,color=('#9baeb8','#008e81')[vi],label=version)
            for yy,value in zip(y,values):ax.text(min(value+1,101),yy,f'{value:.2f}%',va='center',fontsize=9)
        ax.set(yticks=range(4),yticklabels=LABELS,xlim=(0,113),xlabel='Character transcription accuracy (%) · full 0–100% scale')
        ax.invert_yaxis();ax.grid(axis='x',alpha=.13);ax.set_axisbelow(True);ax.legend(loc='lower right',frameon=False)
        ax.set_title('Same images, same labelled zones · default auto routing',loc='left',pad=18,fontweight='bold')
    else:
        keys=['cold_constructor_plus_first','warm_changed_background','warm_revisit']
        titles=['Cold: construction + first OCR','Warm: background changed, text unchanged','Identical-image revisit (cache eligible)']
        fig,axes=plt.subplots(3,1,figsize=(11.6,12.0),layout='constrained')
        for ax,key,title in zip(axes,keys,titles):
            largest=0
            for vi,version in enumerate(VERSIONS):
                color=('#9baeb8','#008e81')[vi]
                for si,scene in enumerate(SCENES):
                    values=data['versions'][version]['scenes'][scene][key]
                    y=si+(vi-.5)*.24;factor=1000 if key==keys[0] else 1
                    raw=[x/factor for x in values['samples_ms']];median=values['median_ms']/factor
                    largest=max(largest,max(raw));ax.plot([min(raw),max(raw)],[y,y],color=color,lw=2,alpha=.6)
                    ax.scatter(raw,[y]*len(raw),s=21,color=color,alpha=.65,zorder=3)
                    ax.scatter([median],[y],s=75,marker='|',color='#142f38',zorder=4)
                    ax.annotate(f'{median:.3f}',(median,y),xytext=(4,-12 if vi else 8),textcoords='offset points',fontsize=8,color=color)
                ax.plot([],[],color=color,marker='o',lw=1,label=version)
            ax.set(yticks=range(4),yticklabels=LABELS,xlim=(0,largest*1.09),xlabel='seconds · all raw values' if key==keys[0] else 'milliseconds · all raw values')
            ax.invert_yaxis();ax.grid(axis='x',alpha=.14);ax.set_axisbelow(True)
            ax.set_title(title,loc='left',pad=16,fontweight='bold');ax.legend(loc='lower right',frameon=False)
    buffer=io.StringIO();fig.savefig(buffer,format='svg',metadata={'Date':None});plt.close(fig)
    svg=buffer.getvalue();svg=svg[svg.index('<svg'):]
    for value in sorted(set(re.findall(r'\bid="([^"]+)"',svg)),key=len,reverse=True):
        svg=svg.replace('id="'+value+'"','id="'+kind+'-'+value+'"').replace('#'+value+'"','#'+kind+'-'+value+'"').replace('#'+value+')','#'+kind+'-'+value+')')
    h.write(h.OUT/(kind+'.svg'),svg)
    return '<div class="chart">'+svg+'</div>'

def image_evidence(h,data,english=False):
    pieces=[]
    for index,scene in enumerate(SCENES):
        path=(h.EVIDENCE/data['source_images'][scene]).resolve()
        if not path.is_relative_to(h.EVIDENCE.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=data['versions'][VERSIONS[1]]['scenes'][scene]['image_sha256']:
            raise ValueError('Fixture hash mismatch '+scene)
        width,height=data['versions'][VERSIONS[1]]['scenes'][scene]['image_size'];gap=22;image_id='fixture-'+str(index)
        canvas=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width*2+gap} {height+48}" role="img" aria-label="Same input, OCR rectangles by release"><defs><image id="{image_id}" width="{width}" height="{height}" href="'+h.uri(path)+'"/></defs>'
        for vi,version in enumerate(VERSIONS):
            record=data['versions'][version]['scenes'][scene];offset=vi*(width+gap)
            canvas+=f'<text x="{offset}" y="28" font-size="22" fill="#18333e">{h.esc(version)} · {h.esc(record["engine"])}</text><g transform="translate({offset},48)"><use href="#{image_id}"/>'
            for zone in record['accuracy']['zones']:
                x1,y1,x2,y2=zone['box'];canvas+=f'<rect x="{x1}" y="{y1}" width="{x2-x1}" height="{y2-y1}" fill="none" stroke="#ffde59" stroke-width="3" stroke-dasharray="9 6"/>'
            for line in record['lines']:
                canvas+=f'<rect x="{line["x"]}" y="{line["y"]}" width="{line["w"]}" height="{line["h"]}" fill="#00e7bc" fill-opacity=".08" stroke="#00e7bc" stroke-width="2"><title>{h.esc(line["text"])}</title></rect>'
            canvas+='</g>'
        canvas+='</svg>';rows=[]
        left=data['versions'][VERSIONS[0]]['scenes'][scene];right=data['versions'][VERSIONS[1]]['scenes'][scene]
        for zid,(a,b) in enumerate(zip(left['accuracy']['zones'],right['accuracy']['zones']),1):
            rows.append([str(zid)+' · '+h.esc(a['box']),'<pre>'+h.esc(a['expected'])+'</pre>','<pre>'+h.esc(a['actual'] or '[empty]')+'</pre>','<pre>'+h.esc(b['actual'] or '[empty]')+'</pre>'])
        caption='Source / OCR rectangles / exact transcription evidence' if english else '\u539f\u56fe / OCR\u6846 / \u9010\u533a\u6587\u5b57\u8bc1\u636e'
        note='Green solid rectangles are actual OCR boxes; yellow dashes are scoring zones. Both sides use the same input, crop and scale. These are source transcriptions, not translated overlays. Hover a box to read its text.' if english else '\u7eff\u8272\u5b9e\u7ebf\uff1a\u5b9e\u9645OCR\u6846\uff1b\u9ec4\u8272\u865a\u7ebf\uff1a\u8bc4\u5206\u533a\u3002\u4e24\u4fa7\u539f\u56fe\u3001\u88c1\u5207\u4e0e\u7f29\u653e\u76f8\u540c\u3002\u8fd9\u662f\u539f\u6587\u8bc6\u522b\u7ed3\u679c\uff0c\u4e0d\u662f\u4e2d\u6587\u8bd1\u6587\u3002\u60ac\u505c\u6846\u53ef\u8bfb\u6587\u5b57\u3002'
        headers=['Scoring zone','Manual source truth','0.01.15 auto output','0.01.27 auto output'] if english else ['\u4eba\u5de5\u8bc4\u5206\u533a','\u4eba\u5de5\u539f\u6587','0.01.15 auto \u5b9e\u9645\u8f93\u51fa','0.01.27 auto \u5b9e\u9645\u8f93\u51fa']
        pieces.append('<details id="evidence-'+Path(scene).stem+'"><summary>'+h.esc(scene)+' · '+caption+'</summary><p>'+note+'</p><div class="chart">'+canvas+'</div>'+h.table(headers,rows)+'<p class="meta">SHA256 '+h.esc(left['image_sha256'])+'</p></details>')
    return ''.join(pieces)

def e2e_markdown(data,english=False):
    if not data or not data.get('samples'):
        return ('No completed fresh real-API sample is currently recorded. This is an unmeasured stage, not zero latency.' if english else '\u672c\u6b21\u5c1a\u65e0\u5df2\u5b8c\u6210\u771f\u5b9eAPI\u6837\u672c\uff1b\u6b64\u9879\u4e3a\u672a\u6d4b\uff0c\u4e0d\u662f\u96f6\u5ef6\u8fdf\u3002')+'\n'
    lines=[('The complete Space Rogue source image is loaded before timing and sent through each release\'s actual pixel OCR. A declared test adapter selects only the left story region [0,70,450,440] for tracking and a real streaming API request. The image is not cropped. Timing starts immediately before pipeline.start and ends when translation callbacks are consumed from the event queue. No visible window or overlay is used; capture, painting, web context, AI vision and DWM/monitor presentation are excluded. Native-paint times are null, not zero.' if english else '\u8ba1\u65f6\u524d\u8f7d\u5165\u5b8c\u6574Space Rogue\u539f\u56fe\uff0c\u5148\u7ecf\u8fc7\u5404\u7248\u672c\u5b9e\u9645Pixel OCR\uff1b\u6d4b\u8bd5\u9002\u914d\u5c42\u968f\u540e\u53ea\u9009\u53d6\u5de6\u4fa7\u5267\u60c5region[0,70,450,440]\u8fdb\u5165\u8ffd\u8e2a\u548c\u771f\u5b9e\u6d41\u5f0fAPI\u3002\u539f\u56fe\u6ca1\u6709\u88c1\u5207\u3002\u8d77\u70b9\u4e3apipeline.start\u4e4b\u524d\uff0c\u7ec8\u70b9\u4e3a\u8bd1\u6587\u56de\u8c03\u88ab\u4e8b\u4ef6\u961f\u5217\u6d88\u8d39\u3002\u4e0d\u663e\u793a\u7a97\u53e3\u6216\u53e0\u5c42\uff0c\u4e0d\u542b\u6355\u83b7\u3001\u7ed8\u5236\u3001\u8054\u7f51\u8bed\u5883\u3001AI\u56fe\u50cf\u7cbe\u8bfb\u3001DWM\u6216\u663e\u793a\u5668\u5448\u73b0\u3002\u539f\u751f\u7ed8\u5236\u65f6\u95f4\u4e3anull\u672a\u6d4b\uff0c\u4e0d\u80fd\u8bb0\u4e3a\u96f6\u3002'),'']
    lines+=['| Pair | Version | Result | First callback ms | Final callback ms | Requests |','|---|---|---|---:|---:|---:|']
    for s in data['samples']:
        fmt=lambda k:f'{s[k]:.3f}' if isinstance(s.get(k),(float,int)) else 'not completed'
        lines.append(f'| {s["pair"]} | {s["version"]} | {"complete" if s.get("success") else "failed"} | {fmt("first_callback_ms")} | {fmt("complete_ms")} | {s.get("session_requests")} |')
    lines+=['',('Release defaults for stabilization and polling are retained. Observation tick is 40ms in .15 and 16ms in .27. Prompts also differ (229 versus 258 input tokens). Sequential provider/network variation is uncontrolled; these few pairs are descriptive, not a statistically established provider speedup. Pair3 final callback is slower in .27: 1982.674ms versus 1863.335ms. This is a fixed-image real-API callback test, not native painting or a running-game overlay certification.' if english else '\u4fdd\u7559\u4e24\u7248\u9ed8\u8ba4\u7a33\u5b9a\u7b49\u5f85\u4e0e\u8f6e\u8be2\u8bbe\u7f6e\uff1b\u89c2\u5bdftick\u4e3a.15\u768440ms\u3001.27\u768416ms\uff0c\u63d0\u793a\u4e5f\u4e0d\u540c\uff08\u8f93\u5165token229/258\uff09\u3002\u987a\u5e8f\u7f51\u7edc/\u670d\u52a1\u5546\u6ce2\u52a8\u672a\u53d7\u63a7\uff0c\u5c11\u91cf\u914d\u5bf9\u53ea\u63cf\u8ff0\u672c\u7ec4\u89c2\u6d4b\uff0c\u4e0d\u6784\u6210\u7edf\u8ba1\u786e\u7acb\u7684\u670d\u52a1\u5546\u52a0\u901f\u3002\u7b2c3\u5bf9\u65b0\u7248\u5b8c\u6574\u56de\u8c03\u66f4\u6162\uff1a1982.674ms\uff0c\u5bf9\u7167\u72481863.335ms\u3002\u8fd9\u662f\u56fa\u5b9a\u56fe\u7247\u771f\u5b9eAPI\u56de\u8c03\u6d4b\u8bd5\uff0c\u4e0d\u662f\u539f\u751f\u7ed8\u5236\u6216\u8fd0\u884c\u4e2d\u6e38\u620f\u8986\u76d6\u8ba4\u8bc1\u3002'),'']
    lines+=['| Version | Poll interval ms | Settle ms | Observation tick ms | Model |','|---|---:|---:|---:|---|']
    for version in VERSIONS:
        first=next((s for s in data['samples'] if s['version']==version),None)
        if first:lines.append(f'| {version} | {first.get("capture_interval_ms")} | {first.get("settle_ms")} | {40 if version==VERSIONS[0] else 16} | {first.get("model")} |')
    lines+=['',('Total actual session requests: ' if english else '\u672c\u7ec4\u5b9e\u9645\u4f1a\u8bdd\u8bf7\u6c42\u6570\uff1a')+str(data.get('total_session_requests','not recorded'))+'.','']
    if data.get('source_text_identical_across_samples') is True:
        lines+=[('All six source-text hashes match. Provider/model response variation and version-specific prompts remain part of this system-level observation.' if english else '6\u4e2a\u6837\u672c\u7684\u6e90\u6587\u5b57\u4e32SHA\u4e00\u81f4\u3002\u670d\u52a1\u5546/\u6a21\u578b\u8f93\u51fa\u6ce2\u52a8\u4e0e\u7248\u672c\u63d0\u793a\u5dee\u5f02\u4ecd\u7136\u5c5e\u4e8e\u672c\u6b21\u7cfb\u7edf\u7ea7\u89c2\u6d4b\u7684\u4e00\u90e8\u5206\u3002'),'']
    token_rows=['| Pair / version | Prompt tokens | Completion tokens |','|---|---:|---:|']
    for s in data['samples']:
        token_rows.append(f'| {s["pair"]} / {s["version"]} | {s.get("prompt_tokens","not recorded")} | {s.get("completion_tokens","not recorded")} |')
    if any('prompt_tokens' in s for s in data['samples']):lines+=token_rows+['']
    return '\n'.join(lines)

def e2e_section(h,english=False):
    data=h.load(h.EVIDENCE/'e2e-summary.json')
    body=h.MD.render(e2e_markdown(data,english))
    if not data or not data.get('samples'):return body
    summary_rows=[]
    for version,metrics in data.get('versions',{}).items():
        for key,label in [('first_callback_ms','First callback'),('complete_ms','Final callback')]:
            x=metrics.get(key)
            if x:summary_rows.append([version,label,str(x['n']),f'{x["median_ms"]:.3f}',f'{x["min_ms"]:.3f}–{x["max_ms"]:.3f}'])
    body+=h.table(['Version','Observed endpoint','n','Median ms','Full range ms'],summary_rows)
    import matplotlib.pyplot as plt
    samples=[s for s in data['samples'] if s.get('success')]
    if samples:
        fig,ax=plt.subplots(figsize=(11.6,max(3.4,len(samples)*.55)),layout='constrained')
        keys=['first_callback_ms','complete_ms'];colors=['#008e81','#193641'];markers=['o','D']
        for i,s in enumerate(samples):
            values=[s[k]/1000 for k in keys];ax.plot(values,[i]*2,color='#c1d1d1',lw=3,zorder=1)
            for k,(value,color,marker) in enumerate(zip(values,colors,markers)):
                ax.scatter([value],[i],color=color,marker=marker,s=54,zorder=2,label=['First callback','Final callback'][k] if i==0 else None)
        ax.set(yticks=range(len(samples)),yticklabels=[f'Pair {s["pair"]} / {s["version"]}' for s in samples],xlim=(0,max(s['complete_ms']/1000 for s in samples)*1.09),xlabel='seconds since pipeline.start · full observed range')
        ax.invert_yaxis();ax.grid(axis='x',alpha=.14);ax.set_axisbelow(True);ax.legend(loc='upper center',bbox_to_anchor=(.5,1.2),ncols=3,frameon=False)
        b=io.StringIO();fig.savefig(b,format='svg',metadata={'Date':None});plt.close(fig);svg=b.getvalue();svg=svg[svg.index('<svg'):]
        for value in sorted(set(re.findall(r'\bid="([^"]+)"',svg)),key=len,reverse=True):
            svg=svg.replace('id="'+value+'"','id="e2e-'+value+'"').replace('#'+value+'"','#e2e-'+value+'"').replace('#'+value+')','#e2e-'+value+')')
        h.write(h.OUT/'e2e.svg',svg);body='<div class="chart">'+svg+'</div>'+body
    body+='<p><a href="e2e.json">'+('All real-API observations and limitations' if english else '\u5b8c\u6574\u771f\u5b9eAPI\u89c2\u6d4b\u3001\u8bf7\u6c42\u6570\u53ca\u9650\u5236JSON')+'</a></p>'
    h.write(h.OUT/'e2e.json',json.dumps(data,ensure_ascii=False,indent=2))
    return body

def markdown(data,english=False,e2e=None):
    if not data:return '# \u4e8c\u8272\u8776 0.01.27 · \u6027\u80fd\u4e0e\u8bc6\u522b\u62a5\u544a\n\n\u65b0\u6d4b\u91cf\u5c1a\u672a\u5b8c\u6210\u3002\n'
    lines=['# Nishokuchou 0.01.27 · Fresh performance evidence' if english else '# \u4e8c\u8272\u8776 0.01.27 · \u6027\u80fd\u4e0e\u8bc6\u522b\u62a5\u544a','',
      '**A better experience. Less waiting.**' if english else '**\u54c1\u8d28\u7684\u4f53\u9a8c\uff0c\u66f4\u5c11\u7684\u7b49\u5f85**','',
      'Fresh comparison with 0.01.15, measured '+data['measured_at']+'. These are image-to-OcrCore results, not translation latency.' if english else '\u56fa\u5b9a\u57fa\u7ebf **0.01.15**\uff0c\u5f53\u524d **0.01.27**\u3002\u672c\u6b21\u6d4b\u91cf '+data['measured_at']+'\u3002\u4ee5\u4e0b\u662f\u56fe\u7247\u8fdb\u5165 OcrCore \u5230\u672c\u5730\u8bc6\u522b\u7ed3\u679c\uff0c**\u4e0d\u662f\u7ffb\u8bd1\u7aef\u5230\u7aef\u5ef6\u8fdf**\u3002','',
      '## Scope and protocol' if english else '## \u8303\u56f4\u4e0e\u65b9\u6cd5','',
      'Three alternating-order rounds; each scene/release uses a fresh worker, three cold samples total and 15 samples per warm path. Cold includes constructor/native/helper/model initialization; excludes Python startup and file loading; OS file cache is not flushed. Changed background means one corner pixel changes and text stays unchanged: whole-frame misses are asserted, subregion caches remain eligible. Cache revisits are separate.' if english else '3\u8f6e\u4ea4\u66ff\u7248\u672c\u987a\u5e8f\uff0c\u6bcf\u4e2a\u573a\u666f/\u7248\u672c\u72ec\u7acbworker\uff0c\u51713\u4e2a\u51b7\u6837\u672c\u3001\u6bcf\u6761\u70ed\u8def\u5f8415\u4e2a\u6837\u672c\u3002\u51b7\u542f\u52a8\u542b\u6784\u9020\u3001\u539f\u751f/helper/\u6a21\u578b\u521d\u59cb\u5316\uff1b\u4e0d\u542bPython\u542f\u52a8\u548c\u539f\u56fe\u8bfb\u53d6\uff0c\u672a\u6e05\u7a7aOS\u6587\u4ef6\u7f13\u5b58\u3002\u80cc\u666f\u53d8\u5316\u53ea\u6539\u53d8\u89d2\u843d1\u50cf\u7d20\u3001\u6b63\u6587\u4e0d\u53d8\uff1a\u6574\u5e27\u7f13\u5b58\u65ad\u8a00\u672a\u547d\u4e2d\uff0c\u4f46\u5141\u8bb8\u5c40\u90e8\u7f13\u5b58\u3002\u539f\u56fe\u590d\u8bbf\u53e6\u5217\uff0c\u4e0d\u80fd\u89c6\u4e3a\u65b0\u6587\u672c\u8bc6\u522b\u3002','',
      'Actual auto routing: .15 default CPU paths; .27 CUDA enabled at quality 75, 1024 MiB, with classic English pixel-frame CPU priority. This is a product/system comparison, not an isolated GPU-vs-CPU algorithm experiment. UI capture ran concurrently; the NEEDY cold maximum of 21.886 s is retained, without causal attribution.' if english else '\u5b9e\u9645auto\u4ea7\u54c1\u8def\u5f84\uff1a.15\u9ed8\u8ba4CPU\u8def\u7531\uff1b.27\u542f\u7528CUDA\u3001\u8d28\u91cf75\u3001\u9884\u7b971024MiB\uff0c\u7ecf\u5178\u82f1\u8bed\u50cf\u7d20\u753b\u9762\u4f18\u5148CPU\u3002\u8fd9\u662f\u7cfb\u7edf\u5bf9\u7167\uff0c\u4e0d\u80fd\u89e3\u91ca\u4e3a\u76f8\u540c\u7b97\u6cd5\u7684\u7eafGPU\u52a0\u901f\u3002\u6d4b\u8bd5\u671f\u95f4\u6709\u5e76\u884cUI\u622a\u56fe\u8d1f\u8f7d\uff1b\u4fdd\u7559NEEDY\u51b7\u542f\u52a8\u6700\u592721.886\u79d2\uff0c\u4e0d\u81c6\u65ad\u539f\u56e0\u3002','',
      '| Scene | Version / backend | Cold median ms | Changed-background median ms | Identical revisit ms | Character accuracy |','|---|---|---:|---:|---:|---:|']
    for scene in SCENES:
        for version in VERSIONS:
            s=data['versions'][version]['scenes'][scene]
            lines.append(f'| {scene} | {version} / {s["engine"]} | {s["cold_constructor_plus_first"]["median_ms"]:.3f} | {s["warm_changed_background"]["median_ms"]:.3f} | {s["warm_revisit"]["median_ms"]:.3f} | {s["accuracy"]["character_accuracy_percent"]:.3f}% |')
    lines+=['','## Accuracy and tradeoffs' if english else '## \u7cbe\u5ea6\u4e0e\u53d6\u820d','',
      'Accuracy is 100 × (1 − Levenshtein edits / labelled characters), with NFKC, whitespace removal and curly-quote normalization; case remains significant. It measures source transcription, not translation meaning. Space Rogue (356 characters) default-auto changes 81.461% → 95.506%; the separate forced-pixel .15 control is 83.989%. NEEDY (248 characters): .15 auto 1.613%, .27 CPU-only control 57.661%, .27 CUDA auto 98.387%. The .15 Windows Japanese OCR control fails because that language is absent; failure is not scored as zero accuracy.' if english else '\u51c6\u786e\u7387=100×\uff081−Levenshtein\u7f16\u8f91\u5dee\u5f02/\u6807\u6ce8\u5b57\u7b26\u6570\uff09\uff0c\u505aNFKC\u3001\u53bb\u7a7a\u767d\u548c\u5f2f\u5f15\u53f7\u89c4\u8303\u5316\uff0c\u533a\u5206\u5927\u5c0f\u5199\uff1b\u8bc4\u4ef7\u539f\u6587\u8f6c\u5f55\uff0c\u4e0d\u8bc4\u4ef7\u7ffb\u8bd1\u8bed\u4e49\u3002Space Rogue\u5171356\u5b57\uff1a\u9ed8\u8ba4auto 81.461%→95.506%\uff1b\u53e6\u5217.15\u5f3a\u5236pixel\u4e3a83.989%\u3002NEEDY248\u5b57\uff1a.15 auto 1.613%\uff0c.27\u5173\u95edCUDA\u5bf9\u716757.661%\uff0c.27 CUDA auto 98.387%\u3002.15 Windows\u65e5\u8bedOCR\u56e0\u7f3a\u8bed\u8a00\u529f\u80fd\u5931\u8d25\uff0c\u5931\u8d25\u4e0d\u8bb0\u4f5c\u96f6\u51c6\u786e\u7387\u3002','',
      'More accurate paths can cost more: Status changed-background median rises from 23.722 to 205.891 ms and cold CUDA initialization is slower. The story scene keeps 98.347% accuracy. Cache speedups and single quality settings are not universal performance promises.' if english else '\u66f4\u51c6\u786e\u7684\u8def\u5f84\u53ef\u80fd\u66f4\u6162\uff1aStatus\u80cc\u666f\u53d8\u5316\u4e2d\u4f4d\u753123.722\u589e\u81f3205.891ms\uff0cCUDA\u9996\u6b21\u521d\u59cb\u5316\u4e5f\u66f4\u6162\uff1b\u6545\u4e8b\u573a\u666f\u7cbe\u5ea6\u4ecd\u4e3a98.347%\u3002\u7f13\u5b58\u6536\u76ca\u548c\u67d0\u4e00\u8d28\u91cf\u6863\u4f4d\u4e0d\u80fd\u4ee3\u8868\u6240\u6709\u65b0\u6587\u672c\u901f\u5ea6\u6216\u51c6\u786e\u7387\u3002','',
      '## Real API callbacks and unmeasured display' if english else '## \u771f\u5b9eAPI\u56de\u8c03\u4e0e\u672a\u6d4b\u663e\u793a\u73af\u8282','',
      'The offline OCR comparison makes zero API requests and excludes capture, cloud transcription, translation, SSE and presentation. Fresh real-API observations are scoped separately. Historical .25 observations or simulated SSE are not substituted.' if english else '\u79bb\u7ebfOCR\u5bf9\u7167API\u8bf7\u6c42\u4e3a0\uff0c\u4e0d\u542b\u6355\u83b7\u3001\u4e91\u7aef\u7cbe\u8bfb\u3001\u7ffb\u8bd1\u3001SSE\u548c\u663e\u793a\u3002\u65b0\u771f\u5b9eAPI\u89c2\u6d4b\u72ec\u7acb\u6ce8\u660e\u8303\u56f4\uff0c\u4e0d\u7528\u5386\u53f2.25\u6570\u636e\u6216\u6a21\u62dfSSE\u586b\u8865\u3002','',e2e_markdown(e2e,english),'',
      '## GPU controls and limits' if english else '## GPU\u63a7\u4ef6\u4e0e\u8fb9\u754c','',
      'Quality 0–100 (default 75) sets the detector resolution cap, quantized to 32 pixels; small images may be equivalent and accuracy is not monotonic. Memory 256–16384 MiB (default 1024) budgets detector/recognizer arenas, not all process/driver allocations. Auto supports CUDA en/ja/zh with CPU priority for classic English pixel frames; manual Windows/Pixel modes stay on CPU. A model score of 95 is not a measured 95% accuracy promise.' if english else '\u8d28\u91cf0–100\uff08\u9ed8\u8ba475\uff09\u8bbe\u68c0\u6d4b\u5206\u8fa8\u7387\u4e0a\u9650\u3001\u630932\u50cf\u7d20\u91cf\u5316\uff1b\u5c0f\u56fe\u53ef\u80fd\u7b49\u6548\uff0c\u7cbe\u5ea6\u4e0d\u4fdd\u8bc1\u5355\u8c03\u3002\u663e\u5b58256–16384MiB\uff08\u9ed8\u8ba41024\uff09\u662f\u68c0\u6d4b/\u8bc6\u522barena\u9884\u7b97\uff0c\u4e0d\u80fd\u7ea6\u675f\u8fdb\u7a0b/\u9a71\u52a8\u5168\u90e8\u5206\u914d\u3002Auto\u652f\u6301CUDA en/ja/zh\u4f46\u7ecf\u5178\u82f1\u8bed\u50cf\u7d20\u753b\u9762\u4f18\u5148CPU\uff1bWindows/Pixel\u6a21\u5f0f\u8d70CPU\u3002\u6a21\u578b\u5206\u657095\u4e0d\u662f\u5b9e\u6d4b\u51c6\u786e\u738795%\u3002','',
      '[Full plots, distributions and same-image OCR evidence](../PERFORMANCE_REPORT.en.html)' if english else '[\u5b8c\u6574\u56fe\u8868\u3001\u5206\u5e03\u4e0e\u540c\u56fe\u8bc6\u522b\u8bc1\u636e](PERFORMANCE_REPORT.html)','',
      '[Teacher review portal](../teacher-review27/index.html)' if english else '[\u8bc4\u5ba1\u5165\u53e3\uff1a\u624b\u518c\u3001\u7ed3\u6784\u3001\u5b8c\u6574UI\u56fe\u5e93](teacher-review27/index.html)','']
    return '\n'.join(lines)

def render(h,data):
    if not data:return None
    body=h.hero('FRESH MEASUREMENTS / 0.01.15 → 0.01.27','\u54c1\u8d28\u7684\u4f53\u9a8c\uff0c<br>\u66f4\u5c11\u7684\u7b49\u5f85','\u56fa\u5b9a\u57fa\u7ebf0.01.15\uff0c\u4e0e\u5f53\u524d0.01.27\u6bd4\u8f83\u3002\u5148\u770b\u8303\u56f4\uff0c\u518d\u770b\u5404\u8f6e\u503c\uff1b\u51b7\u542f\u52a8\u3001\u7f13\u5b58\u548c\u80cc\u666f\u53d8\u5316\u70ed\u8def\u5f84\u4e0d\u5408\u6210\u4e00\u4e2a\u52a0\u901f\u500d\u6570\u3002')
    body+='<section id="method"><h2>\u5148\u754c\u5b9a\u95ee\u9898\uff0c\u518d\u6bd4\u8f83\u6570\u5b57</h2>'+h.table(['\u8def\u5f84','\u6d4b\u91cf\u5b9a\u4e49','\u89e3\u91ca\u8fb9\u754c'],[
      ['\u51b7\u542f\u52a8','\u6784\u9020+\u7b2c\u4e00\u6b21OcrCore\u7ed3\u679c','\u542b\u539f\u751f/helper/\u6a21\u578b\uff1b\u4e0d\u542bPython\u542f\u52a8\u3001\u539f\u56fe\u6587\u4ef6\u8bfb\u53d6'],['\u80cc\u666f\u53d8\u5316\u70ed\u8def\u5f84','\u552f\u4e00\u89d2\u843d1\u50cf\u7d20\u53d8\u5316\u3001\u6b63\u6587\u4e0d\u53d8','\u6574\u5e27\u672a\u547d\u4e2d\uff1b\u5141\u8bb8\u5c40\u90e8\u7f13\u5b58\uff1b\u975e\u4efb\u610f\u65b0\u6587\u672c'],['\u539f\u56fe\u590d\u8bbf','\u540c\u5b9e\u4f8b\u3001\u540c\u56fe\u7247','\u53ef\u547d\u4e2d\u6574\u5e27\u7f13\u5b58\uff1b\u53ea\u8bf4\u660e\u590d\u8bbf\u6210\u672c'],['\u5b57\u7b26\u51c6\u786e\u7387','\u540c\u56fe\u540c\u8bc4\u5206\u533a\uff0c\u89c4\u8303\u5316\u7f16\u8f91\u8ddd\u79bb','\u539f\u6587\u8f6c\u5f55\uff0c\u4e0d\u662f\u7ffb\u8bd1\u8bed\u4e49'],['\u771f\u5b9eAPI','\u53e6\u5217\u4e0b\u8282\u5b9e\u9645\u8d77\u6b62','\u4e0d\u4ee5OCR\u6216\u6a21\u62dfSSE\u66ff\u4ee3\u5b8c\u6574\u94fe\u8def']])
    body+='<p class="meta">'+h.esc(data['measured_at'])+' · '+h.esc(data['hardware']['os'])+' · '+h.esc(data['hardware']['gpu'])+'</p><div class="note">3\u8f6e\u4ea4\u66ff\u7248\u672c\u987a\u5e8f\uff0c\u6bcf\u573a\u666f/\u7248\u672c\u51b7\u6837\u672cn=3\u3001\u6bcf\u70ed\u8def\u5f84n=15\u3002\u56fe\u50cf→OcrCore\u7ed3\u679c\uff0c\u96f6API\u8bf7\u6c42\uff1bOS\u6587\u4ef6\u7f13\u5b58\u672a\u6e05\u7a7a\u3002\u6d4b\u8bd5\u671f\u95f4\u6709\u5e76\u884cUI\u622a\u56fe\u8d1f\u8f7d\uff0c\u4fdd\u7559\u6240\u6709\u79bb\u7fa4\u503c\u3001\u4e0d\u81c6\u65ad\u56e0\u679c\u3002\u9ed8\u8ba4auto\u8def\u7531\uff1a.27\u542f\u7528CUDA75/1024\uff0c\u50cf\u7d20\u753b\u9762\u4f18\u5148CPU\uff1b\u8fd9\u662f\u4ea7\u54c1\u7cfb\u7edf\u5bf9\u6bd4\uff0c\u4e0d\u662f\u7eafGPU\u52a0\u901f\u5b9e\u9a8c\u3002</div></section>'
    body+='<section id="ocr"><h2>OCR\uff1a\u9996\u6b21\u4e0e\u70ed\u8def\u5f84</h2><p>\u70b9\u4e3a\u5168\u90e8\u539f\u59cb\u6837\u672c\uff0c\u6df1\u8272\u7ad6\u7ebf\u4e3a\u4e2d\u4f4d\u6570\uff0c\u6a2a\u7ebf\u4e3a\u8303\u56f4\u3002\u4e09\u6761\u8def\u5f84\u5404\u81ea\u5b8c\u6574\u5750\u6807\u8f74\uff0c\u65e0150ms\u622a\u65ad\u3002\u91cd\u590d\u753b\u9762\u65f6\u95f4\u662f\u7f13\u5b58\u590d\u7528\uff0c\u4e0d\u662f\u65b0\u6587\u672c\u901f\u5ea6\u3002</p>'+plots(h,data,'latency');rows=[]
    for scene in SCENES:
        for version in VERSIONS:
            s=data['versions'][version]['scenes'][scene];cells=[h.esc(scene),version+'<br><span class="meta">'+h.esc(s['engine'])+'</span>']
            for key in ('cold_constructor_plus_first','warm_changed_background','warm_revisit'):
                x=s[key];cells.append(f'<strong>{x["median_ms"]:.3f}</strong><br><span class="meta">{x["min_ms"]:.3f}–{x["max_ms"]:.3f} · n={x["n"]}</span>')
            rows.append(cells)
    body+=h.table(['\u573a\u666f','\u7248\u672c / \u5b9e\u9645\u540e\u7aef','\u51b7\u542f\u52a8ms\uff08\u4e2d\u4f4d/\u8303\u56f4\uff09','\u80cc\u666f\u53d8\u5316ms\uff08\u4e2d\u4f4d/\u8303\u56f4\uff09','\u539f\u56fe\u590d\u8bbfms\uff08\u4e2d\u4f4d/\u8303\u56f4\uff09'],rows)+'<div class="note amber"><strong>\u7cbe\u5ea6\u589e\u52a0\u6709\u6210\u672c\u3002</strong> Status\u80cc\u666f\u53d8\u5316\u4ece23.722ms\u589e\u81f3205.891ms\u3002NEEDY CUDA\u51b7\u542f\u52a8\u4e2d\u4f4d3.287\u79d2\u3001\u6700\u592721.886\u79d2\u3002\u6545\u4e8b\u573a\u666f\u7cbe\u5ea6\u4e0d\u53d8\u3002\u5b8c\u6574\u4fdd\u7559\u53d8\u6162\u4e0e\u4e0d\u53d8\u7684\u7ed3\u679c\u3002</div></section>'
    body+='<section id="accuracy"><h2>\u51c6\u786e\u7387\uff1a\u540c\u56fe\u3001\u540c\u533a\u3001\u9010\u5b57\u5dee\u5f02</h2><p>\u51c6\u786e\u7387=100×(1−\u7f16\u8f91\u5dee\u5f02/\u6807\u6ce8\u5b57\u7b26\u6570)\u3002\u89c4\u8303\u5316NFKC\u3001\u7a7a\u767d\u548c\u5f2f\u5f15\u53f7\uff0c\u4fdd\u7559\u5927\u5c0f\u5199\uff1b\u6309\u6846\u4e2d\u5fc3\u9009\u533a\u540ey/x\u6392\u5e8f\u3002\u8fd9\u91cc\u8bc4\u4ef7\u539f\u6587\u8f6c\u5f55\uff0c\u4e0d\u8bc4\u4ef7\u7ffb\u8bd1\u8bed\u4e49\u3002</p>'+plots(h,data,'accuracy');rows=[]
    for scene in SCENES:
        a=data['versions'][VERSIONS[0]]['scenes'][scene]['accuracy'];b=data['versions'][VERSIONS[1]]['scenes'][scene]['accuracy']
        rows.append([h.esc(scene),str(a['characters']),f'{a["edits"]} / {a["character_accuracy_percent"]:.3f}%',f'{b["edits"]} / {b["character_accuracy_percent"]:.3f}%',f'{b["character_accuracy_percent"]-a["character_accuracy_percent"]:+.3f} pp'])
    body+=h.table(['\u573a\u666f','\u6807\u6ce8\u5b57\u7b26','0.01.15 \u5dee\u5f02/\u51c6\u786e\u7387','0.01.27 \u5dee\u5f02/\u51c6\u786e\u7387','\u767e\u5206\u70b9\u53d8\u5316'],rows)
    controls=h.load(h.EVIDENCE/'controls.json',{});rows=[]
    for item in controls.get('controls',[]):
        a=item.get('accuracy');rows.append([h.esc(item['version']),h.esc(item['scene']),h.esc(item['options']),h.esc(item.get('engine','unavailable')),f'{a["character_accuracy_percent"]:.3f}% · edits {a["edits"]}' if a else h.esc(item.get('error'))])
    body+='<details><summary>\u663e\u5f0f\u8bbe\u7f6e\u5bf9\u7167\uff1a\u5f3a\u5236Pixel\u3001Windows\u65e5\u8bed\u4e0e\u5173\u95edCUDA</summary><p>\u72ec\u7acb\u63a7\u5236\u5b9e\u9a8c\uff0c\u4e0d\u8986\u76d6\u9ed8\u8ba4auto\u57fa\u7ebf\u3002\u672a\u7a77\u4e3e\u8c03\u53c2\uff1b\u8de8\u7248\u672c\u540c\u540e\u7aef\u6a21\u5f0f\u4e5f\u4e0d\u662f\u540c\u4e00\u7b97\u6cd5\u5b9e\u73b0\u3002</p>'+h.table(['\u7248\u672c','\u573a\u666f','\u914d\u7f6e','\u5b9e\u9645\u540e\u7aef','\u7ed3\u679c'],rows)+'</details><div class="note">Space Rogue356\u5b57\uff1a\u9ed8\u8ba4auto81.461%→95.506%\uff1b.15\u5f3a\u5236pixel83.989%\u4e0d\u80fd\u5192\u5145\u9ed8\u8ba4\u57fa\u7ebf\u3002NEEDY248\u5b57\uff1a.15\u9ed8\u8ba4/Pixel1.613%\uff0c.27\u5173\u95edCUDA57.661%\uff0c\u542f\u7528CUDA98.387%\u3002\u7f3aWindows\u65e5\u8bed\u5305\u7684\u5931\u8d25\u4e0d\u8ba1\u7cbe\u5ea6\u3002</div>'+image_evidence(h,data)+'</section>'
    body+='<section id="e2e"><h2>\u771f\u5b9eAPI\uff1a\u56fa\u5b9a\u56fe\u7247\u5230\u8bd1\u6587\u56de\u8c03</h2>'+e2e_section(h)+'</section>'
    body+='<section id="gpu"><h2>GPU\u8bbe\u7f6e\u7684\u5b9e\u9645\u542b\u4e49</h2><div class="grid two"><div class="card"><h3>\u8d28\u91cf\u6ed1\u67610–100</h3><p>\u9ed8\u8ba475\uff0c\u63a7\u5236\u68c0\u6d4b\u5206\u8fa8\u7387\u4e0a\u9650\uff0c\u630932\u50cf\u7d20\u91cf\u5316\u3002\u5c0f\u56fe\u53ef\u80fd\u7b49\u6548\uff0c\u9ad8\u503c\u4e0d\u4fdd\u8bc1\u51c6\u786e\u7387\u5355\u8c03\u4e0a\u5347\u3002</p></div><div class="card"><h3>1024MiB arena\u9884\u7b97</h3><p>\u53ef\u8c03256–16384MiB\uff1b\u68c0\u6d4b/\u8bc6\u522b\u9884\u7b97\u4e0d\u8986\u76d6\u5168\u90e8\u8fdb\u7a0b\u3001\u9a71\u52a8\u548c\u8fd0\u884c\u5e93\u5f00\u9500\uff0c\u4e0d\u4f1a\u5f3a\u884c\u5360\u6ee11GiB\u3002</p></div></div><div class="note">\u7ecf\u5178\u82f1\u8bed\u50cf\u7d20\u753b\u9762Auto\u4f18\u5148CPU\uff1bWindows/Pixel\u6a21\u5f0f\u663e\u5f0fCPU\u3002CUDA\u6a21\u578b\u5206\u657095\u4e0d\u662f\u5b9e\u6d4b\u51c6\u786e\u738795%\u3002\u65e0\u517c\u5bb9\u7ec4\u4ef6\u65f6\u660e\u786e\u62a5\u544aCPU\u56de\u9000\u3002</div></section>'
    gpu=data['versions'][VERSIONS[1]]['scenes']['needy-caution-full.png'].get('cuda') or {}
    kernel=gpu.get('kernel_counts',{});arena=gpu.get('provider_arena_bytes',{})
    verification='<h3>\u672c\u8f6e\u5b9e\u9645GPU\u540e\u7aef\u8bb0\u5f55</h3>'+h.table(['\u9879','\u672c\u8f6e\u8bb0\u5f55','\u542b\u4e49'],[
        ['Provider',h.esc(gpu.get('provider')),h.esc(gpu.get('model'))+' / ORT '+h.esc(gpu.get('ort_version'))],
        ['\u5b9e\u9645kernel\u9a8c\u8bc1',h.esc(gpu.get('kernels_verified')),'det '+h.esc(kernel.get('det'))+' / rec '+h.esc(kernel.get('rec'))+' profiling\u4e8b\u4ef6'],
        ['\u8d28\u91cf\u6863\u4f4d / \u68c0\u6d4b\u957f\u8fb9',h.esc(gpu.get('quality'))+' / '+h.esc(gpu.get('det_limit_side'))+' px','\u672c\u8f6e\u53ea\u6d4b75\uff1b\u672a\u5236\u4f5c0–100\u6863\u4f4d\u7cbe\u5ea6\u6392\u884c\u699c'],
        ['provider arena\u914d\u7f6e',h.esc(arena.get('det'))+' + '+h.esc(arena.get('rec'))+' bytes','\u68c0\u6d4b/\u8bc6\u522b\u9884\u7b97\uff0c\u4e0d\u662f\u5b9e\u6d4b\u5cf0\u503c\u6216\u603b\u8fdb\u7a0b\u663e\u5b58']])
    # Insert into the GPU section without duplicating its stable section id.
    close=body.rfind('</section>');body=body[:close]+verification+body[close:]
    body+='<section id="raw"><h2>\u539f\u59cb\u8bb0\u5f55\u4e0e\u590d\u73b0</h2><p>\u6d4b\u91cf\u811a\u672c <code>tools/teacher_benchmark27.py</code>\uff1b\u539f\u59cb\u8bb0\u5f55 <code>reports/teacher-review27/raw/</code>\u3002\u5b8c\u6574\u6570\u636e\u542b\u6bcf\u8f6e\u503c\u3001\u540e\u7aef\u3001\u7f13\u5b58\u65ad\u8a00\u3001\u8f93\u5165SHA\u548c\u539f\u6587\u3002</p><p><a href="evidence.json">\u4e0b\u8f7d\u672c\u6b21\u5b8c\u6574\u5bf9\u7167JSON</a> · <a href="controls.json">\u72ec\u7acb\u63a7\u5236\u5b9e\u9a8cJSON</a></p><details><summary>\u5b8c\u6574\u6837\u672c\u6458\u8981</summary><pre>'+h.esc(json.dumps(data,ensure_ascii=False,indent=2))+'</pre></details></section>'
    return h.shell('\u6027\u80fd\u4e0e\u65b9\u6cd5',body,'performance'),markdown(data,e2e=h.load(h.EVIDENCE/'e2e-summary.json'))

def render_english(h,data):
    body=h.hero('FRESH MEASUREMENTS / 0.01.15 → 0.01.27','A better experience.<br>Less waiting.','Read the scope before the comparison. Cold startup, unchanged-text warm paths, cached revisits and transcription accuracy are distinct measurements.')
    body+='<section id="method"><h2>Define the question before comparing the numbers</h2>'+h.table(['Path','Measured interval','Interpretation'],[
        ['Cold','OcrCore construction through first result','Includes native/helper/model initialization; excludes Python launch and source-file loading'],
        ['Changed-background warm','Unique corner-pixel change; text unchanged','Whole-frame miss asserted; subregion caches remain eligible; not unseen-text speed'],
        ['Identical revisit','Same image, same instance','Eligible whole-frame cache; only the revisit cost'],
        ['Accuracy','Same manual truth and scoring zones','Source transcription, not translation meaning'],
        ['Real API','Separately scoped below','Not replaced with local OCR or simulated SSE']])+'<div class="note">Three alternating-order rounds. Per scene/release: n=3 cold and n=15 per warm path. OS file cache is not flushed. Concurrent UI-capture load was present; all outliers are retained without causal attribution. Actual auto routing is compared: .27 enables CUDA75/1024 with classic English pixel-frame CPU priority. This is a product/system comparison, not an isolated GPU speedup.</div><p class="meta">'+h.esc(data['measured_at'])+' · '+h.esc(data['hardware']['os'])+' · '+h.esc(data['hardware']['gpu'])+'</p></section>'
    body+='<section id="ocr"><h2>OCR: initialization and warm paths</h2><p>Dots show every sample, dark ticks show medians and lines show full ranges. Each axis includes every observed value; there is no 150ms cap. Fast cached revisits are not new-text recognition.</p>'+plots(h,data,'latency');rows=[]
    for scene in SCENES:
        for version in VERSIONS:
            s=data['versions'][version]['scenes'][scene];row=[h.esc(scene),version+'<br>'+h.esc(s['engine'])]
            for key in ['cold_constructor_plus_first','warm_changed_background','warm_revisit']:
                x=s[key];row.append(f'<strong>{x["median_ms"]:.3f}</strong><br><span class="meta">{x["min_ms"]:.3f}–{x["max_ms"]:.3f} · n={x["n"]}</span>')
            rows.append(row)
    body+=h.table(['Scene','Version / actual backend','Cold ms, median/range','Changed background ms, median/range','Identical revisit ms, median/range'],rows)+'<div class="note amber">Accuracy can cost latency. Status changed-background median increases from 23.722 to 205.891ms. NEEDY CUDA cold median is 3.287s and its maximum is 21.886s. Story accuracy is unchanged. These slower and unchanged results remain visible.</div></section>'
    body+='<section id="accuracy"><h2>Accuracy: same image, same zones, exact text</h2><p>100 × (1 − Levenshtein edits / labelled characters). NFKC, whitespace and curly quotes are normalized; case remains significant. Box centres select zones, then y/x determines order. This measures transcription, not semantic translation quality.</p>'+plots(h,data,'accuracy')
    body+='<div class="note">Space Rogue has 356 labelled characters: default auto 81.461% → 95.506%. The separate .15 forced-pixel control is 83.989%; it is not the default baseline. NEEDY has 248 characters: .15 auto/pixel 1.613%, .27 CPU-only control 57.661%, .27 CUDA auto 98.387%. Missing Windows Japanese OCR support is a failed control, not zero accuracy.</div>'+image_evidence(h,data,True)+'</section>'
    body+='<section id="e2e"><h2>Real API: fixed image to translation callbacks</h2>'+e2e_section(h,True)+'</section>'
    gpu=data['versions'][VERSIONS[1]]['scenes']['needy-caution-full.png']['cuda']
    body+='<section id="gpu"><h2>GPU controls and their limits</h2><div class="grid two"><div class="card"><h3>Quality 0–100</h3><p>Default 75 changes the detector resolution cap, quantized to 32 pixels. Small images can be equivalent across settings. Higher values do not guarantee higher accuracy.</p></div><div class="card"><h3>1024MiB arena budget</h3><p>Range 256–16384MiB. This budgets detector/recognizer arenas, not all process, driver or library allocations. It neither reserves nor forces a full 1 GiB allocation.</p></div></div><p>Auto gives classic English pixel frames CPU priority; manual Windows/Pixel modes stay on CPU. Model confidence 95 is not a measured 95% accuracy promise. Missing/incompatible components have explicit CPU fallback.</p>'+h.table(['Current recorded backend fact','Value'],[['Provider / model',h.esc(gpu['provider'])+' / '+h.esc(gpu['model'])],['Kernel profiling verified',h.esc(gpu['kernels_verified'])+' · det '+h.esc(gpu['kernel_counts']['det'])+' / rec '+h.esc(gpu['kernel_counts']['rec'])],['Quality / detector cap',h.esc(gpu['quality'])+' / '+h.esc(gpu['det_limit_side'])+'px'],['Configured provider arenas (not measured peak)',h.esc(gpu['provider_arena_bytes'])]])+'<p>Only quality 75 is measured in this fresh paired review; no 0–100 accuracy ranking is inferred.</p></section>'
    body+='<section id="raw"><h2>Public evidence and reproduction</h2><p><a href="evidence.json">All OCR distributions, zones and transcripts</a> · <a href="controls.json">Separate explicit backend controls</a></p><p>Measurement runner: <code>tools/teacher_benchmark27.py</code>. Per-round implementation hashes and diagnostic logs live in the full project under <code>reports/teacher-review27/raw/</code>. This review preserves all sample values and embeds the source images.</p></section>'
    return h.shell('Fresh performance evidence',body,'performance.en','en')
