# SPDX-License-Identifier: MIT
"""Write standalone release HTML using this version's measured OCR samples."""
from html import escape
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'


def page(title, label, content, lang='zh-CN'):
    style = ":root{color-scheme:light;--ink:#26242d;--muted:#605c68;--paper:#f7f3ef;--card:#fffcfb;--line:#ddd5d4;--red:#a8203b;--slate:#625c75}\n*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.68 system-ui,'Microsoft YaHei UI',sans-serif}main{width:min(1100px,92vw);margin:auto;padding:56px 0 84px}header{border-top:4px solid var(--red);padding:28px 0;border-bottom:1px solid var(--line);margin-bottom:35px}nav{display:flex;gap:1.2rem;flex-wrap:wrap;margin-top:1rem}a{color:var(--red)}h1,h2,h3{line-height:1.2}h1{font-size:clamp(2.1rem,5vw,3.8rem);letter-spacing:-.035em;margin:.2em 0}h2{margin:1.8em 0 .7em}p{margin:.65em 0}.eyebrow{font-weight:700;letter-spacing:.09em;color:var(--red)}.muted{color:var(--muted)}.card,.chart,details{padding:20px 24px;border:1px solid var(--line);border-radius:15px;background:var(--card);margin:12px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}.metric{display:block;font-size:2.05rem;font-weight:750;color:var(--red)}.bar{height:14px;margin:4px 0 12px;border-radius:5px;background:#eae4e6;overflow:hidden}.bar span{height:100%;display:block;background:var(--slate)}.bar.on span{background:var(--red)}.pair{display:grid;grid-template-columns:1fr 1fr;gap:15px}table{width:100%;border-collapse:collapse}td,th{padding:10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}.scroll{overflow:auto}code{overflow-wrap:anywhere}img{display:block;max-width:100%;height:auto;border:1px solid var(--line);border-radius:7px}figure{margin:0}summary{cursor:pointer;font-weight:650}li{margin:.3em 0}.flow{display:flex;gap:8px;flex-wrap:wrap}.flow span{border:1px solid var(--line);background:var(--card);padding:8px 12px;border-radius:8px}.flow b{align-self:center;color:var(--red)}@media(max-width:640px){main{padding-top:18px}.pair{grid-template-columns:1fr}.card,.chart,details{padding:14px}}\n"
    return f"""<!doctype html><html lang="{lang}"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{escape(title)} · 0.01.30</title>
<style>{style}</style><main><header><div class="eyebrow">NISHOKUCHOU · 0.01.30 / {label}</div>
<h1>{escape(title)}</h1></header>{content}</main></html>"""


def bars(title, off, on, maximum, suffix, digits=1):
    sides = []
    for label, value, css in (('CUDA \u5173', off, ''), ('CUDA \u5f00', on, 'on')):
        sides.append(f'<div>{label} · <strong>{value:.{digits}f}{suffix}</strong>'
                     f'<div class="bar {css}"><span style="width:{max(0,value)/maximum*100:.2f}%"></span></div></div>')
    return f'<section class="chart"><h3>{title}</h3>{"".join(sides)}</section>'


