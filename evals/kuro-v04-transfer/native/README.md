# 実モデルによる Codex ネイティブ圧縮

2026-11-21 UTC、`codex-cli 0.172.0-alpha.2`。今回追加で調べた経路では、圧縮前のモデル応答まで到達した新規 CLI スレッドは 0 件だった。両条件の圧縮後の保持率、モデル待ち時間、実トークン数、実費は欠測。

|今回追加で確認した経路|観測|
|---|---|
|既存の管理デーモンへの公式 CLI 照会 `codex app-server daemon version`|制御ソケットへの接続時に OS エラー 1。終了 1。|
|空の構成領域から、CLI がサポートする OS キーリングを指定して `login status`|OS がキーリングへの接続を拒否。終了 1。|
|空の構成領域で、メモリー内の認証ストアを明示して `login status`|未ログイン、終了 1。プロセスに提供できる公式例の ChatGPT プラン用 OAuth 環境変数 2 個も未設定。|
|既存ログインを CLI に任せ、`--ignore-user-config`、`--ephemeral`、一時 SQLite・ログ領域、履歴保存とシェルスナップショットの無効化を併用|in-process app-server の初期化時に読み取り専用ファイルシステム（OS エラー 30）。合成プロンプトへの応答・JSON イベントとも 0 件。|

Codex app-server の公式プロトコルには手動圧縮の `thread/compact/start` と、使用量の `thread/tokenUsage/updated` がある。この Work セッションから利用できる操作には、管理中の会話に対してこれらを実行・購読する機能が公開されていなかった。CLI の `cloud` が提供するのはタスク投入、状態、一覧、差分表示・適用で、同一スレッドの手動圧縮や使用量の購読はサブコマンドに含まれていない。外部のタスクは投入していない。

実行結果は `observed.json`。同じ診断は `python -B check_routes.py --try-model-startup` で表示できる。フラグを付けると既存ログイン経由で短い合成プロンプトを 1 回送る。この実行ではストレージ初期化で終了した。

公式仕様　[Codex App Server](https://developers.openai.com/codex/app-server/) ・ [Configuration Reference](https://developers.openai.com/codex/config-reference/) ・ [Sign in with ChatGPT for app-server](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server)
