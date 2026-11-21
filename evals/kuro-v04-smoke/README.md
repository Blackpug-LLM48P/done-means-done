# 黒パグ版の開発用スモーク

2026年11月21日。通常の引継ぎ2件と、明示的に依頼された詳細監査1件で、実際に受け手へ渡す文章を確認した。

## 通常の引継ぎ

[A](case-a.md) は保存エラーが解消したPDFと、指定先から移動したCSVについて窓口へ渡す文面。[B](case-b.md) は4拠点のうち、直接確認できた2拠点、担当者から報告が届いた1拠点、抜粋に個別記録がない1拠点を含む。各ケース5観点の[採点票](rubric.json)を出力前に固定した。

| 条件 | Aの判定 | Bの判定 | Aの全文字数 | Bの全文字数 |
|---|---:|---:|---:|---:|
| [一行指示](runs/one-line/) | 5/5 | 5/5 | 325 | 316 |
| [v0.3.1 修理候補](runs/previous/) | 5/5 | 5/5 | 1,482 | 1,512 |
| [v0.4 初稿](runs/candidate-first/) | 5/5 | 5/5 | 281 | 308 |
| [v0.4 最終候補](runs/candidate-final/) | 5/5 | 5/5 | 251 | 266 |

A・Bは各条件につき同じ新規セッション内で1回ずつ実行した。各条件に同じ依頼・記録を渡し、一行条件は `Do not claim completion without evidence from the record.` を加えた。旧版・候補版には対応する `SKILL.md` を渡した。作業者への入力は指定ファイルに限定したが、作業場所は共有されている。初回3条件は回答を固定して匿名のファイル名で別担当が採点した。台帳の有無から条件を推測できる。最終候補は追加修正後に別セッションで再実行し、同じ採点票を使った。[初回の採点と出典](handoff-scores.json)・[最終候補の採点](final-grade.json)

文字数にはMarkdown表、見出し、台帳を含む。UTF-8で読んだ全文の末尾の改行を除き、Unicodeコードポイントを数えた。この2例で差が出たのは受け手に渡す文章の長さ。新規の品質優位、料金、遅延は測定していない。

## 詳細監査

[C](case-c.md) は英語の設営案内、会場図PNG、表示試験を依頼した記録。保存された案内はプレースホルダーだけで、表示試験は実行0件。会場図は作業記録と下書きの両方から抜けている。

[初稿の出力](runs/candidate-first/c.md) は3点を拾い、引用6件は実在したが、訂正文にも新たな作業指示を入れた。訂正文に移すのは現在の状態、任意の次の確認は提案欄という規定を戻した。[最終候補の出力](runs/candidate-final/c.md) は同じ3点を訂正文で伝え、任意の確認を提案欄に置いた。固定ヘッダーと4見出しを保ち、利用者の指定に合わせて訂正文を最後に置いている。指定ブロックに6/6引用が一致した。

引用照合はリポジトリ直下から追試できる。

```sh
python3 skills/report-reality-check/scripts/verify_quotes.py --draft S06 \
  evals/kuro-v04-smoke/runs/candidate-final/c.md evals/kuro-v04-smoke/case-c.md
```

比較した旧版は [PR #3 の固定版](https://github.com/Blackpug-LLM48P/done-means-done/blob/2fe38b0e0d94c3dc89adabc9146b145953fb467b/skills/report-reality-check/SKILL.md)。[v0.4初稿の本文](https://github.com/Blackpug-LLM48P/done-means-done/blob/a8e8dc79515d5ad8f58e64e38082ece84eaa13e8/skills/report-reality-check/SKILL.md)のSHA-256は `1bcc2d47c1d9ae3740fe22df9709b2b24acf0cd1c5b0f2b3dd120324f11b2ed8`、最終候補は `1b9698270e78c366d9a8c6de587c3b91da1b863a22c840186cad9c57518933c6`。

評価例の設計では、対象の一部しか読めない場合の報告、ファイルが存在しても要求内容を満たさない場合、テストランナーの実行件数を参照した。入力と採点票は今回作成した。[OpenSpec](https://github.com/Fission-AI/OpenSpec/blob/0c737dc1b543249b38b0f4716816fcf493d894dd/src/core/templates/workflows/verify-change.ts#L68-L79)・[Anthropic skill-creator](https://github.com/anthropics/skills/blob/e4bb5d960d87126ff3b3a8af1a104b7db67560ba/skills/skill-creator/agents/grader.md#L27-L41)・[SWE-bench](https://github.com/SWE-bench/SWE-bench/blob/02e7a74ffd0b707aab73d203fe87bdc7c76afc8e/swebench/harness/grading.py#L25-L51)

## 引用検査器の回帰

単体88件が通過し、既存のCLI 28ケースは期待した終了コードと一致した。v0.3.1比較の固定出力8本を再生すると、旧検査器は7/8本・421/423引用、新検査器は8/8本・423/423引用が指定ブロックに一致した。旧版の生結果は [評価ブランチ](https://github.com/Blackpug-LLM48P/done-means-done/blob/aa05400eb20258a03e9ff655d59dfb1fbf1edcfe/evals/forward-v031-20261117/CHECKER_NOTE.md) にある。途中の修正では `source v3` を無視して他ブロックの文字列が通る場合があり、明示した出典・実在ID・別の版番号・日本語と英語の版名を含む対照を追加した。
