# 利用規約

NKC_Galgame_Translator · 1.01.13

## 1. 同意と License
初めて使うとき、または規約が改定されたときに、内容を確認して同意してください。同意した規約の版と日時はこの PC に保存されます。本プロジェクト独自の Source Code には MIT License が適用され、その条件の下で商用利用、変更、再配布ができます。本規約はアプリの動作とデータの取り扱いを説明するもので、MIT License や各 Component の License で認められた権利を変更するものではありません。MIT License の原文を末尾に掲載しています。

## 2. ゲーム画面の読み取り
利用者が選んだゲームの Window または範囲を取り込み、文字を読み取って、元の位置に訳文を重ねます。ゲーム File の変更、コードの注入、ゲームの Process Memory の読み書きは行いません。文字の読み取りや訳文、表示位置には誤りが生じることがあります。原文を確認するには、翻訳を停止するか、アプリを終了してください。

## 3. 翻訳サービスへの送信と料金
新しい訳文は、利用者が指定したサービスで生成します。原文と言語の組み合わせのほか、Profile のメモ、保存した要約、関連する翻訳履歴を送信する場合があります。LLM による画像認識を有効にすると、選択したゲーム画面の画像も送信します。オンライン検索による背景情報の取得や自動要約を有効にすると、追加の Request が発生することがあります。データの取り扱いと料金は各サービスの規約に従います。アプリ内で回数を制限しても、請求額の上限は設定されません。

## 4. この PC に保存するデータ
訳文、Profile、メモ、要約はこの PC に保存します。翻訳チーム用ツールを有効にすると、指定の Folder にゲーム画面の画像と対訳も保存します。保存容量を抑えるため、Context のデータを圧縮することがあります。API Key は Windows の DPAPI を使い、現在の Windows ユーザーに紐づけて暗号化します。サービスへの認証時には復号して使用します。アプリに利用状況の解析機能は組み込まれていません。

## 5. 利用している Software
実行環境と画面表示には CPython と Tcl/Tk、画像処理には Pillow を使用します。ローカルの文字認識には tesserocr、Tesseract とその言語データ、画像処理 Library Leptonica を使います。追加の GPU パッケージでは RapidOCR と ONNX Runtime を NVIDIA CUDA、cuDNN と組み合わせて使用します。API 通信と証明書の検証には HTTPX、httpcore、OpenSSL、certifi、Profile の保存と圧縮には SQLite と zlib を使用します。画面とガイドの書体は源ノ角ゴシックです。Windows 版の配布には PyInstaller を使用します。各 Component の表記と License は THIRD_PARTY_NOTICES.md と licenses Folder で確認できます。

## 6. 利用と責任
利用する権利のあるゲーム、画像、文章を対象にしてください。本 Software は MIT License に従い、現状のまま提供されます。適用される法令により排除できない権利と責任は、その法令に従います。

## MIT License

Copyright (c) 2026 NKC_Galgame_Translator contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
