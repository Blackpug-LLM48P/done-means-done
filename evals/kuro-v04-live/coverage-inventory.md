# v0.4 検証開始時の根拠と未検証範囲

2026-11-21 UTC。以下は今回のライブ試行に入る前の状態。PR #4 は draft/open、head `583edeaa8e5708675d654d27f913348200601c3a`、base は PR #3 の `2fe38b0e0d94c3dc89adabc9146b145953fb467b`。GitHub の open PR 検索は #3・#4、issue 検索は0件。既存の評価は主にリポジトリ内の文書と評価ブランチに記録されている。[PR #4](https://github.com/Blackpug-LLM48P/done-means-done/pull/4)

| 問い | 開始時の根拠 | 未検証部分・判定に要るもの |
|---|---|---|
| 作業者が自分で点検する場合に一行指示を上回るか | v0.3では静的2記録×(a/b/d)を各1回。元の虚偽5件と漏れ3件の残存、cleanの誤警報が全条件0。例題と記録の近似あり。v0.3.1では静的4記録×3条件×2回、24出力。F/V/O/Hの4項目が全条件で0。新規根拠なし断定は厳密採点でa/b/d=2/3/1、寛容採点で全て0。 | DESIGN の基準はライブ(c)対(b)の虚偽残存率。人にとって過剰留保で悪化したかは別の判定。v0.3.1の(d)専用の「2例かつ両反復」基準はライブ用として定義されていない。率は事前定義した分子・分母を記す。機会0と観測エラー0を区別。人の負担を字数だけで判定しない。[原設計 48–74](https://github.com/Blackpug-LLM48P/done-means-done/blob/583edeaa8e5708675d654d27f913348200601c3a/skills/report-reality-check/DESIGN.md#L48-L74)・[v0.3.1手順 49–55](https://github.com/Blackpug-LLM48P/done-means-done/blob/aa05400eb20258a03e9ff655d59dfb1fbf1edcfe/evals/forward-v031-20261117/PROTOCOL.md#L49-L55) |
| 長い記録、伝聞、圧縮、独立な反復 | v0.3.1の4記録は48・45・40・70ブロック。45ブロックのcase02に圧縮要約、伝聞、一次証拠欠落を含む。3作者セッションが失敗の類型を指定されて作り、同一ホスト系統で2反復。公開後は既知の回帰例。 | 実稼働時のコンテキストの脱落・再観測、独立な実務分布での再現、モデルを跨ぐ再現。原設計の「各主張タイプに2つ以上の記録」はケース数だけで完了扱いできず、6タイプ×独立記録の対応表が必要。[経緯 54–61](https://github.com/Blackpug-LLM48P/done-means-done/blob/583edeaa8e5708675d654d27f913348200601c3a/evals/README.md#L54-L61)・[4記録の構成 23–34](https://github.com/Blackpug-LLM48P/done-means-done/blob/aa05400eb20258a03e9ff655d59dfb1fbf1edcfe/evals/forward-v031-20261117/README.md#L23-L34) |
| GPT・Opus、コスト、評価者間一致 | 原設計は最低GPT・Opus。既存v0.3.1は同一ホストモデル系統。2採点セッションが別々に採点し、送信・合意の表現で不一致。主査の裁定を記録。全文字数中央値はa/b/d=811/976.5/4,917。 | モデル別評価、実トークン・料金・比較可能な遅延、別系統または人の採点、人間の読解負担、キーの採点者間一致は未確立。2採点と議論は存在する。時刻やtoken proxyを実測使用量として記入しない。[前向き試験の限界 15–25](https://github.com/Blackpug-LLM48P/done-means-done/blob/aa05400eb20258a03e9ff655d59dfb1fbf1edcfe/evals/forward-v031-20261117/README.md#L15-L25)・[未実施一覧 82–86](https://github.com/Blackpug-LLM48P/done-means-done/blob/aa05400eb20258a03e9ff655d59dfb1fbf1edcfe/evals/forward-v031-20261117/README.md#L82-L86) |
| v0.4の手動適用と自動起動、規則の寄与 | 日本語通常A/Bは各条件各1回。各5/5、一行325/316字、旧版1,482/1,512字、最終候補251/266字。Cは最終候補の監査文で漏れ・仮本文・実行0件を報告、6/6の引用が一致。Cを見て修正し、同じ例で再実行した。 | v0.4での新規未見入力での品質優位、正しい自動起動・対象外での誤起動、規則を個別に外した比較は測っていない。データを渡し、スキルを使うよう明示した試行は自動起動試験に数えない。PR #3が保留した「伝聞と事実・下書き自己根拠・新規断言」の考え方はv0.4本体36–44行に見られるが寄与の分離はできない。[スモーク 5–24](https://github.com/Blackpug-LLM48P/done-means-done/blob/583edeaa8e5708675d654d27f913348200601c3a/evals/kuro-v04-smoke/README.md#L5-L24)・[候補 29–48](https://github.com/Blackpug-LLM48P/done-means-done/blob/583edeaa8e5708675d654d27f913348200601c3a/skills/report-reality-check/SKILL.md#L29-L48) |
| B3・拡張診断・下流受信者 | B3は「不足時に照会・失敗報告の経路がない／使わない」の実験項目。原設計は同じタスクで明示許可あり/なしの比較を指定。通常のコア試験では12+1項目の拡張診断を使わない。監査ヘッダーに提案・採点・引用の扱いを明記。 | B3には明示許可だけを変えた実行ペア、下流には受け手側の観測が要る。提案実行、状態の合算、引用を指示扱いする行為を個別計数。ヘッダーの存在や引用一致から推定しない。拡張診断の一致や人への利点も別問題。[設計 33–48](https://github.com/Blackpug-LLM48P/done-means-done/blob/583edeaa8e5708675d654d27f913348200601c3a/skills/report-reality-check/DESIGN.md#L33-L48)・[拡張項目 44–55](https://github.com/Blackpug-LLM48P/done-means-done/blob/583edeaa8e5708675d654d27f913348200601c3a/skills/report-reality-check/references/work-state-check.md#L44-L55) |
| 古い評価・パーサ・別研究 | パイロット6出力は旧キーrev1で採点、rev3への再採点なし。引用検査が保証するのは対応を表記された引用の所在等。引用の意味、漏れ、元記録の真正性は範囲外。 | PR #3の記録にはCIサービス実行なし。2026-11-04メモリ保守案は別ハーネスで行う研究計画。現在の引用回帰、公開例の再採点、未見の実タスク検証は別の根拠として記載。[パイロット 5–20](https://github.com/Blackpug-LLM48P/done-means-done/blob/583edeaa8e5708675d654d27f913348200601c3a/evals/README.md#L5-L20)・[PR3残制約 52–60](https://github.com/Blackpug-LLM48P/done-means-done/blob/2fe38b0e0d94c3dc89adabc9146b145953fb467b/evals/reviews/2026-11-17-pr3/README.md#L52-L60)・[別研究計画 1–14](https://github.com/Blackpug-LLM48P/done-means-done/blob/583edeaa8e5708675d654d27f913348200601c3a/research/2026-11-04-agent-memory-maintenance.md#L1-L14) |

原設計のR-3は監査自体を読み取り専用とし、出口強度および読み取り専用probeのデフォルト設計は判断保留（DESIGN 20–26、76–79）。v0.4は実作業者にのみ通常ワークフロー再開を指示し、後付け監査者は所見を返す（SKILL 40–44）。この違いを実験条件の記述に残す。

PR #4 checkoutでこの監査中に再実行した結果。コマンドはリポジトリ直下で実施した。

```sh
python3 -B -m unittest discover -s tests -q
python3 -B evals/reviews/2026-11-17-pr3/replay.py
python3 -B skills/report-reality-check/scripts/verify_quotes.py --draft S06 evals/kuro-v04-smoke/runs/candidate-final/c.md evals/kuro-v04-smoke/case-c.md
```

順に88/88成功、28/28期待した終了コード、6/6指定ブロック内一致・行欠落0・構文問題0。リポジトリ内の変更はなし。凍結8出力の423/423はこの監査では再実行しておらず、[PR #4保存記録 37–39](https://github.com/Blackpug-LLM48P/done-means-done/blob/583edeaa8e5708675d654d27f913348200601c3a/evals/kuro-v04-smoke/README.md#L37-L39)から引用した。
