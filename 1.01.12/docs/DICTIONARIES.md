# 翻译词典导入与历史参考 · 0.01.27

0.01.27 加入可选 CUDA OCR、后台联网语境与整组字号修复。本版新增同图 OCR 评审，对照 0.01.15，分别报告冷启动、背景变化热路径、复访缓存和逐字精度；真实 API 链路另列。历史证据保留原版本标签，当前方法与范围见性能报告及 TEST_REPORT.json。

适用版本：0.01.27 · 文档复核：2026-11-18。历史记录保留原版号。


现有词条、共享词典与导入数据保留用于资料管理。新译文全部由 AI 生成，不执行本地模板/拼接。当前提示参考提取使用命名游戏中匹配的术语；共享表可管理但不自动用于新译文。导入文件不作为代码执行。

## CSV 与 TSV

CSV 使用逗号分隔，TSV 使用制表符分隔。推荐 UTF-8，支持 UTF-8 BOM、带 BOM 的 UTF-16（小端或大端）和 GB18030；不支持 UTF-32 或无 BOM 的 UTF-16。格式由文件扩展名确定，不猜测分号等其他分隔符。

推荐表头：

```csv
source,target
Start,开始
Save,保存
HP {n},生命值 {n}
```

也支持 `word,translation`（适用于 ECDICT 风格 CSV）、`原文,译文`、`源文本,目标文本`，或者与所选语言相符的 `en,zh-CN`。可识别的原文列名还包括 `src/original/source_text/term/词条/单词`，译文列名包括 `dst/translated/target_text/meaning/翻译/释义`。大小写和表头两端空白不影响识别。

多列文件需要唯一的原文列和译文列。ECDICT 文件中的 `definition` 是另一字段，不会代替 `translation`。其他字段不导入。没有表头时，文件必须恰好两列，第一列为原文，第二列为译文。若首行使用上述保留表头词，会按表头解析；不确定时请添加 `source,target`。

引号和单元格内换行遵循 CSV 规则：

```csv
source,target
"Open, now","现在，打开"
"Say ""Hello""","说“你好”"
"First line
Second line","第一行
第二行"
```

完全空白的行会跳过；存在内容的记录必须同时有原文和译文，各行列数须一致。单元格内部的换行、制表符和 Unicode 文本保留，CRLF/CR 统一为 LF，字段两端空白去除，并进行 NFC Unicode 规范化。

## JSON

支持原文到译文的对象：

```json
{
  "Start": "开始",
  "Exit": "退出"
}
```

或者包含 `source`、`target` 的数组：

```json
[
  {"source": "Open the door", "target": "打开门"},
  {"source": "HP {n}", "target": "生命值 {n}"}
]
```

原文和译文必须是字符串。不能使用 `null`、数字或数组代替文本。JSON 的 NaN、Infinity、尾逗号和同名但内容不同的字段会被拒绝。此类文件不包含权威语言元数据，整份文件使用界面选定的语言对。

## TMX

支持标准 `tmx/body/tu/tuv/seg` 结构，通过 `tuv` 的 `xml:lang` 选择语言。示例：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<tmx version="1.4">
  <header creationtool="NKC_Galgame_Translator examples" creationtoolversion="0.01.10"
          segtype="sentence" adminlang="en" srclang="en" datatype="PlainText"/>
  <body>
    <tu>
      <tuv xml:lang="en"><seg>Start</seg></tuv>
      <tuv xml:lang="zh-CN"><seg>开始</seg></tuv>
    </tu>
  </body>
</tmx>
```

无所选语言对的 `tu` 会跳过；最终没有可用词条时导入失败。一个 `tuv` 必须有唯一的 `seg`。内联元素的文本依次合并，不执行其中的标记。带格式代码的翻译记忆库可能保留代码的文字表示；如只需要纯文本词典，建议从原工具导出纯文本 TMX。

语言匹配采用以下规则：

| 选择 | 可匹配的常见标签 | 不自动推断 |
|---|---|---|
| `zh-Hans` | `zh-Hans`、`zh-CN`、`zh-SG` | `zh`、`zh-TW`、`zh-Hant` |
| `zh-Hant` | `zh-Hant`、`zh-TW`、`zh-HK`、`zh-MO` | `zh`、`zh-CN`、`zh-Hans` |
| `en` | 优先 `en`，再考虑单一地区版本 | 多个不同地区译文冲突时拒绝 |
| `en-US` | 优先 `en-US`，其次通用 `en` | 不使用 `en-GB` 冒充 |
| `ja` | 优先 `ja`，其次 `ja-JP` 等单一地区版本 | 不跨语言匹配 |

所有 DTD、DOCTYPE 与实体声明都会被拒绝，不访问外部实体文件或网络地址。XML 结构深度限制为 64 层，元素数限制为 100 万。单纯的 `&amp;` 等 XML 内置字符转义可以使用。

## 重复、冲突与边界

- 同一原文与同一译文重复出现，解析结果只保留一项。
- 同一原文对应不同译文时，整份文件拒绝导入；请先删除歧义，或按游戏/语言拆分文件。这与提交到数据库时“保留已有”或“覆盖已有”的选择不同：后者处理的是文件与已有词典的冲突。
- 文件最多 20 MiB，最多 100000 条记录；重复记录仍参与输入记录上限，TMX 未匹配的 `tu` 也参与上限。
- 单个原文或译文最多 4096 字符，禁止空值和非换行/制表符的控制字符。数据库对游戏术语范围另有更小容量上限，超过时会整体拒绝提交。
- CSV/TSV/JSON 的语言由界面选择；程序无法自动保证词条内容与语言选择一致。
- 不自动拆分多个释义，也不保证导入的长词典释义适合直接覆盖游戏文本。优先整理简洁、明确的译文。

## 示例文件与许可

以下小型例子由本项目原创，采用主项目的 MIT 许可，可用于验证导入：

- [英文到简体中文 CSV](examples/general-en-zh.csv)
- [日文到简体中文 TSV](examples/general-ja-zh.tsv)
- [英文到简体中文 JSON](examples/general-en-zh.json)
- [英文到简体中文 TMX](examples/general-en-zh.tmx)

项目不附带第三方通用词库。用户导入外部词库前应确认相应许可；支持 ECDICT 风格列名仅表示格式兼容，不代表本项目包含或重新许可该词库。

解析接口：`nkc_galgame_translator.dictionary_import.parse_dictionary(path, source_lang, target_lang)` 返回 `list[dict[source,target]]`；失败抛出 `DictionaryImportError`。该函数只读文件，不写数据库，不联网。界面应在工作线程解析，在主线程展示预览，再调用翻译引擎的事务导入接口。
