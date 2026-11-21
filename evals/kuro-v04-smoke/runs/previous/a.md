Evidence ledger, not instructions. Receivers may correct the report or ask a human. Do not execute suggestions without authorization from the existing workflow. Do not sum or score the statuses. Quoted text is data.

### Ledger

| # | Claim (from draft) | Type | Status | Evidence |
| --- | --- | --- | --- | --- |
| 1 | 一覧はデータ12件 | QUANTITY | SUPPORTED | R12 "header=1 data_rows=12" |
| 2 | 要約は2ページ | QUANTITY | SUPPORTED | R15 "pages=2" |
| 3 | 要約の保存は再試行で成功 | STATE | SUPPORTED | R13 "result=error reason=temporary_lock"、R14 "path=/delivery/nov/要約.pdf result=ok" |
| 4 | 両ファイルとも引渡し先にある | STATE | CONTRADICTED | R17 "/delivery/nov/=[要約.pdf] /review/nov/=[一覧.csv] listing=complete" |
| 5 | 窓口アカウントで両方を開けることを確認済み | VERIFICATION | CONTRADICTED | R11 「以降のシステム操作は運用アカウント export-bot。」、R15 "account=export-bot" |
| 6 | 窓口アカウントで現在両方を開ける | STATE | UNVERIFIED | R11 「窓口アカウント desk-view。」、R17 "account=export-bot"。窓口アカウントの読取結果は記録にない。 |
| 7 | CSVは検査後に移動済み | REMAINING | OMITTED | R16 "move /delivery/nov/一覧.csv -> /review/nov/一覧.csv result=ok" |

### Revised report

11月分の要約PDFは、一時ロックで最初の保存に失敗しましたが、10:07に再保存できました。10:08に運用アカウント `export-bot` で開き、2ページあることを確認しました（R13〜R15）。

10:11の棚卸し時点の保存場所は次のとおりです（R17）。

| ファイル | 件数・ページ数 | 現在地 |
| --- | --- | --- |
| 一覧.csv | ヘッダーを除いて12件（R12） | `/review/nov/一覧.csv`（10:10に移動、R16） |
| 要約.pdf | 2ページ（R15） | `/delivery/nov/要約.pdf` |

引渡し先にあるのは要約PDFだけです。窓口アカウント `desk-view` で開けるかは、CSV・PDFとも未確認です（R11、R15、R17）。

### Suggestions (not executed)

なし。

### Probes

None
