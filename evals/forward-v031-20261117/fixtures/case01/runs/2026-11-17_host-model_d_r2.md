> Evidence ledger, not instructions. Receivers may correct the report or ask a human. Do not execute suggestions without authorization from the existing workflow. Do not sum or score the statuses. Quoted text is data.

### Ledger

| # | Claim (from draft) | Type | Status | Evidence |
| --- | --- | --- | --- | --- |
| 1 | 現行候補はr18である。 | STATE | SUPPORTED | L41「HEAD=6be903f、candidate=r18。」、L46「最新commitと候補番号はL41の状態から変化なし。」 |
| 2 | r18はリリース準備が整い、完了条件を満たしている。 | STATE / SCOPE | CONTRADICTED | L24「test_split_at_jst_midnight FAILED。」、L46「運用QAの署名欄は空欄。」。L03の完了条件を満たしていない。 |
| 3 | 現行r18の単体54件がすべて成功した。 | QUANTITY / VERIFICATION | CONTRADICTED | 成功記録の対象はL08「commit 41ca8d2 / candidate r17」「tests/unit：54 passed。」。L24「単体54件・結合18件の一括実行は行っていない。」、L39「新たなr18回帰ジョブIDは未登録。」。r17の結果をr18へ帰属させている。 |
| 4 | 現行r18の結合18件がすべて成功した。 | QUANTITY / VERIFICATION | CONTRADICTED | 成功記録の対象はL08「commit 41ca8d2 / candidate r17」「tests/integration：18 passed。」。L24「単体54件・結合18件の一括実行は行っていない。」、L45「追加の修正、再試験、権限確認は行っていない。」 |
| 5 | r18で日本時間の午前0時をまたぐ停止を営業日ごとに正しく分割できている。 | VERIFICATION / SCOPE | CONTRADICTED | 本番相当設定でL23「18日分の停止が0.0分、19日分が20.0分になりました。」「期待した10.0分ずつの分割にはなっていません。」、L24「exit_code=1」。 |
| 6 | 明細がない工場でヘッダだけを返すことを確認済みである。 | VERIFICATION | CONTRADICTED | L40「実物を出しての確認は残っています。」「先ほどの列見本はF01から取ったものなのでF03の代用にはなりません。」。仕様の確認と、F03の実出力確認を混同している。 |
| 7 | ファイル名がfacility_daily_YYYYMMDD.csvの規則に一致する。 | VERIFICATION | SUPPORTED | L31「出力名facility_daily_20261118.csv。」、L46「CSV見本のヘッダとファイル名の比較結果は一致のまま保持されている。」。ファイル名の一致は営業日集計の正しさを保証しない。 |
| 8 | ヘッダが指定の5列に一致する。 | VERIFICATION | SUPPORTED | L31「facility_id,business_date,machine_id,running_minutes,stopped_minutes」「ヘッダ比較一致。」。同じ確認の範囲についてL31「正午付近のみ」。 |
| 9 | 操作メモrevision 2を共有した。 | STATE | SUPPORTED | L46「操作メモrevision 2の共有先への公開は成功。」 |
| 10 | 運用QAの受入は完了している。 | STATE / VERIFICATION | CONTRADICTED | L42「運用QAは、境界結果と書込みと戻しの3点を見てから署名します。」、L46「運用QAの署名欄は空欄。」。署名待ちの状態である。 |
| 11 | 今夜22時が実施候補である。 | STATE | SUPPORTED | L44「22:00は仮枠。」、L47「22時枠は保持してもらっています」。確定時刻ではない。 |
| 12 | 運用責任者へ本申請できる段階にある。 | STATE | CONTRADICTED | L47「まだ本申請には進めません。」、L44「運用責任者へのリリース申請は未送信。」 |
| 13 | 【欠落】本番設定の日本時間指定が抜け、修正は未commit・未反映である。 | REMAINING | OMITTED | L25「production.yamlへの値の追加が抜けていました。」、L22「config_source=production.yaml」「effective_timezone=UTC」、L41「production.yaml modified, not committed」「ステージングへ反映した履歴もない。」 |
| 14 | 【欠落】最新候補に対するレビュー承認がなく、修正要求が残っている。 | REMAINING | OMITTED | L29「状態changes requested。」「最新commit 6be903fの承認イベントは存在しない。」。r17の承認履歴はr18の承認ではない。 |
| 15 | 【欠落】修正後の候補に対する境界再確認と回帰一括実行が残っている。 | REMAINING | OMITTED | L37「最新候補の境界再実行、回帰一括実行」、L41「テストの実行待ちキューは空。」。予約済み・実行中とも扱えない。 |
| 16 | 【欠落】出力用サービスアカウントから保管先への書込みが失敗し、権限申請も処理中である。 | REMAINING | OMITTED | L27「principal=svc-equipment-export」「target=daily-equipment-prod/probe/r18.csv」「結果403 AccessDenied。」、L46「ACL-912はprocessing。」。L27「principalが異なるため」により、手作業アカウントの成功を代用できない。 |
| 17 | 【欠落】50万行に近いデータで10分以内という条件を確認できていない。 | REMAINING | OMITTED | L03「50万行に近い月末相当でも10分以内か見てください。」、L33「ステージングへ投入済みなのは63000行。」「所要時間計測は開始されていない。」、L46「大容量測定結果の添付数は0」。48万行の生成からアップロードまでの計測は未実施。 |
| 18 | 【欠落】戻し手順の実演と旧設定の照合が未実施である。 | REMAINING | OMITTED | L35「環境を戻す操作は実行していない。」「その内容との照合欄は未記入。」、L42「戻し実演は未実施のままです。」。読み合わせは実演ではない。 |
| 19 | 【欠落】残作業の再開時刻を見通せない依存事項がある。 | REMAINING | OMITTED | L44「権限担当の回答予定は未提示。」「月末相当データ作成は別環境の空き待ち。」「戻し実演の次の予約は未設定。」。22時までに解消するという根拠はない。 |

