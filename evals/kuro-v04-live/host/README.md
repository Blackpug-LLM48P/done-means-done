# Codex CLI の実コンテキスト圧縮に関する追加試行

## 既存ChatGPT認証での実モデル試行

2026-11-21 UTC。`codex-cli 0.172.0-alpha.2`、`codex login status` は `Logged in using ChatGPT`。既存認証のまま `gpt-6.2-astra`、通常速度 `default` を指定した。対象は新規の合成 `work/entries.tsv`。2件の差額を読み取り専用の実作業で求め、その証拠が揃った場合に公開プロトコルの `thread/compact/start` を呼び、同じスレッドで数値と監査の状態を尋ねる手順を組んだ。監査は提案されたのみ。実測では最初のモデル作業に到達しなかった。

|経路|停止地点|観測|
|---|---|---|
|stdio app-server、既定ストレージ|`initialize` の応答前|最初の診断無し接続は6.43秒で閉鎖。標準エラーを絞って収録した再試行は5.67秒、SQLiteコード14 `unable to open database file`、終了1。|
|stdio app-server、書き込み可能な一時SQLiteディレクトリ|`initialize` の応答前|6.58秒、`Read-only file system (os error 30)`、終了1。起動時に未認識設定が1件と表示されたが、その設定名は取得できていない。|
|`codex exec --ephemeral`、一時SQLite・ログディレクトリ|in-process app-server 初期化|6.15秒、`failed to initialize in-process app-server client: Read-only file system (os error 30)`、終了1。JSONイベント0件。|
|新しい空のCLI構成ディレクトリで認証とstdio初期化を検査|初期化成功、既存ログインを引き継がず|`codex login status` は終了1、`Not logged in`。`initialize` の応答を取得。合計0.23秒。資格情報を移送せず、この構成でモデルリクエストは送っていない。|

上の秒数は各ローカルプロセスまたは初期化確認の所要時間。既存ChatGPT認証での成功したモデル作業・圧縮要求・圧縮後の報告は各0件。この経路でモデル遅延、利用トークン、費用は取得できなかった。接続先の応答がないため、モデル側の対応状況・費用の値は判定不能。対照条件とv0.4の比較にも算入していない。

`clean_home_probe.py` と `clean_home_observation.json` に新しい空のCLI構成での初期化と認証結果を記録した。`host_probe.py` が公開stdioプロトコル版、`exec_probe.py` がCLI版。`host_observation.json` と `exec_observation.json` は一時ストレージを使用した実行の記録。`initial_observation.json` と `sqlite_diagnostic.json` は既定ストレージでの観測。`protocol_summary.json` はこのCLI自身が生成したスキーマのメソッド名の確認結果。認証情報や既存スレッドのデータは記録していない。

同じバージョンと既存のChatGPTログインがある環境で、次の順に実行する。観測ファイルは再実行時に上書きされる。

```bash
python -B host_probe.py
python -B exec_probe.py
python -B clean_home_probe.py
```

## 固定応答プロバイダーを使った実ホストの圧縮処理

実物の Codex CLI にローカルの決め打ち応答を接続し、新規の一時スレッドで圧縮前・圧縮・圧縮後の3要求を観測した。ホストは `thread/compact/start` を受理し、`item/started`、`item/completed`（いずれも `contextCompaction`）、`turn/completed`（`completed`）を返した。プロバイダー側で観測した各 `/v1/responses` 要求の `input` は次のとおり。

|ホストの段階|圧縮前のアシスタント出力専用マーカー|固定要約専用マーカー|
|---|---|---|
|最初のターン|なし|なし|
|圧縮用リクエスト|あり|なし|
|圧縮後の次ターン|なし|あり|

固定要約への置き換えが次ターンの送信内容に反映された。サービス側の意味的な要約、実モデルの推論、費用、実トークンはこの試行の対象外。0.97秒はローカル試験の経過時間。外部インターフェースが存在しないネットワーク名前空間で、合成データと空のCLI構成を使った。ローカル用 `modelProvider` は `offline_fixture`、モデル名は `fixture-stub`。このフィクスチャはプロジェクト指示を必要としないため `project_doc_max_bytes=0` とした。実ホストのアプリプロトコルと受信側で観測したマーカーを `offline/observation.json` に収録した。

```bash
unshare -Urn python -B offline/host_integration.py
```
