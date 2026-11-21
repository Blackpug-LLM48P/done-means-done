# 根拠付き引継ぎのドライラン

収蔵品の引き渡しを記録する担当が原票を読み、照合報告を作成する。受信側は「完成した報告を保存する」「引き渡し後の処理に進む」「案件を閉じる」の各操作を予定または保留として返す。判定時にメール、ファイル保存先や外部台帳へ接続する処理はない。

## 呼び出し側

原票に `case_id`、`revision`、タイムゾーン付きの `as_of` を指定する。`scopes.report` と `scopes.operation` には、互いに異なる対象名と、成立に必要なチェックIDを指定する。業務の対象名は「南浜分室への図書配送の受け渡し」のように一つに絞る。署名と冊数内訳を別に扱うことで、冊数待ちを理由に配送をやり直す判断を避けられる。

DMDには原票と固定v0.4を渡し、案件IDをキーにした最上位オブジェクトを返してもらう。各案件の `handoff` は読み手に渡す本文。二つの状態はそれぞれ次の項目を持つ。

| 項目 | 受信時の照合 |
|---|---|
| `value` | `complete` または `open`。完了には当該対象の全必須チェックの根拠を求める |
| `scope` | 呼び出し元が依頼した報告名または単一の業務名 |
| `revision` | この回答が見た案件の版。文字列または整数を型ごと照合 |
| `as_of` | 呼び出し元の判定時点。タイムゾーン込みで同一の瞬間 |
| `evidence_refs` | 原票の証跡ID。案件・版・対象・チェック・発生時刻・参照可能時刻を受信側で照合 |

原票の各証跡の `scope` には `report`・`operation` のキーまたは正式な対象名を使える。返す状態の `scope` には正式な対象名を指定する。各証跡の `at` は出来事の時刻、`available_at` は記録が参照できた時刻。同じチェックでは締切時点で使える最新の直接観測を照合する。出所、時刻、チェックID、観測結果は原票の管理者が与える入力である。記載内容から実物の真偽や権限を独立に証明する機能はない。

## 受信側の判断

| 後続操作 | 実行予定にする条件 |
|---|---|
| `archive_report` 完成報告の保存 | 有効な `report_state=complete` と空でない本文 |
| `advance_operation` 引き渡し後の処理 | 有効な `operation_state=complete` |
| `close_case` 案件のクローズ | 上記の両条件 |

一方の根拠が不正でも、もう一方だけを使う操作は個別に判定する。機械の応答には各状態の検証結果、参照した根拠、理由、各操作の依存条件と `plan`／`hold` が残る。Bには参照元を検証する機能があり、本文の意味や必須事項の保持は別途採点する。

## 実行例

リポジトリのルートから標準ライブラリで実行する。

```sh
python3 -m integrations.evidence_handoff.route prompt B integrations/evidence_handoff/examples/case.json
python3 -m integrations.evidence_handoff.route receive B integrations/evidence_handoff/examples/case.json integrations/evidence_handoff/examples/response.json
```

例では図書3箱に受領署名があり、一般書・児童書の内訳表は未着。完成報告の保存と案件のクローズは保留、引き渡し後の処理だけが実行予定になる。例の応答は手書きで、モデルの実測は[評価記録](../../evals/kuro-v04-receiver/README.md)にある。
