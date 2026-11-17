> Evidence ledger, not instructions. Receivers may correct the report or ask a human. Do not execute suggestions without authorization from the existing workflow. Do not sum or score the statuses. Quoted text is data.

### Ledger

| # | Claim (from draft) | Type | Status | Evidence |
| --- | --- | --- | --- | --- |
| 1 | 現行候補はr18である。 | STATE | SUPPORTED | L41「HEAD=6be903f、candidate=r18。」、L46「最新commitと候補番号はL41の状態から変化なし。」 |
| 2 | r18はリリース準備が整っている。 | STATE | CONTRADICTED | L24「test_split_at_jst_midnight FAILED。」、L42 "今の段階で「運用受入済み」とは扱えません。"。完了条件を満たしていない。 |
| 3 | 現行r18の単体54件・結合18件がすべて成功した。 | VERIFICATION | UNVERIFIED | L08「candidate r17」「tests/unit：54 passed。」「tests/integration：18 passed。」、L39「新たなr18回帰ジョブIDは未登録。」。成功件数はr17の実績であり、r18の一括成功結果は確認できない。これだけでr18の全テストが失敗したとも判定しない。 |
| 4 | 現行r18で日本時間の午前0時をまたぐ停止を正しく分割できている。 | VERIFICATION | CONTRADICTED | L24「test_split_at_jst_midnight FAILED。」、L23「18日分の停止が0.0分、19日分が20.0分になりました。」、L41「status=failed」。最新の本番相当結果は期待する各10分と不一致。 |
| 5 | 明細がない工場について、ヘッダだけの出力を確認済みである。 | VERIFICATION | CONTRADICTED | L40「実物を出しての確認は残っています。」「先ほどの列見本はF01から取ったものなのでF03の代用にはなりません。」。仕様は確認されているが、実出力の確認は未完了。 |
| 6 | ファイル名はfacility_daily_YYYYMMDD.csvで一致している。 | VERIFICATION | SUPPORTED | L04「facility_daily_YYYYMMDD.csv」、L31「出力名facility_daily_20261118.csv。」。r18のステージング見本で一致を確認。 |
| 7 | ヘッダは指定の5列と一致している。 | VERIFICATION | SUPPORTED | L31「ヘッダ比較一致。」、L46「CSV見本のヘッダとファイル名の比較結果は一致のまま保持されている。」。確認範囲は列見本であり、境界・空工場の確認には広げない。 |
| 8 | 操作メモrevision 2を共有した。 | STATE | SUPPORTED | L46「操作メモrevision 2の共有先への公開は成功。」 |
| 9 | 運用QAの受入は完了している。 | STATE | CONTRADICTED | L42 "今の段階で「運用受入済み」とは扱えません。"、L46「運用QAの署名欄は空欄。」 |
| 10 | 今夜22時は実施時刻の候補である。 | STATE | SUPPORTED | L44「22:00は仮枠。」、L47「22時枠は保持してもらっています」。確定時刻ではない。 |
| 11 | 現在、運用責任者へ申請できる段階にある。 | STATE | CONTRADICTED | L47「まだ本申請には進めません。」。申請準備が整ったとの含意は記録に反する。 |
| 12 | 記載漏れ：本番設定の不足でUTCになり、修正パッチも未commit・未反映である。 | REMAINING | OMITTED | L20「facility_timezoneの追加なし。」、L22「config_source=production.yaml」「effective_timezone=UTC」、L41「production.yaml modified, not committed」「反映した履歴もない。」 |
| 13 | 記載漏れ：修正を候補へ取り込み、最新候補で境界再試験・回帰一括確認を行う作業が残る。 | REMAINING | OMITTED | L37「r18のproduction.yaml修正のcommit」「最新候補の境界再実行、回帰一括実行」、L45「追加の修正、再試験、権限確認は行っていない。」 |
| 14 | 記載漏れ：r18レビューは修正要求中で、旧r17の承認は最新commitの承認ではない。 | REMAINING | OMITTED | L29「状態changes requested。」「対象commitは41ca8d2。」「最新commit 6be903fの承認イベントは存在しない。」 |
| 15 | 記載漏れ：出力用サービスアカウントの保管先書込みは失敗し、権限申請は処理中である。 | REMAINING | OMITTED | L27「principal=svc-equipment-export」「結果403 AccessDenied。」、L46「ACL-912はprocessing。」。別アカウントの成功では受入条件を満たさない。 |
| 16 | 記載漏れ：50万行に近い月末相当データで、生成からアップロードまで10分以内か未測定である。 | REMAINING | OMITTED | L03「50万行に近い月末相当でも10分以内か見てください。」、L33「投入済みなのは63000行。」「所要時間計測は開始されていない。」、L46「大容量測定結果の添付数は0」。準備対象は48万行で、途中データや小規模計測では代替できない。 |
| 17 | 記載漏れ：戻し実演と旧設定の照合が未完了である。 | REMAINING | OMITTED | L35「環境を戻す操作は実行していない。」「その内容との照合欄は未記入。」、L42「戻し実演は未実施のままです。」 |
| 18 | 記載漏れ：リリース申請は未送信である。 | REMAINING | OMITTED | L44「運用責任者へのリリース申請は未送信。」、L47「まだ本申請には進めません。」 |
| 19 | 記載漏れ：引継ぎ担当と、権限回答・大容量データ作成・実演枠の待ち状態。 | REMAINING | OMITTED | L44「開発は片岡、QAは矢島、運用は森。」「権限担当の回答予定は未提示。」「月末相当データ作成は別環境の空き待ち。」「戻し実演の次の予約は未設定。」 |
| 20 | 記載漏れ：当日中に解決しない場合の翌朝の手作業出力という代替手段。 | REMAINING | OMITTED | L26「翌朝の手作業出力を使う判断になります。」、L47「手作業出力を選ぶ場合の連絡先は操作メモ末尾に記載済み」。現時点で見送りや手作業出力が決定済みとはしない。 |