def performance(data):
    names = {'needy-caution-full.png':'\u4e3b\u64ad\u5973\u5b69\u91cd\u5ea6\u4f9d\u8d56 · \u8b66\u544a\u9875', 'spacerogue-game.png':'Space Rogue Classic · \u5267\u60c5',
             'status.png':'Space Rogue Classic · \u72b6\u6001\u83dc\u5355', 'cargo.png':'Space Rogue Classic · \u8d27\u7269\u4ef7\u683c\u8868'}
    scene = next(item for item in data['scenes'] if item['scene']=='needy-caution-full.png')
    off, on = scene['cuda_off'], scene['cuda_on']
    gain = 100*(1-on['median_ms']/off['median_ms'])
    points = on['accuracy_percent']-off['accuracy_percent']
    charts = (
        bars('\u9884\u70ed\u540e\u7684 OCR \u4e2d\u4f4d\u65f6\u95f4 · \u8d8a\u77ed\u8d8a\u5feb', off['median_ms'], on['median_ms'], 600, ' ms') +
        bars('\u6807\u6ce8\u533a\u5b57\u7b26\u51c6\u786e\u7387 · \u8d8a\u957f\u8d8a\u9ad8', off['accuracy_percent'], on['accuracy_percent'], 100, '%', 2) +
        bars('\u65b0\u8fdb\u7a0b\u9996\u6b21 OCR · \u542b\u5f15\u64ce\u521d\u59cb\u5316', off['first_ms']/1000, on['first_ms']/1000,
             max(off['first_ms'], on['first_ms'])/1000, ' \u79d2', 2))
    rows = []
    samples = []
    for item in data['scenes']:
        a,b = item['cuda_off'],item['cuda_on']
        name = names[item['scene']]
        route = 'RapidOCR / CUDA' if b['cuda_status']=='active' else 'Tesseract \u50cf\u7d20\u8def\u5f84'
        rows.append(f"<tr><th>{name}</th><td>{route}</td><td>{a['median_ms']:.1f} → {b['median_ms']:.1f}</td>"
                    f"<td>{a['accuracy_percent']:.2f}% → {b['accuracy_percent']:.2f}%</td>"
                    f"<td>{a['edits']} → {b['edits']} / {a['characters']}</td></tr>")
        lines = []
        for label,result in (('\u5173',a),('\u5f00',b)):
            values = '\u3001'.join(f'{number:.1f}' for number in result['warm_ms'])
            lines.append(f"<p>CUDA {label} · {escape(result['engine'])} · \u9996\u6b21 {result['first_ms']:.1f} ms · \u9884\u70ed\u6837\u672c {values} ms</p>")
        samples.append(f'<h3>{name}</h3><p><code>{item["sha256"]}</code></p>{"".join(lines)}')
    return page('\u54c1\u8d28\u7684\u4f53\u9a8c\uff0c\u66f4\u5c11\u7684\u7b49\u5f85', 'OCR BENCHMARK', f"""
<p>\u540c\u4e00\u53f0\u7535\u8111\u3001\u540c\u4e00\u7248\u672c\u3001\u540c\u4e00\u5f20\u539f\u59cb\u622a\u56fe\u3002\u53ea\u6539 CUDA \u5f00\u5173\uff0c\u6bd4\u8f83\u8f6f\u4ef6\u5b9e\u9645\u9009\u7528\u7684 OCR \u8def\u5f84\u3002</p>
<div class="grid"><div class="card"><span class="metric">−{gain:.1f}%</span>\u8b66\u544a\u9875\u9884\u70ed\u4e2d\u4f4d\u8017\u65f6</div>
<div class="card"><span class="metric">+{points:.2f} \u4e2a\u767e\u5206\u70b9</span>\u8b66\u544a\u9875\u5b57\u7b26\u51c6\u786e\u7387</div>
<div class="card"><span class="metric">{on['first_ms']/1000:.2f} \u79d2</span>CUDA \u65b0\u8fdb\u7a0b\u9996\u6b21\u8bc6\u522b</div></div>
<h2>\u5b9e\u9645\u8c03\u7528 CUDA \u7684\u573a\u666f</h2><p>{names[scene['scene']]} · {scene['size'][0]} × {scene['size'][1]} \u50cf\u7d20\u3002</p>{charts}
<h2>\u56db\u7ec4\u622a\u56fe\u7684\u5b8c\u6574\u7ed3\u679c</h2><div class="scroll"><table><thead><tr><th>\u753b\u9762</th><th>\u5f00\u542f\u540e\u5b9e\u9645\u8def\u5f84</th>
<th>\u4e2d\u4f4d\u65f6\u95f4\uff08ms\uff09\u5173 → \u5f00</th><th>\u51c6\u786e\u7387 \u5173 → \u5f00</th><th>\u7f16\u8f91\u8ddd\u79bb / \u5b57\u7b26\u6570</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<p>\u4e09\u5f20 Space Rogue Classic \u622a\u56fe\u5747\u547d\u4e2d CPU \u50cf\u7d20\u5b57\u4f53\u4e13\u7528\u8def\u5f84\u3002\u8868\u4e2d\u7684\u65f6\u95f4\u5dee\u5c5e\u4e8e\u540c\u4e00\u8def\u5f84\u7684\u5b9e\u6d4b\u6ce2\u52a8\u3002</p>
<h2>\u6d4b\u8bd5\u53e3\u5f84</h2><div class="card">
<p>Windows 11 · {escape(data['gpu'])}\u3002GPU \u914d\u7f6e\u4e3a 1024 MiB \u5185\u5b58\u9884\u7b97\u300175/100 \u7cbe\u5ea6\u7cfb\u6570\u3002</p>
<p>\u6bcf\u5f20\u56fe\u3001\u6bcf\u79cd\u914d\u7f6e\u5355\u72ec\u5efa\u7acb OCR \u8fdb\u7a0b\u6216\u4f1a\u8bdd\u3002\u8bb0\u5f55\u7b2c\u4e00\u6b21\u8c03\u7528\u548c\u4e4b\u540e {data['warm_rounds']} \u6b21\uff0c\u53d6\u540e\u8005\u4e2d\u4f4d\u6570\u3002\u6bcf\u6b21\u6e05\u7406\u5e27\u7ed3\u679c\u7f13\u5b58\uff0c\u8ba1\u65f6\u5305\u542b CPU/GPU \u8bc6\u522b\u3001\u8f85\u52a9\u8fdb\u7a0b\u901a\u4fe1\u53ca\u533a\u57df\u7ec6\u5316\u3002</p>
<p>\u4ee5\u4eba\u5de5\u5206\u533a\u6807\u6ce8\u4e3a\u51c6\uff0c\u505a Unicode NFKC\u3001\u5ffd\u7565\u7a7a\u767d\u540e\u8ba1\u7b97\u5b57\u7b26\u7f16\u8f91\u8ddd\u79bb\u3002\u51c6\u786e\u7387 = 1 − \u7f16\u8f91\u8ddd\u79bb ÷ \u6807\u6ce8\u5b57\u7b26\u6570\u3002\u56fa\u5b9a\u622a\u56fe\u5bf9\u7167\u4ec5\u8986\u76d6 OCR\uff0c\u7aef\u5230\u7aef\u7ffb\u8bd1\u8fd8\u53d7\u5230\u622a\u56fe\u53d6\u5f97\u3001\u7f51\u7edc\u4e0e\u6a21\u578b\u8f93\u51fa\u65f6\u95f4\u5f71\u54cd\u3002</p>
<p>\u771f\u6b63\u4f7f\u7528 CUDA \u7684\u516c\u5f00\u5bf9\u7167\u4e3a 1 \u5f20\u622a\u56fe\u3002CUDA \u7b2c\u4e00\u6b21\u8fd0\u884c\u9700\u521d\u59cb\u5316\u6a21\u578b\u4e0e\u9a71\u52a8\u4f1a\u8bdd\uff0c\u4f53\u9a8c\u53d6\u51b3\u4e8e\u673a\u5668\u4e0e\u6e38\u620f\u753b\u9762\u3002</p></div>
<details><summary>\u67e5\u770b\u539f\u59cb\u6837\u672c\u4e0e\u622a\u56fe\u6458\u8981</summary>{''.join(samples)}</details>""")


