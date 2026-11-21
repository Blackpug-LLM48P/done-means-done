# 別モデルで公開課題を再実行する

2026-11-21時点で、この追試で新たに実行したClaude Opusのセッションは0件。利用可能な作業者モデルはGPT系で、接続済みのツールにAnthropic推論は含まれていなかった。Claudeプラグイン検索は該当0件で、ローカルのClaude CLIと対象サービスの設定を示す環境変数名も見つからなかった。公開の候補枝と実験枝に推論を委任するGitHub Actionsのワークフローはなかった。リポジトリには[Claudeによる旧版の試走](../../testlog-01/STRESS_CHECK_RUN01_claude.txt)がある。正解作成者がv0.2を採点した記録で、Opusの型番も今回の課題の納品も記載していない。

この補助ツールを使うと、公開主試験の16パケットを別ホストへ個別に渡し、返却された報告とCSVを元の採点器で再検査できる。実行にはPython 3.9以上と、[元の2コミット](../PROTOCOL.md)を含むGit履歴を使用する。以降はリポジトリのルートで実行する。

## パケットを渡す

```sh
python3 -B evals/kuro-v04-live/crossfamily/bridge.py export ./worker-packets
```

1件だけ出す場合は末尾に `--runs K17` を付ける。出力先には新しいディレクトリ名を指定する。各IDの `worker/` が作業用ディレクトリ、`dispatch.txt` がそのディレクトリをカレントにして送る依頼文。採点鍵・他の担当の出力・実行者用テンプレートを見せず、各担当に新規のセッションと専用の作業場所を割り当てる。元の公開課題・条件文・補助スクリプトの全ファイルを凍結時のSHA-256と照合する。ここで測れるのは公開済み課題の再実行である。

## 結果を受け取る

1件ごとに `returns/K17/REPORT.md`、`returns/K17/delivery/` と、実行者が記録した `returns/K17/runner.json` を置く。`runner-template.json` を複製し、実際のモデルIDを `model`、ホストまたはクライアントと版を `host`、実行を照合できる非機密の参照を `run_reference` に記す。`status` は納品なら `submitted`、実行の中断なら `interrupted` とする。`packet` と `packet_sha256` はテンプレートの値を保持する。

`usage` は実測値を取得できた場合のみ記入する。取得できなければ `null` のままにする。メトリクスごとに値が不明ならそのキーを省く。

| `usage` のキー | 記録する値 |
| --- | --- |
| `source`、`scope` | 用量表示や請求記録の出所、および対象範囲。例として、セッション全体か一呼出しか、キャッシュ・推論トークンをどのカウントに含むかを記す。 |
| `input_tokens`、`output_tokens` | ホストが報告した入出力トークン数。 |
| `reasoning_tokens`、`cache_read_input_tokens`、`cache_creation_input_tokens` | ホストが個別に報告した内訳。 |
| `elapsed_ms` | 実行者が観測した経過ミリ秒。計測の起点・終点は `scope` に記す。 |
| `billed_amount`、`currency` | 実際に取得した請求額の十進文字列と通貨コード。 |

```sh
python3 -B evals/kuro-v04-live/crossfamily/bridge.py ingest ./returns ./external-receipts --source-kind external-run
```

`raw/` は受領したバイト、`receipts.json` は原本のハッシュ、条件、CSVの合否、末尾改行を除く報告の文字数を保持する。実行記録のモデル名・使用量は実行者申告で、ツールによるプロバイダー認証は行わない。中断、未着、提出済みでCSVが欠落した場合を別に記録する。報告中の誤り、未確認の主張、伝え忘れはこの機械採点の対象外で、[元の盲検採点手順](../PROTOCOL.md)を使う。

## 実施した検算

```sh
python3 -B evals/kuro-v04-live/crossfamily/verify.py
python3 -B evals/kuro-v04-live/crossfamily/bridge.py ingest evals/kuro-v04-live/results ./archived-receipts --source-kind archived-replay
```

6テスト合格。16パケットすべてで作業者に渡すファイル集合・全バイトのハッシュ・依頼文を確認した。GPTによる公開済み16納品を `archived-replay` として取り込むと、全64ファイルのSHA-256、16報告の文字数、48件のCSV判定が元の受領記録に一致した。納品欠落、実行中断、誤ったパケット識別子、計測値の形式不備、未着の扱いは合成テストで確認した。合成テスト内のモデル名・用量・金額は計測結果に含めていない。