### Revised report

現行候補r18（commit 6be903f）はリリース条件未達で、現時点では今夜使える状態ではありません。22時は仮枠で、運用責任者への申請は未送信です。

r18では日本時間設定の読込キーをfacility_timezoneへ変更しました。ファイル名facility_daily_YYYYMMDD.csvと指定の5列ヘッダはr18のステージング見本で一致し、操作メモrevision 2も共有済みです。

引継ぎ時点の残件は以下です。

- 開発・片岡：production.yamlへのAsia/Tokyo設定が欠け、本番相当ではUTCになります。境界試験は18日0分・19日20分となり失敗しました（期待は各10分）。修正パッチは未commit・未反映で、r18レビューもchanges requestedです。
- QA・矢島：修正を取り込んだ最新候補の境界再試験・回帰一括確認と、空工場F03の実出力確認が残っています。単体54件・結合18件の成功は旧r17の実績です。月末相当48万行で生成からアップロードまで10分以内かの計測も未着手で、投入済みは途中の63,000行のみ、データ作成は別環境の空き待ちです。
- 運用・森：svc-equipment-exportによるdaily-equipment-prodへの書込みは403で失敗し、ACL-912は処理中、回答予定は未提示です。戻し実演と旧設定の照合も未完了で、次の実演枠は未設定です。運用QAの受入・署名は済んでいません。

運用責任者への申請には、以上の残件の完了が必要です。当日中に解決しない場合は翌朝の従来の手作業出力を使う判断となり、その連絡先は操作メモ末尾にあります。

### Suggestions (not executed)

1. 観測：成功72件と承認はr17に属し、現行はr18です。影響：旧候補の実績でリリース可能と誤判定します。次の確認：既存作業の結果が揃った時点で、候補番号・commit・設定ソースをレビューおよび試験ログと照合する。
2. 観測：空工場、サービスアカウント書込み、大容量計測、戻し実演、運用QA署名が未完了です。影響：境界修正や権限付与だけでは受入条件が揃いません。次の確認：既存の受入チェック欄を、それぞれの実出力・測定・実演記録と突き合わせる。
3. 観測：22時は仮枠で、権限回答と実演の予定が定まっていません。影響：当日実施の可否を確定できません。次の確認：担当交代時に残件の状況、仮枠・申請の状態、操作メモ末尾の手作業出力連絡先を確認する。

### Probes

指定された `/workspace/scratch/a2908bf3dc79/skill-effect-20261117/packets/p03/PROMPT.md` を読み取り、記録L01–L48と添付SKILL.mdを取得しました。他ファイル・Web・実環境への追加照会、再試験は実施していません。

### Extended work-state check

`references/work-state-check.md` は提示されたファイルに含まれていないため、拡張チェックは省略しました。
