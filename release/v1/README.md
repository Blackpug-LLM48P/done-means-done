# DMD v1.0 の進捗

基準はPR #16のv0.4候補。2026年11月22日（JST）、全文スキルを使う作業者と一行指示を使う作業者を比較するため、配布範囲を固定して未見案件の回収に着手した。

| 工程 | 判定 | 証跡 |
| --- | --- | --- |
| G1 本体と配布範囲 | 完了 | [配布候補7ファイル、通常引き継ぎと既存監査の互換範囲](SCOPE.md) |
| G2 評価計画の事前登録 | 完了 | [案件・モデル・採否基準](evaluation/PROTOCOL.md)、[GPTの隔離ダミー](evaluation/ISOLATION.md)、[独立検算](evaluation/input-crosscheck.json) |
| G3 未見の実作業、原記録の固定 | 完了（32/32提出） | [事前固定](https://github.com/Blackpug-LLM48P/done-means-done/commit/1ef97af3e3e2e8d1056464e086137e784690c4fb)、[GPT 16枠](evaluation/gpt-wave-summary.json)、[Opus 16枠](evaluation/opus-wave-summary.json) |
| G4 独立採点・人による読解 | 進行中 | [実納品の機械採点](evaluation/delivery-summary.json)。[報告の独立採点・裁定完了](evaluation/REPORT_SCORING.md)。実読解0/32 |
| G5 採否 | 保留 | 人による読解の実測待ち。[事前登録の採否基準](evaluation/PROTOCOL.md) |
| G6〜G8 RC・回帰・配布 | 未着手 | G5の判定後に配布対象を決める |

**本線8工程のうち完了3、残り5。** 8案件それぞれについて一行指示（B）とDMD全文（C）をGPT・Opusで1回ずつ実行。32枠すべてで、本人の2ターン目の最終報告を受領した。B1の受信側、R1の候補確認、別枠X1はこの比較の対象外。

## 登録と原記録

1. [本体と配布範囲](https://github.com/Blackpug-LLM48P/done-means-done/commit/b8a45305d5c823b08e313af7c143c974f9a7915f)を固定した。全7ファイルのSHA-256が一致し、基準checkoutの引用検査関連テストは88件通過した。
2. [条件・採点・停止規則](https://github.com/Blackpug-LLM48P/done-means-done/commit/c1c8cbc3ce3153550cf38b019d1a3f2731c4a354)を登録し、8案件を一度だけ抽選した。第4層には同一版の受付失敗と回復を表す明示的な履歴を含む。生成に用いた実装と入力・採点票のコミットメント、同一セッション2ターンの隔離ダミーは[この固定点](https://github.com/Blackpug-LLM48P/done-means-done/commit/865f547fffd8a1081afa80f1f297e17bde77b036)にある。
3. 8案件の期待納品物は、作業者の起動前に別実装で53ファイル・825セルを照合した。正例8件と、1セルを変えた負例53件が検算を通過した。これらは採点器の対照である。
4. GPTの16枠を実行担当と別の検収担当が独立に照合した。独立16セッション・32ターン、納品ファイル106点のハッシュと全報告のハッシュが記録に一致した。入力479,242＋出力34,037＝513,279トークン、欠測・再起動0件。採点前の記録として、運営側の原記録と別ホスト向け配布物を別々に保全した。[受領照合の再現手順](evaluation/RECEIPT_VERIFICATION.md)。

5. Opusは公式CLI 2.1.330、モデル `claude-opus-5-5`。補足検査で、本人用の入出力の作成・読戻し、採点・他作業者側の合成マーカーに対する不可視、ネットワーク分離、ツールなしの同一セッションでの2ターンを実証した。元のダミー試行1・2はいずれも初回提出の構文エラーで未完了と記録した。
6. Opus本番は独立16セッション、32ターン。各枠の原応答、実行コード、失敗の記録から再構成した2ターン目の依頼、最終報告が対応した。全件で説明文がコードブロックの外にあり、共通抽出器は応答全文を実行器に渡した。16件とも終了コード1の `SyntaxError`、納品0。説明の位置は前後12件、前のみ2件、後のみ2件。CLI表示額の合計は約3.31米ドル、実請求額は未取得。

## G4　実納品の機械採点

全32枠の提出を確認してから、事前登録済みの8組の鍵を開封し、入力と鍵のコミットメントを照合した。固定採点器は納品されたCSVのファイル名、列、行、セルを期待値と比較する。

| 系列・条件 | 最終報告の受領 | 必須CSVの内容一致 | 未納CSV | 誤内容・余分 |
| --- | ---: | ---: | ---: | ---: |
| GPT・一行 B | 8/8 | 53/53 | 0 | 0 |
| GPT・全文 C | 8/8 | 53/53 | 0 | 0 |
| Opus・一行 B | 8/8 | 0/53 | 53 | 0 |
| Opus・全文 C | 8/8 | 0/53 | 53 | 0 |

## 次の工程

32報告の独立64票と必要な裁定を記録した。[報告の採点表](evaluation/REPORT_SCORING.md) ／ [系列・条件・案件別の集計](evaluation/report-scores.json)。残るG4の工程は日本語読者4人×8報告の読解。現時点では実測0/32。G5の採否は保留。

| 運営側で保管するファイル | SHA-256 |
| --- | --- |
| `DMD_Opus_operator_handoff.zip` | `f63249d55dba34dfcefd294d9ad8a05295ce0d35fedb0ffdfa8700412ec3d382` |
| `DMD_G3_operator_records.zip` | `5aa850f4cbdaa76984200e90fefdd47babda29dfffe673eb763c925fdd97af66` |
| `DMD_Opus_returns.tar.gz` | `9ca20ba9607cd46163abbae2625ff9d29551f0b2e468da6af35a54f68f605f35` |
| `DMD_Opus_host_config.json` | `0937a17d1c4e907692063b214087423ba3d8427c3723dd9eaca7b4dd643b23a8` |
| `DMD_Opus_trial2_supplementary_check.tar.gz` | `1ea9f922121173a6c7bd4497210c9c9e5f2db8a3eee7fe5b9185c5b4483c3bb6` |
