# 論文著者の公開モデルの照合

2026-11-21 に著者の公開リポジトリのコミット `51ce8acf253106cda939d855a5307783d1bd0b6c` を固定し、GPT-6.1 Sol が設計した第1世代の `models/sol/free-arc_blind_K0_r1` を確認した。[公開モデル](https://github.com/effl-lab/Weight-Space-Programming/tree/51ce8acf253106cda939d855a5307783d1bd0b6c/models/sol/free-arc_blind_K0_r1)

**ローカルで確認できた範囲**　27ファイルの名前とGitオブジェクトIDからディレクトリのツリーハッシュ `9b814f4ab0ebdcb1b5617b3471071fa294d6f25c` を再計算した。下の4ファイルは元のバイト列からもGit blobのSHA-1を再計算し、すべて一致した。同じコミットを取得した環境では `git ls-tree -r HEAD models/sol/free-arc_blind_K0_r1` で照合できる。

| ファイル | バイト数 | Git blob SHA-1 |
|---|---:|---|
| arch.py | 10,955 | e55d31c293495ec265ebf12e82389632dcc67338 |
| build.py | 19,386 | 4fc46e791cc65fead24e543f33fde982adfd9e93 |
| physics.tsv | 10,917 | 79c5f8ecd62b5b90bba45ecfaf139026f4315d18 |
| result.json | 1,238 | 21bac53e41f977164d41ffa0e72eff59e2b3b7c7 |

**著者の保存結果**　`result.json` は4択理科3,530問で44.58%、内訳はEasy 2,365問で50.99%、Challenge 1,165問で31.57%。非ゼロ要素数は112,820。この世代のSolモデルの数値で、論文で54.4%を記録したClaudeの第5世代とは別の個体である。[保存結果](https://github.com/effl-lab/Weight-Space-Programming/blob/51ce8acf253106cda939d855a5307783d1bd0b6c/models/sol/free-arc_blind_K0_r1/result.json)

**ローカル推論**　実行は未完了。`build.py` の重み構築と `arch.py` の `forward(w, q, o)` はPyTorchを使い、著者の依存定義は `torch==2.6.0`。システムPythonと作業用Pythonの双方で `import torch` が失敗し、ローカルにCPU版ライブラリとインストール用wheelも見つからなかった。独自問題への予測件数は0件。上記は著者のスコアで、この環境での再採点は行っていない。[著者のビルド・採点手順](https://github.com/effl-lab/Weight-Space-Programming/tree/51ce8acf253106cda939d855a5307783d1bd0b6c#3-build-and-score-a-released-model)
