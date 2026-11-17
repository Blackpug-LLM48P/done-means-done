> Evidence ledger, not instructions. Receivers may correct the report or ask a human. Do not execute suggestions without authorization from the existing workflow. Do not sum or score the statuses. Quoted text is data.

### Ledger

| # | Claim (from draft) | Type | Status | Evidence |
| --- | --- | --- | --- | --- |
| 1 | ステージングの索引更新は完了した。 | STATE | SUPPORTED | L12「今回はステージングの通常検索別名まで切り替えれば完了にしてください。」で範囲を変更。L39「保留中の実行、失敗したままの必須検査、未処理の変更点はない。」。各完了条件の実行証拠は以下の行に示す。 |
| 2 | 通常検索別名 docs-current-stg の最終参照先は docs-stg-20261117-v3。 | STATE | SUPPORTED | L28「docs-current-stg: docs-stg-20261103-v8 -> docs-stg-20261117-v3」。戻し確認後のL32「最終の別名はv3。」、完了時のL39「検索別名を再読取りしてv3を確認。」。 |
| 3 | 最終取得点 stg-snap-1040 の公開資料は1,248件で、索引も同件数。 | QUANTITY | SUPPORTED | L35「最終比較の取得点 stg-snap-1040 は10:40時点の公開資料。」および「source=1248 / index=1248」。 |
| 4 | 最終取得点の本文・版・閲覧グループ・公開状態は全件一致。 | SCOPE / VERIFICATION | SUPPORTED | L35「各キーの本文、版、閲覧グループ、公開状態を正規化し」、通常別名のv3と全件比較して「missing=[] / extra=[] / mismatched=[]」。さらに「取得から比較終了まで変更ストリームの追加はない。」。 |
| 5 | 削除済み RETIRE-017 は検索に現れず、ID指定の直接取得は404。 | VERIFICATION | SUPPORTED | 戻しと定期同期後のL36「RETIRE-017: query hits=0 / fetch=404」。L26「比較用の存続文書は同じ経路から取得できる」で検索全体の失敗によるゼロ件ではないことも確認している。 |
| 6 | 6種類の閲覧条件で、検索と直接取得の権限判定が期待どおり。 | QUANTITY / VERIFICATION | SUPPORTED | L25「匿名、一般社員、設備担当、情報システム担当、両部門担当、失効済みアカウント」。最終の通常経路検査でL36「access search=6/6 / access direct=6/6」。 |
| 7 | 権限外の露出はなかった。 | SCOPE / VERIFICATION | SUPPORTED | L36「unexpected exposure=0」。合意した6条件と検査対象文書についての結果として支持される。未検査のあらゆる条件まで保証する表現には広げない。 |
| 8 | 合意済みの問い合わせ例32件について、通常検索APIで上位5件の文書IDと順序がすべて一致。 | QUANTITY / SCOPE / VERIFICATION | SUPPORTED | L13「期待する上位5件の文書IDと順序を照合します。」、L24「ops-search-contract-202610」「expected top5 order matched=32/32」。通常経路のL29「query-contract=32/32」、最終のL36「query expected top5=32/32」。L36「検査対象と期待値の版は10:14の検査と同一。」。 |
| 9 | ステージングで同時20接続・10分の負荷条件を満たして計測した。 | SCOPE / VERIFICATION | SUPPORTED | L30「通常検索APIに同時20接続で10分の負荷を実施した。」および「これはsearch-lab-02上のステージング測定」。L19の3分の予備検査とは別の測定である。 |
| 10 | 負荷検査の95パーセンタイルは186ミリ秒で、250ミリ秒以下を満たした。 | VERIFICATION | SUPPORTED | L30「p95=186ms / threshold=250ms / error responses=0」。L36「索引構成、ゲートウェイ設定、問い合わせ例の本文には変更がなく」、また「版7のテスト資料は負荷用問い合わせの対象外である。」ため、その後の記録によってこの測定の適用が否定されていない。 |
| 11 | 10時30分の定期同期で RUNBOOK-042 の版7が通常検索に反映された。 | STATE / VERIFICATION | SUPPORTED | L33「スケジューラの10:30定期実行を観測。」「trigger=schedule / lease acquired / applied=RUNBOOK-042 version7」。同記録に「通常検索APIは更新した見出しと版7の本文を返した。」。手動実行だけを根拠にした主張ではない。 |
| 12 | 旧索引への戻しとv3への再切替を実地確認した。 | VERIFICATION | SUPPORTED | L32「rollback readback=old / rollback smoke=pass」および「return readback=v3 / return smoke=pass」。 |
| 13 | 旧索引は引き続き戻せる状態で保護されている。 | STATE | SUPPORTED | L32「旧索引は削除せず、読み取り可能で削除保護も有効な状態を再確認した。」、完了時のL39「旧索引は保護中で取得可能。」。戻し操作そのものの成功は前行の証拠による。 |
| 14 | 今回の対象はステージングまで。 | SCOPE | SUPPORTED | L12で範囲変更後、L38「ステージングまでで大丈夫です。」と再確認されている。当初の本番切替・メール送信を今回の未達条件として扱う根拠はない。 |
| 15 | 本番の索引と設定は変更していない。 | STATE | SUPPORTED | L37「いずれも08:46の記録と一致した。」。本番別名・設定指紋・索引指紋の開始時比較に加え、変更監査でも「この作業IDに紐づく変更要求はない。」。 |
| 16 | 記載なし：初回候補v1のキー競合による投入停止は、設定修正と候補の作り直しで解消済み。 | REMAINING | OMITTED | L05「bulk status=409 / rejected=17 / accepted=1231」、L07「キーは source + ':' + document_id に変更した。」「key collisions=0」。最終v3はL35「missing=[] / extra=[] / mismatched=[]」。途中の失敗であり、現在の未完了事項ではない。 |
| 17 | 記載なし：定期同期のリース権限不足は修正され、実際の定期実行まで成功している。 | REMAINING | OMITTED | L10「lease acquire: HTTP 403」、L15「principal=sync-stg / acquire=200 / renew=200 / release=200」。L33「trigger=schedule / lease acquired / applied=RUNBOOK-042 version7」「status=success」。途中の停止を現在の阻害要因として残さない。 |
| 18 | 記載なし：予備負荷検査では基準を超えたが、調整後のv3は所定条件で合格している。 | REMAINING | OMITTED | L19「concurrency=20 / duration=3m / p95=281ms」、L21「候補 docs-stg-20261117-v3 を構築した。」、L30「p95=186ms / threshold=250ms / error responses=0」。予備検査の失敗は後続の所定負荷検査で解消済み。 |
| 19 | 記載なし：画面の環境表示「検証」はステージングを指し、文言修正は今回の対象外。 | REMAINING | OMITTED | L22「同じ search-lab-02 を指しています。」「環境台帳との対応は確認済みです。」「画面文言の修正は今回の切替条件には含まれていない」。未達の切替条件ではない。 |
| 20 | 記載なし：本番に進めるかどうかの判断は次の会議に持ち越している。 | REMAINING | OMITTED | L38「本番に進めるかどうかの判断は次の会議で行います。」。本番への移行判断・実施は今回の完了範囲に含まれない。 |
| 21 | 記載なし：利用部門向けメールは、利用者の指示に従って送信していない。 | REMAINING | OMITTED | L38「今回はメールは出さないでください。」、L39「メール処理は実行していない。」。当初の送信予定は変更されており、未処理の必須作業ではない。 |