def main():
    data = json.loads((ROOT/'reports/cuda-comparison30.json').read_text(encoding='utf-8'))
    (DOCS/'PERFORMANCE_REPORT.html').write_text(performance(data), encoding='utf-8')
    (DOCS/'TASK_REPORT.html').write_text(page('0.01.30 \u4efb\u52a1\u62a5\u544a', 'RELEASE REVIEW', """
<div class="grid"><div class="card"><h3>\u7126\u70b9\u4e0d\u6253\u65ad\u7ffb\u8bd1</h3>
<p>\u77ed\u6309\u94ae\u6587\u672c\u786e\u8ba4\u540e\uff0c\u91c7\u96c6\u753b\u9762\u7684\u6309\u94ae\u5185\u4fa7\u50cf\u7d20\u76f8\u540c\u65f6\u7ee7\u7eed\u4f7f\u7528\u539f\u8bc6\u522b\u7ed3\u679c\u548c\u5df2\u6709\u8bd1\u6587\u3002\u79fb\u52a8\u7126\u70b9\u4ea7\u751f\u7684\u63cf\u8fb9\u4e0d\u4f1a\u8ba9 OK \u91cd\u65b0\u8fdb\u5165\u7ffb\u8bd1\u961f\u5217\u3002</p></div>
<div class="card"><h3>\u6309\u6e90\u5b57\u5f62\u9ad8\u5ea6\u6392\u7248</h3>
<p>\u6309\u94ae\u8bd1\u6587\u53ea\u4f7f\u7528\u7ecf\u68c0\u67e5\u7684\u7559\u767d\uff0c\u5e76\u6309\u539f\u4e2d\u5fc3\u7ed8\u5236\u3002\u77ed\u6807\u7b7e\u7b49\u5b8c\u6574\u8bd1\u6587\u540e\u4e00\u6b21\u663e\u793a\u3002\u5b57\u53f7\u4ecd\u53d7\u8bbe\u7f6e\u4e0e\u5b9e\u9645\u7a7a\u95f4\u7ea6\u675f\u3002</p></div>
<div class="card"><h3>\u5b89\u88c5\u548c\u8fc1\u79fb</h3>
<p>\u53d1\u884c\u7a0b\u5e8f\u9762\u5411 Windows x64\u3002\u914d\u7f6e\u3001\u52a0\u5bc6\u5bc6\u94a5\u4e0e\u6863\u6848\u7531\u672c\u673a\u8fc1\u79fb\u3002\u516c\u5f00\u5305\u7528\u4e8e\u5206\u53d1\u3002</p></div></div>
<h2>\u9a8c\u8bc1\u8986\u76d6</h2>
<ul><li>\u7126\u70b9\u63cf\u8fb9\u548c OCR \u8bef\u8bfb\u7684\u56de\u5f52\u6d4b\u8bd5\u786e\u4fdd\u4fdd\u7559\u5df2\u6709\u8bd1\u6587\uff0c\u5e76\u9a8c\u8bc1\u771f\u5b9e\u5b57\u5f62\u53d8\u5316\u4ecd\u66f4\u65b0\u3002</li>
<li>Windows \u539f\u751f\u7ed8\u5236\u56de\u5f52\u68c0\u67e5\u5b57\u53f7\u3001\u5c45\u4e2d\u4ee5\u53ca\u8fb9\u754c\u3002</li>
<li>\u5386\u53f2\u6e38\u620f\u539f\u59cb\u622a\u56fe\u7684 CUDA \u5b9e\u6d4b\u786e\u8ba4 OK \u548c Cancel \u90fd\u53ef\u4f7f\u7528\u7ecf\u786e\u8ba4\u7684\u7559\u767d\u3002\u6e38\u620f\u5185\u8fde\u7eed\u4ea4\u4e92\u7684\u8868\u73b0\u4ecd\u9700\u5b9e\u673a\u89c2\u5bdf\u3002</li>
<li>\u4e2d\u6587\u3001\u82f1\u6587\u3001\u65e5\u6587\u4e94\u4e2a\u4e3b\u9875\u9762\u53ca\u914d\u7f6e\u5bf9\u8bdd\u6846\u4f7f\u7528\u9694\u79bb\u914d\u7f6e\u622a\u56fe\u3002\u7ed3\u679c\u968f\u4ea4\u4ed8\u5305\u63d0\u4f9b\u3002</li></ul>
<h2>\u9605\u8bfb\u6750\u6599</h2><nav><a href="PROJECT_MANUAL.html">\u4e2d\u6587\u624b\u518c</a><a href="PROJECT_MANUAL.en.html">English manual</a>
<a href="PERFORMANCE_REPORT.html">CUDA \u6a21\u5f0f\u5bf9\u7167</a></nav>"""), encoding='utf-8')
    for source, dest, title, label, lang in (
        ('MANUAL_30.zh.md', 'PROJECT_MANUAL.html', '\u4e8c\u8272\u8776·\u6e38\u620f\u5b9e\u65f6\u7ffb\u8bd1', '\u64cd\u4f5c\u624b\u518c', 'zh-CN'),
        ('MANUAL_30.en.md', 'PROJECT_MANUAL.en.html', 'Nishokuchou Real-time Game Translation', 'USER GUIDE', 'en'),
    ):
        content = (DOCS/source).read_text(encoding='utf-8')
        (DOCS/dest).write_text(page(title,label,content,lang),encoding='utf-8')


if __name__ == '__main__':
    main()
