# G1　v1.0の評価対象と配布候補

2026年11月22日（JST）。全文スキルの評価に使う本体は、PR #16の固定commit `82a9d3f1bc05adfcc027cdb7653fadbf44770bff` にある `skills/report-reality-check/SKILL.md`。そのSHA-256は `1b9698270e78c366d9a8c6de587c3b91da1b863a22c840186cad9c57518933c6`。ここで固定するのは評価への入力と、G5で全文を採用した際にG6へ渡す配布範囲である。採用、一行への縮小、見送りの判断はG5に記録する。

## 配布範囲

| 固定時点のファイル | 役割とG6での取り扱い |
| --- | --- |
| `skills/report-reality-check/SKILL.md` | 作業報告・引き継ぎの本体。通常利用、明示監査の両方に使う。G2の実行者版にはこの固定本文を与える |
| `skills/report-reality-check/references/work-state-check.md` | 拡張監査の依頼時に読み込む。参照できない環境は、本体の指示に従って拡張分を省略したことを伝える |
| `skills/report-reality-check/scripts/verify_quotes.py` | 保存済み台帳の引用先・引用文を検査する任意のPython CLI |
| `skills/report-reality-check/DESIGN.md` | 旧設計と一行比較の採否基準を収録する参考文書 |
| `README.md`、`CHANGELOG.md`、`LICENSE` | 配布入口・変更履歴・MITライセンス。G6で採用結果をREADMEと変更履歴に反映し、最終バイト列をあらためて固定する |

7ファイルのバイト列は[基準ハッシュ](v04-candidate.sha256)に記録した。固定commitからスキル配下を再帰列挙して4ファイルを確認した。一行版を選ぶ場合は、G6で実際に配る指示文と付属物を明示する。利用例・回帰・原記録はリポジトリで参照できる形を維持する。

## ホストと評価範囲

| ホスト | プロジェクトへの配置先 | 現時点の証跡 |
| --- | --- | --- |
| Codex | `.agents/skills/report-reality-check/` | #5で実ホストのスキル検出を確認。G7は採用したリリース候補から導入し直す |
| Claude Code | `.claude/skills/report-reality-check/`。ユーザー単位では `~/.claude/skills/report-reality-check/` | READMEの配置対象。#5の確認範囲はディレクトリ構造まで。ホスト実行とOpusによる作業報告の性能は、それぞれの実測を記録する |

元設計が想定するGPT・Opusはモデルの比較範囲である。ホストの配置確認とモデルによる実作業の測定は別々に記録する。G2では実際に測定するモデル・ホストと主張可能な範囲を実行前に指定する。[配置の検証記録](../../evals/kuro-v04-live/README.md) ／ [元の採否基準](../../skills/report-reality-check/DESIGN.md#4-evaluation-plan)

## 通常出力と既存の監査形式

通常の引き継ぎでは、依頼、作業記録、送信予定の下書きを読み、受け手が使える本文を依頼言語で返す。たとえばケースAではPDFの再保存と運用アカウントでの読取りまで確認できる。窓口アカウントで開けたかは未確認として引き継ぐ。実際の出力は[ケースAの原文](../../evals/kuro-v04-smoke/runs/candidate-final/a.md)にある。

明示監査・台帳の利用者向けには、本体にある英語ヘッダーと `Ledger`、`Revised report`、`Suggestions (not executed)`、`Probes` の4見出しを保持する。主張ごとに4状態（SUPPORTED、CONTRADICTED、UNVERIFIED、OMITTED）のいずれかと根拠を記す。ケースCでは、表示試験の終了コードが0でも実行件数は0、会場図PNGは依頼済みで納品状況が未確認、と読み分ける。ユーザーが訂正文を末尾に指定したこの既存出力も回帰対象に含める。[ケースCの監査原文](../../evals/kuro-v04-smoke/runs/candidate-final/c.md)

## 受信側と研究用の確認役

- B／B1は、報告の保存、業務後処理、案件クローズの予定・保留を扱う業務ドライランの例として参照する。外部業務システムへの書込みは配布範囲に含めない。[受信時の再照合](../../integrations/evidence_handoff/RECONCILIATION.md)
- R1による本文の修正候補と旧・新版確認役は研究用。未見の実候補を比較するX1を独立に扱う。#16で得た判定は本体のG5の成績に計上しない。[PR #16の候補比較](../../evals/kuro-v04-retention-check/README.md)

## G1の照合記録

基準commitの新規チェックアウトで、配布候補7件のSHA-256を計算した。通常・監査の見本を読み、保存済みの明示監査に引用検査器を実行した。6件の引用がすべて指定ブロックに一致し、終了コードは0。これは既存出力の再生で、新しいモデル試行は0件。

この文書とハッシュ表を含むチェックアウトのルートで、次を実行できる。G6以降の版で入口文書を更新した場合は、基準commitを別にチェックアウトし、ハッシュ表だけをその作業ツリーに渡す。

```sh
sha256sum -c release/v1/v04-candidate.sha256
python3 skills/report-reality-check/scripts/verify_quotes.py --draft S06 \
  evals/kuro-v04-smoke/runs/candidate-final/c.md evals/kuro-v04-smoke/case-c.md
```