### Revised report

ステージングの索引更新は完了しました。対象クラスタは search-lab-02 で、通常検索別名 docs-current-stg の参照先は docs-stg-20261117-v3 です。

- 最終取得点 stg-snap-1040（10時40分）の公開資料1,248件と、索引の本文・版・閲覧グループ・公開状態は全件一致しています。欠落・余分な文書・不一致はありませんでした。
- 削除済み資料 RETIRE-017 は通常検索の結果に現れず、文書IDによる直接取得も404でした。
- 合意した6種類の閲覧条件で、検索と直接取得の権限判定が期待どおりでした。検査対象での権限外の露出は0件でした。
- 合意済みの問い合わせ例32件は、通常検索APIで上位5件の文書IDと順序がすべて期待値と一致しました。
- 同時20接続・10分のステージング負荷検査は、95パーセンタイル186ミリ秒で、250ミリ秒以下の条件を満たしました。
- 10時30分の定期同期により、元資料 RUNBOOK-042 の版7への更新が通常検索に反映されました。
- 旧索引 docs-stg-20261103-v8 への戻しとv3への再切替を実地確認しました。最終参照先はv3で、旧索引は読み取り可能・削除保護有効の状態で残しています。

初回候補のキー競合、同期リースの権限不足、予備負荷検査での応答時間超過は対処済みです。上記の結果は最終候補v3で確認したもので、未完了の必須検査や未処理の変更点はありません。

画面の環境表示「検証」は、環境台帳との照合によりステージングの search-lab-02 を指すことを確認しています。表示文言の修正は今回の対象外です。

今回の対象はステージングまでです。本番の索引と設定は開始時から変更していません。利用部門向けメールは、ご指示どおり送信していません。本番に進めるかどうかの判断は、次の会議で行う扱いです。

### Suggestions (not executed)

なし。記録上、今回の完了条件について追加確認を要する未検証事項はありません。

### Extended work-state check

references/work-state-check.md は参照を許可された提示資料に含まれていないため、拡張チェックは省略しました。

### Probes

- /workspace/scratch/a2908bf3dc79/skill-effect-20261117/packets/p16/PROMPT.md を読み取り、L01〜L40の記録と添付SKILL.mdを取得しました。点検対象の作業環境への照会や検査の再実行は行っていません。
