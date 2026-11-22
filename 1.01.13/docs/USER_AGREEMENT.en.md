# User terms

NKC_Galgame_Translator · 1.01.13

## 1. Acceptance and license
When you first use the app, or when these terms change, you are asked to read and accept them. The app saves the version you accepted and the date on this PC. The project's own code is licensed under the MIT License, which permits commercial use, modification and redistribution subject to its terms. This notice describes how the app works and handles data. The MIT License and the licenses of individual components continue to govern the rights they grant. The full MIT text appears below.

## 2. Capturing and translating a game
Select the game window or the areas you want to translate. The app captures those areas, recognizes the text and draws a translation in the same place. Game files and game memory are not modified. The app does not inject code or read game memory. OCR, translation and positioning can make mistakes. To see the original, stop translation or close the app.

## 3. Your API provider and costs
The provider you select generates new translations. A request may include game text, the language pair, profile notes, summaries and relevant translation history. If you enable image recognition through the backend, the selected part of the game screen is also sent. Online context lookup and automatic summaries may make extra requests. Your provider's terms and prices apply. Limiting the number of requests in the app does not set a monetary spending cap.

## 4. Local files and API keys
Profiles, translations, notes and summaries are saved on this PC. The optional localization toolkit also writes screenshots and text pairs to the folder you choose. Saved context can be compressed. Windows encrypts API keys for your user account using DPAPI. The app decrypts a key when it needs to authenticate a request. The app has no built-in usage analytics.

## 5. Third-party software
CPython and Tcl/Tk run the app and its interface. Pillow reads and processes images. tesserocr connects to Tesseract for local text recognition, using its language data and the Leptonica imaging library. The optional GPU package uses RapidOCR and ONNX Runtime with NVIDIA CUDA and cuDNN. HTTPX, httpcore, OpenSSL and certifi handle API connections and certificate verification. SQLite stores profiles and zlib compresses data. Source Han Sans provides the interface and tour fonts. PyInstaller builds the Windows distribution. The component notices and licenses are in THIRD_PARTY_NOTICES.md and the licenses folder.

## 6. Use and liability
Only process material you have the right to use. The software is provided as is under the MIT License. Any rights or liabilities that applicable law does not allow the parties to exclude remain in effect.

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
