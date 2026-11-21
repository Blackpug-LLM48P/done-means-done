"""Independent authored development examples. No evaluation input is required."""
from scope_matcher import actions, evaluate, features, revisions


def selected(case, arm, policy, qi=0):
    return evaluate([case])["cases"][0]["queries"][qi]["arms"][arm][policy]["row_id"]


def main():
    assert features("ＭＥＮＵ-窓口") == ["menu", "窓口"]
    assert revisions("見本_rev12.pdf、Ｒ１２") == ["r12"]
    assert revisions("第3版と Ver.3") == ["v3"]
    assert revisions("srv19") == []
    assert "proof" not in actions("r12 再校正は未実施")
    assert "test_run" not in actions("r12 pytest --collect-only を実行した")
    assert "test_discovery" in actions("r12 pytest --collect-only を実行した")
    assert "test_run" in actions("r12 pytest 3 passed")
    assert "test_run" not in actions("r12 pytest 0 passed")
    assert "receive" not in actions("r12 の資料を受信者へ送信した")
    assert set(actions("開いた。全ページ校正は未実施。")) == {"open"}
    assert set(actions("r12 全面を目視照合した")["proof"][0]) == {"all_pages", "human"}
    assert "all_pages" not in actions("r12 表紙だけを目視照合した")["proof"][0]
    assert actions("r12 見本を保存していない") == {}
    q = {"id": "d", "question": "星雲 r12 の星表ですか", "claim": "r12の星表を保存した"}
    case = {"case_id": "dev", "queries": [q], "rows": [
        {"id": "story", "text": q["question"] + q["claim"], "source": "reported"},
        {"id": "other", "text": "r13の星表を保存した", "source": "direct"},
        {"id": "right", "text": "r12 星表を格納した", "source": "direct"}]}
    assert selected(case, "source_revision_action", "veto") is None
    assert selected(case, "source_revision_action", "rescue") == "right"
    for rows, claim, expected in [
        ([("r2 見本を保存した", "direct")], "r3 見本を保存した", None),
        ([("r3 見本を送信した", "direct")], "r3 見本を受領した", None),
        ([("r3 見本を受領した", "hearsay")], "r3 見本を受領した", None),
        ([("r3 見本を受領した", "inference")], "r3 見本を受領した", None),
        ([("r3 見本を受領した", "direct")], "r3 見本を受領した", "0"),
        ([("r3 見本を開いた", "direct")], "r3 見本の文字が読めた", None),
        ([("r2 とr3を校正した", "direct")], "r3 見本を校正した", None),
        ([("見本を校正した", "direct")], "r3 見本を校正した", None),
        ([("r3 表紙のみ目視照合した", "direct")], "r3 全頁を目視照合した", None),
        ([("r3 全頁を照合した", "direct")], "r3 全頁を目視照合した", None),
        ([("r3 全頁を目視照合した", "direct")], "r3 全頁を目視照合した", "0"),
        ([("r3 全頁を目視照合した", "direct")], "r3 見本を配送手配した", None),
        ([("r3 テストを列挙した", "direct")], "r3 テストを実行した", None),
        ([("r3 テストを列挙した", "direct")], "r3 テストを列挙した", "0"),
        ([], "r3 見本を受領した", None),
    ]:
        dev = {"case_id": "single", "queries": [{"id": "q", "question": "", "claim": claim}],
               "rows": [{"id": str(i), "text": t, "source": s} for i, (t, s) in enumerate(rows)]}
        for policy in ("veto", "rescue"):
            assert selected(dev, "source_revision_action", policy) == expected, (rows, claim)
    ablation = {"case_id": "axes", "queries": [{"id": "q", "question": "", "claim": "r8を送信した"}],
                "rows": [{"id": "x", "source": "direct", "text": "r6を送信した"}]}
    assert selected(ablation, "source_action", "rescue") == "x"
    assert selected(ablation, "source_revision", "rescue") is None
    ablation["rows"][0]["text"] = "r8を保存した"
    assert selected(ablation, "source_action", "rescue") is None
    assert selected(ablation, "source_revision", "rescue") == "x"
    result = evaluate([case])["cases"][0]["queries"][0]["arms"]
    lexical_order = [[(s["row_id"], s["bm25"]) for s in mode["scores"]]
                     for policies in result.values() for mode in policies.values()]
    assert all(order == lexical_order[0] for order in lexical_order)
    print("All development checks passed.")


if __name__ == "__main__":
    main()
