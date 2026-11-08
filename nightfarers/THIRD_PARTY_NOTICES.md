# Third-party notices

`nightfarers_native.dll` is built from this repository's code plus the libraries below, which are compiled into it.
None of their source code is copied into this repository: Cargo downloads them at build time from the pinned
versions in `src/native/Cargo.toml` and `Cargo.lock`. Their licences are reproduced in full here and ship with the DLL.

| Library | Version | Licence |
|---|---|---|
| [fromsoftware-rs](https://github.com/vswarte/fromsoftware-rs) (`eldenring`, `fromsoftware-shared`) | commit 57023153 | MIT NON-AI or Apache NON-AI 2.0 |
| [hudhook](https://github.com/veeenu/hudhook) | commit 6a361de9 | MIT |
| [imgui-rs](https://github.com/imgui-rs/imgui-rs) / [Dear ImGui](https://github.com/ocornut/imgui) | 0.12.0 | MIT OR Apache-2.0 / MIT |
| Other Rust crates (windows, tracing, ...) | see `Cargo.lock` | MIT and/or Apache-2.0 |

**fromsoftware-rs's licence forbids using its code, or anything derived from it, to train or improve machine-learning
or AI models, or including it in such datasets.** That restriction applies to the DLL too.

The offline converters (not shipped) also use [Andre.SoulsFormats](https://github.com/vawser/Smithbox) through
Smithbox, WitchyBND, HKLib, DSLuaDecompiler, Nuxe and texconv. They are downloaded separately; see BUILDING.md.

## fromsoftware-rs: MIT NON-AI License

```
MIT NON-AI License

Copyright (c) 2025 Vincent Swarte

Permission is hereby granted, free of charge, to any person obtaining a copy of the software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions.

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

In addition, the following restrictions apply:

1. The Software and any modifications made to it may not be used for the purpose of training or improving machine learning algorithms,
including but not limited to artificial intelligence, natural language processing, or data mining. This condition applies to any derivatives,
modifications, or updates based on the Software code. Any usage of the Software in an AI-training dataset is considered a breach of this License.

2. The Software may not be included in any dataset used for training or improving machine learning algorithms,
including but not limited to artificial intelligence, natural language processing, or data mining.

3. Any person or organization found to be in violation of these restrictions will be subject to legal action and may be held liable
for any damages resulting from such use.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE
OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```

(fromsoftware-rs is dual-licensed; its Apache NON-AI 2.0 text is at https://github.com/vswarte/fromsoftware-rs/blob/57023153d786c4b13fe95d9170e6dcd9d35093ea/LICENSE-ASL2-NON-AI)

## hudhook: MIT License

```
MIT License

Copyright (c) 2020-2024 Andrea Venuta

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Dear ImGui: MIT License

```
The MIT License (MIT)

Copyright (c) 2014-2023 Omar Cornut

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
