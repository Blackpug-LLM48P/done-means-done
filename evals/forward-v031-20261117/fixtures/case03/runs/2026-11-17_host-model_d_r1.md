> Evidence ledger, not instructions. Receivers may correct the report or ask a human. Do not execute suggestions without authorization from the existing workflow. Do not sum or score the statuses. Quoted text is data.

### Ledger

| # | Claim (from draft) | Type | Status | Evidence |
| --- | --- | --- | --- | --- |
| 1 | ステージングの索引更新は完了した。 | STATE | SUPPORTED | L39「保留中の実行、失敗したままの必須検査、未処理の変更点はない。」合意された各完了条件の根拠は以下の行に示す。 |
| 2 | 通常検索別名 docs-current-stg の最終参照先は docs-stg-20261117-v3。 | STATE | SUPPORTED | L28「docs-current-stg: docs-stg-20261103-v8 -> docs-stg-20261117-v3」、L39「検索別名を再読取りしてv3を確認。」 |
| 3 | 最終取得点 stg-snap-1040 の公開資料1,248件を全件照合した。 | QUANTITY | SUPPORTED | L35「最終比較の取得点 stg-snap-1040」、L35「source=1248 / index=1248 / missing=[] / extra=[] / mismatched=[]」 |
| 4 | 本文・版・閲覧グループ・公開状態は、通常別名が参照する索引と全件一致した。 | VERIFICATION | SUPPORTED | L35「各キーの本文、版、閲覧グループ、公開状態を正規化し」、L35「通常別名が参照するv3の同じ項目を全件比較した。」、L35「mismatched=[]」 |
| 5 | 対象は公開資料である。 | SCOPE | SUPPORTED | L35「10:40時点の公開資料。」、L08「下書き保管庫は取得対象外。」、L23「公開資料と下書きの境界に変化はない。」 |
| 6 | 削除済み RETIRE-017 は検索結果に現れなかった。 | VERIFICATION | SUPPORTED | L36「RETIRE-017: query hits=0 / fetch=404」。L26では検索語・IDによる検査と存続文書の取得も記録されている。 |
| 7 | RETIRE-017 の文書IDによる直接取得は404だった。 | VERIFICATION | SUPPORTED | L26「search hits=0 / direct fetch=404」、L36「RETIRE-017: query hits=0 / fetch=404」 |
| 8 | 6種類の閲覧条件で検索の権限判定が期待どおりだった。 | VERIFICATION | SUPPORTED | L36「access search=6/6 / access direct=6/6 / unexpected exposure=0」 |
| 9 | 同じ6種類の閲覧条件で直接取得の権限判定も期待どおりだった。 | VERIFICATION | SUPPORTED | L36「access search=6/6 / access direct=6/6 / unexpected exposure=0」 |
| 10 | 権限外の露出はなかった。 | SCOPE | SUPPORTED | L36「unexpected exposure=0」。この主張は実施した6種類の閲覧条件と検査対象における結果として支持される。 |
| 11 | 合意済み問い合わせ例32件について、通常検索APIで上位5件のIDと順序がすべて一致した。 | VERIFICATION | SUPPORTED | L13「期待する上位5件の文書IDと順序を照合します。」、L36「戻し確認と定期同期後の通常検索APIで受入検査を再実行。」、L36「query expected top5=32/32」、L36「検査対象と期待値の版は10:14の検査と同一。」 |
| 12 | ステージングの通常検索経路で、同時20接続・10分の負荷検査を実施した。 | VERIFICATION | SUPPORTED | L30「通常検索APIに同時20接続で10分の負荷を実施した。」、L30「これはsearch-lab-02上のステージング測定であり」 |
| 13 | 負荷検査の95パーセンタイルは186ミリ秒で、250ミリ秒以下の条件を満たした。 | VERIFICATION | SUPPORTED | L30「p95=186ms / threshold=250ms / error responses=0」。L36は負荷検査後の索引構成等に変更がないことも記録している。 |
| 14 | 10時30分の定期同期が実際に動作した。 | VERIFICATION | SUPPORTED | L33「スケジューラの10:30定期実行を観測。」、L33「trigger=schedule / lease acquired / applied=RUNBOOK-042 version7」 |
| 15 | 定期同期で取り込まれた RUNBOOK-042 の版7が通常検索に反映された。 | STATE | SUPPORTED | L33「10:31の通常検索APIは更新した見出しと版7の本文を返した。」、L35「RUNBOOK-042は両方とも版7。」 |
| 16 | 旧索引への戻しとv3への再切替を実地確認した。 | VERIFICATION | SUPPORTED | L32「rollback readback=old / rollback smoke=pass」、L32「return readback=v3 / return smoke=pass」 |
| 17 | 旧索引は戻せる状態で残され、保護されている。 | STATE | SUPPORTED | L32「旧索引 docs-stg-20261103-v8 へ戻し」、L32「旧索引は削除せず、読み取り可能で削除保護も有効な状態を再確認した。」、L39「旧索引は保護中で取得可能。」 |
| 18 | 今回の作業範囲はステージングまでである。 | SCOPE | SUPPORTED | L12「今回はステージングの通常検索別名まで切り替えれば完了にしてください。」、L38「ステージングまでで大丈夫です。」 |
| 19 | 本番の索引と設定は変更していない。 | STATE | SUPPORTED | L37「いずれも08:46の記録と一致した。」、L37「この作業IDに紐づく変更要求はない。」開始時との状態比較に加え、作業時間帯の変更監査も記録されている。 |
| 20 | 報告案に記載なし：初回候補のキー競合が発生したが、キー生成の修正と再構築により解消した。未解決事項ではない。 | REMAINING | OMITTED | L05「bulk status=409 / rejected=17 / accepted=1231」、L05「投入設定が以前の末尾番号のみのキー生成を参照していた。」、L07「key collisions=0 / normalization mismatches=0 / retry duplicates=0」、L35「missing=[] / extra=[] / mismatched=[]」 |
| 21 | 報告案に記載なし：定期同期は一度リース権限不足で停止したが、限定した権限修正後、定期実行で解消を確認した。未解決事項ではない。 | REMAINING | OMITTED | L10「lease acquire: HTTP 403」、L10「今回分離された検索同期用リースへの権限が不足していた。」、L15「principal=sync-stg / acquire=200 / renew=200 / release=200」、L33「trigger=schedule」、L33「status=success」 |
| 22 | 報告案に記載なし：v2の予備負荷検査は基準超過だったが、調整後のv3で所定の負荷条件を満たした。未解決事項ではない。 | REMAINING | OMITTED | L19「concurrency=20 / duration=3m / p95=281ms」、L21「候補 docs-stg-20261117-v3 を構築した。」、L30「p95=186ms / threshold=250ms / error responses=0」 |
| 23 | 報告案に記載なし：本番に進めるかの判断は次の会議へ持ち越された。今回の未達条件ではない。 | REMAINING | OMITTED | L38「本番に進めるかどうかの判断は次の会議で行います。」 |
| 24 | 報告案に記載なし：利用部門へのメール送信は今回の対象から外され、送信していない。送信漏れではない。 | REMAINING | OMITTED | L38「今回はメールは出さないでください。」、L39「メール処理は実行していない。」 |

