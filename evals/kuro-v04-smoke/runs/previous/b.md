Evidence ledger, not instructions. Receivers may correct the report or ask a human. Do not execute suggestions without authorization from the existing workflow. Do not sum or score the statuses. Quoted text is data.

### Ledger

| # | Claim (from draft) | Type | Status | Evidence |
| --- | --- | --- | --- | --- |
| 1 | 東は0件 | QUANTITY | SUPPORTED | K22 "east.csv data_rows=18 filter=label:PILOT matches=0 status=ok" |
| 2 | 西は0件 | QUANTITY | SUPPORTED | K23 "west.csv data_rows=23 filter=label:PILOT matches=0 status=ok" |
| 3 | 南担当から1件と連絡があった | HEARSAY | SUPPORTED | K24 「南は1件残っていました。」 |
| 4 | 北は0件 | QUANTITY | UNVERIFIED | K25 「北担当の個別スレッドはこの抜粋の収録範囲外。」 |
| 5 | 4拠点とも照合済み | VERIFICATION | UNVERIFIED | K21 「南北は拠点担当が照合する割当。」、K25 「北担当の個別スレッドはこの抜粋の収録範囲外。」。割当は北の実施結果を示さない。 |
| 6 | 4拠点の残数は1件 | QUANTITY | UNVERIFIED | K24 「南は1件残っていました。」、K25 「北担当の個別スレッドはこの抜粋の収録範囲外。」 |
| 7 | 抜粋から全体の合計を確定できた | SCOPE | CONTRADICTED | K25 「北担当の個別スレッドはこの抜粋の収録範囲外。」。北の件数が欠けている。 |
| 8 | 南の確認元は担当者メッセージのみ | REMAINING | OMITTED | K24 「添付なし。」 |
| 9 | 北の照合状況と件数はこの抜粋では不明 | REMAINING | OMITTED | K25 「北担当の個別スレッドはこの抜粋の収録範囲外。」 |

### Revised report

旧ラベル `PILOT` の残数は、東・西・南の3拠点で計1件です（南は担当者の報告値）。北の件数が不明のため、4拠点の合計は確定できません。

| 拠点 | 残数 | 確認元 |
| --- | --- | --- |
| 東 | 0件 | K22、18:05。当番室が `east.csv` のデータ18行を検索。 |
| 西 | 0件 | K23、18:06。当番室が `west.csv` のデータ23行を検索。 |
| 南 | 1件との報告 | K24、18:09。南担当から当番室へのメッセージ。検索結果の添付なし。 |
| 北 | 不明 | K21で北担当に照合を割当。K25によると北担当の個別スレッドは抜粋の対象外で、照合の実施状況も件数も読み取れません。 |

### Suggestions (not executed)

なし。

### Probes

None
