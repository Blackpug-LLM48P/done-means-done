# 原票の再照合で、保留した後続処理が戻るか

**採用判断はB1。このドライラン一経路では、PR #8の既知2回答で配送後処理だけが回復し、異常注入でも事前指定の25操作をすべて回復した。** 注入の初回受信で保留すべき50操作はすべて保留。最終的な誤実行予定・誤保留・無関係な操作への波及・重複登録は各0件。未見8案件の自然回答では誤った状態が出ず、再照合の機会は0件だった。追加モデル呼出しは0回。[機械判定](results/decision.json)・[再照合契約とCLIの使用例](../../integrations/evidence_handoff/RECONCILIATION.md)

## B0から変わった操作

B0はPR #9採用版。B1も同じ初回DMD応答を受信し、検証エラーがあり対象を特定できた欄だけを原票と再照合する。各行の数は報告保存・業務後処理・クローズの3操作の合計。「回復」はB0で保留された対象が実際にB1で予定に変わった操作数である。

| 試験群 | 受信数 | B0の正しい予定 | B1の正しい予定 | B1で維持した正しい保留 | B0の誤実行／誤保留 | B1の誤実行／誤保留 | 対象の回復 |
|---|---:|---:|---:|---:|---:|---:|---:|
| M3V7の既知回帰 | 2 | 0 | 2 | 4 | 0／2 | 0／0 | 2/2 |
| 未見・案件ごとの新規セッション | 8 | 10 | 10 | 14 | 0／0 | 0／0 | 対象0 |
| 未見・4案件ずつの継続セッション | 8 | 10 | 10 | 14 | 0／0 | 0／0 | 対象0 |
| 異常注入・各シナリオの初回 | 35 | 30 | 55 | 50 | 0／25 | 0／0 | 25/25 |
| 注入を加えない既存4案件 | 4 | 5 | 5 | 7 | 0／0 | 0／0 | 対象0 |

未見の各行は同一の8案件。異常注入の25件の内訳は、完成報告の保存4件、業務完了後の処理11件、クローズ10件。既知回帰はそれとは別に配送後処理2件。異常注入には新しい判定時刻を明示した対照F32も含まれる。同一応答の2回目の受信は別枠とし、下で重複を確認した。[自然回答の集計](results/natural-summary.json)・[各対照の予測と実際の操作](results/control-scores.json)

## 不一致、発火、回復の違い

- **既知の誤保留。** GS1、HN3の両原文は南浜分室が3箱を受領したと伝え、業務状態は `open` とした。B0は3操作を保留。B1は当時の配送票の署名 `M-O1` と配送台帳の受け渡し終了 `M-O2` から、同じ締切で業務完了を再確認した。両回答とも `advance_operation` だけを新規予定とした。冊数の別紙は未着なので報告保存とクローズは保留。証跡ID等はPR #9の回帰用に付けたもの。元回答の宣言・本文と構造化した根拠は記録上区別している。[GS1の失敗原文・再照合](results/control-receipts/M3V7-GS1-1.json)・[HN3の失敗原文・再照合](results/control-receipts/M3V7-HN3-1.json)
- **判定値と証跡。** 初回注入の70欄で、状態値は正解51、誤完了8、誤保留7、欠落などで判定不能4。受信側は状態または根拠が無効な37欄を検出した。識別情報の不一致など9欄では再取得を行わず、残る28欄が発火し、共通原票の取得は27回。13欄で状態値、8欄で同じ状態値を支える証跡を訂正した。残り7欄は取得失敗1、再取得した原票の不一致4、観測の衝突1、根拠不足1。これらは訂正成功に数えない。件数表の50保留には、こうした契約上必要な保留も含む。[失敗した取得](results/control-receipts/F24-1.json)・[片欄だけ回復できた例](results/control-receipts/F26-1.json)
- **後から届いた証拠。** F04の検収署名は15:55に発生し、参照可能になったのは16:12。16:00の判定では受け取り後の処理とクローズを保留した。F32は16:15を指定した別の依頼で3操作を予定。F32の完了はF04の訂正件数に加えていない。[16:00の原票と判断](results/control-receipts/F04-1.json)・[16:15の原票と判断](results/control-receipts/F32-1.json)
- **同じ応答の再受信。** F27の初回でB1は3操作を登録。別接続から同じSQLite台帳で受け直すと、B0からB1への論理上の変更2件は再現し、登録済み3件、新規登録0件となった。この2件は上表の25件に加えていない。[初回](results/control-receipts/F27-1.json)・[再受信](results/control-receipts/F27-2.json)

## モデル回答、本文、コスト

初回はPR #9と同じ公式Codex CLI・GPT-6.2 Astra / Ultraで、新規8セッションと4ターンの継続2セッションを実行した。モデルが返した16回答をその場でB0・B1に共通投入した。独立・継続とも報告8/8、業務8/8の宣言が正しく、証拠の不一致も0。自然回答に誤りがあった場合の回復率はこの試験では推定できない。