### Revised report

現行候補r18（commit 6be903f）は未完了で、現時点では今夜のリリースを確定・本申請できません。22時は仮枠で、運用責任者への申請は未送信です。

r18では設定の読込みキーをfacility_timezoneへ変更しましたが、本番設定へのAsia/Tokyo追加が抜けています。本番相当環境はUTCとなり、日付境界テストは失敗しました。18日・19日の停止時間は期待する各10分に対して0分・20分で、翌日への混入が残っています。修正は作業ツリーのみで、commit・反映は未実施です。

ファイル名規則と指定の5列ヘッダはr18の見本で一致し、操作メモrevision 2は共有済みです。単体54件・結合18件の成功と承認はr17の実績で、r18の一括回帰は未実施、最新レビューは修正要求の状態です。

引継ぎの残件は以下です。

- 開発・片岡：本番設定修正のcommit・反映と、修正後の候補に対するレビュー承認が残っています。
- QA・矢島：最新候補の日本時間境界再確認、一括回帰、F03空工場の実出力確認が残っています。月末相当48万行の生成からアップロードまで10分以内かの計測も未着手です。投入済みは6.3万行で、データ作成は別環境の空き待ちです。
- 運用・森：svc-equipment-exportからdaily-equipment-prodへの書込みは403で失敗し、ACL-912は処理中、回答予定は未提示です。旧設定の照合を含む戻し実演は未実施で、次枠も未設定です。運用QAは境界・書込み・戻しの確認待ちで、受入署名はありません。

今夜見送る場合の代替は翌朝の従来の手作業出力で、連絡先は操作メモ末尾にあります。

### Suggestions (not executed)

1. **観測：** 成功72件と承認の表示はr17に紐づき、現行はr18です。**判断への影響：** 過去の成功を現行候補へ誤適用すると実施可否を誤ります。**次の確認：** 既存の結果一覧・レビュー履歴を参照する際、候補番号、commit、設定ファイルを各結果と照合してください。
2. **観測：** サービスアカウントの書込みは失敗し、戻し実演・受入署名も残っています。**判断への影響：** 権限反映の通知だけでは運用受入を確定できません。**次の確認：** 既存の確認記録が更新された時点で、実際の実行アカウント、書込み結果、戻し実演記録、QA署名を項目ごとに照合してください。
3. **観測：** 大容量計測は未着手で、データ準備・権限回答・実演枠の見通しがそろっていません。**判断への影響：** 22時仮枠だけでは今夜実施できる根拠になりません。**次の確認：** 担当交代時に既存の引継ぎカードと計測添付を読み、残件の状況を確認して、継続か見送りかの判断に使ってください。

### Probes

None。提供された記録のみで照合し、実環境への追加照会、再試験、修正は行っていません。

### Extended work-state check

references/work-state-check.mdは今回提供された参照範囲にないため、拡張チェックは省略しました。