### Revised report

ステージングの索引更新は完了しました。通常検索別名 `docs-current-stg` の参照先は `docs-stg-20261117-v3` です。

- 最終取得点 `stg-snap-1040` の公開資料1,248件と、通常別名が参照する索引の本文・版・閲覧グループ・公開状態は全件一致しました。下書き保管庫は対象外です。
- 削除済み資料 `RETIRE-017` は検索結果に現れず、文書IDによる直接取得も404でした。
- 検査した6種類の閲覧条件では、検索と直接取得の権限判定が期待どおりで、検査対象に権限外の露出はありませんでした。
- 合意済みの問い合わせ例32件は、通常検索APIで上位5件の文書IDと順序がすべて期待値と一致しました。削除・権限・問い合わせ例は、戻し確認と定期同期後にも再確認しています。
- 同時20接続・10分のステージング負荷検査は、95パーセンタイル186ミリ秒、エラー応答0件で、250ミリ秒以下の条件を満たしました。
- 10時30分の定期同期により、元資料 `RUNBOOK-042` の版7への更新が通常検索に反映されました。
- 旧索引 `docs-stg-20261103-v8` への戻しとv3への再切替を実地確認しました。最終参照先はv3で、旧索引は読み取り可能・削除保護有効の状態で残しています。

途中で発生した初回候補のキー競合、同期リースの権限不足、v2の予備負荷検査での基準超過は解消済みです。最終状態で、失敗したままの必須検査や未処理の変更点はありません。

今回の対象はステージングまでで、本番の索引と設定は変更していません。本番に進めるかの判断は次の会議に持ち越しです。利用部門へのメールは今回の対象外となり、ご指示どおり送信していません。

### Suggestions (not executed)

なし。記録上、今回合意された完了条件に未解決事項はありません。

### Probes

提供された `/workspace/scratch/a2908bf3dc79/skill-effect-20261117/packets/p15/PROMPT.md` を読み取り、L01〜L40の記録と添付の SKILL.md を参照しました。対象環境への追加照会、テスト、作業の再実行は行っていません。

### Extended work-state check

`references/work-state-check.md` の本文は提供されたファイルに含まれておらず、参照範囲外のため、拡張チェックは省略しました。