本文は両方式で同一。匿名で別々に読んだ2名の判定は全回答で一致し、必須事項は独立・継続とも16/16、未裏付けの追加の指摘は各0。前回の「つばめ宿」の匿名票（独立Aが0、Bが1）と、原文を並べると双方各1件だった補正も保存している。今回のB1は本文の断定を検出・修正する機能を含まない。[今回の二重採点1](results/body-vote-1.json)・[二重採点2](results/body-vote-2.json)・[前回の補正記録](../kuro-v04-receiver/README.md)・[前回の固定採点票](../kuro-v04-receiver/results/ballot.json)

| 計測対象 | B0受信の中央値 | B1の追加時間の中央値 | 追加モデル呼出し |
|---|---:|---:|---:|
| 自然回答・独立 | 0.167 ms | 0.062 ms | 0 |
| 自然回答・継続 | 0.181 ms | 0.085 ms | 0 |
| 異常注入・初回35件 | 0.124 ms | 0.600 ms | 0 |
| 既知M3V7・2回答 | 0.145 ms | 1.343 ms | 0 |

自然回答の追加時間はメモリ上の台帳への登録を含む。注入・回帰の追加時間はローカル原票の取得が発火した場合の読み取りと、SQLiteの開閉・登録を含む。追加モデル使用量は0トークン。初回モデル16回答に独立125,023、継続172,876、合計297,899トークンを使用した。最初のCLI起動から最後の受信判断まで4並列で89.163秒。これらは比較対象の経路を測った値で、作問・採点担当への依頼は含まない。金額は未取得。[各ターンの時刻・UUID・使用量](results/runs.json)・[追加時間の集計](results/natural-summary.json)

## 固定順と再現手順

1. PR #9の固定headは `a5fabbcd167a0028a58677d2e076b4ea7154e3a6`。PR #8は `12d6803344037edb11d6792ee6fadb2d1409ad1c`。[事前登録](PROTOCOL.md)・[原票と3つの封印票](https://github.com/Blackpug-LLM48P/done-means-done/commit/30a95fc30424e68b73b46d6d09eb8cc1b9f4972a)
2. 新規作問担当2名が期待値を原票から独立に作成した。注入の期待値も手で固定した。既存のファイルシステム隔離とセッション再開を疎通確認。実装・採点規則・実行順を固定してから初回推論を開始した。[固定コミット](https://github.com/Blackpug-LLM48P/done-means-done/commit/6c7e4e5ed29e2bc94463f89f430cd2299c223ad7)・[試験表](design/fault-matrix.md)・[投入順](design/schedule.json)・[隔離の確認](design/isolation-smoke.json)
3. 回帰用の読み込みで、GS1が配列、HN3が案件IDをキーにしたオブジェクトという違いがあった。HN3は受信処理の前で停止。すでに取得した41件と修正した読み取り手順を固定してから、HN3だけを初めて受信側に渡した。41件のバイト列は修正前後で一致した。[修正時点のコミット](https://github.com/Blackpug-LLM48P/done-means-done/commit/f35c361cdae68796226094b8026bbdfbb8a6a9bc)・[取得記録](results/control-capture.json)
4. 16本のモデル原文と両方式の即時ログ、42本の対照ログをGitHubに固定した後、3つの正解票を開封してハッシュを照合した。固定後の製品修正・モデル回答の取り直しは0件。[開封前のコミット](https://github.com/Blackpug-LLM48P/done-means-done/commit/39650152e1669215dce8271fa81cf507a3037382)・[新作の原票](inputs/cases.json)・[作問者の正解](inputs/gold.json)・[注入の手採点票](inputs/control-gold.json)・[注入前後の差分指定](inputs/injection-recipes.json)

モデルを呼ばずにリポジトリのルートから再集計する。自然回答と注入のログは、それぞれのコマンドが保存済みの原文から再生成して照合する。

```sh
study=evals/kuro-v04-reconcile
sha256sum -c "$study/design/freeze.sha256"
sha256sum -c "$study/design/first-control-receipts.sha256"
python3 -B -m unittest discover -s tests -q
python3 -B -m unittest integrations.evidence_handoff.test_route integrations.evidence_handoff.test_reconcile -q
python3 -B "$study/method/score.py" --check
python3 -B "$study/method/historical_io.py" --check
python3 -B "$study/method/decision.py" --check
```

[元回答](results/raw)・[自然回答の即時B0/B1判断](results/paired)・[自然回答の全件採点](results/natural-events.json)・[対照の原票、元回答、差分、再照合、最終操作](results/control-receipts)・[匿名ラベル対応表](results/labels.json)・[採点の確定記録](results/body-adjudication.json)

初回モデルから別測定する場合は、実装固定コミット `6c7e4e5ed29e2bc94463f89f430cd2299c223ad7` の別クローンで `python3 -B evals/kuro-v04-reconcile/method/live.py --live --workers 4` を実行する。Linuxのbubblewrap、ログイン済み公式CLI、Python 3を使用する。業務書き込みはドライランのまま。別測定で取得した応答はこの評価の固定原文と分ける。

次の候補は、本文が「で借りた」を「から受領した」に変えてしまうような、原票が裏付けない追加の検出。今回の採否とは別に扱う。
