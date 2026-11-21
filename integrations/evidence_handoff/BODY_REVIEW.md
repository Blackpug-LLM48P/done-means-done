# 引き継ぎ本文と原票を照合する

この処理は案件、型付きの版、観測時刻、参照可能時刻、対象とチェックを照合し、指定時点で読めた記録と本文をレビュー担当に渡す。記録の出所には直接観測と伝聞の区別がある。訂正候補と元の引き継ぎ本文を別々に保存できる。操作予定やB1の状態はこの処理への入力に含まれない。

## 使用例

リポジトリのルートで、既存の図書配送の例を使う。原票では分室の職員が到着した3箱を受領している。

```sh
example=integrations/evidence_handoff/examples
work="$(mktemp -d)"
printf '%s' '南浜分室から3箱を受領した。' > "$work/handoff.txt"
python3 -B -m integrations.evidence_handoff.body_review prompt "$example/case.json" "$work/handoff.txt"
```

このプロンプトを独立したレビューセッションに渡す。下記は出力形式を確認するための手書きの応答例。実測時の呼び出しと応答は[評価記録](../../evals/kuro-v04-body/README.md)にある。

```sh
printf '%s' '{"findings":[{"sentence_id":1,"quote":"南浜分室から","reason":"O2では分室職員が受領した。","checked_refs":["O2"],"replacement":"南浜分室で"}]}' > "$work/review.json"
python3 -B -m integrations.evidence_handoff.body_review apply "$example/case.json" "$work/handoff.txt" "$work/review.json"
```

例の `proposed_body` は「南浜分室で3箱を受領した。」。`original_body` には「南浜分室から3箱を受領した。」が残る。モデルの指摘をゼロ件と判断したときは `clear`、原文の引用位置・参照先・形式を確認できた指摘があるときは `flagged`。JSONや参照先が不正な場合は `invalid` と理由を返し、候補文は `null` になる。提案の事実性や元の必須事項の保持は別に採点する。

`sentence_id` は1始まり、`start` と `end` は元本文のUnicodeコードポイントで数えた半開区間。レビューを依頼する際に `packet_sha256(case, body)` を保存し、その値を `apply_review(..., expected_packet_sha256=...)` またはCLIの `--packet-sha256` に渡すと、返答を適用するときに入力の差し替えを検査できる。
