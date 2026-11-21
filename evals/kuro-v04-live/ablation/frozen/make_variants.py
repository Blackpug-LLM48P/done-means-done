from pathlib import Path
import shutil, hashlib, difflib, json

root = Path(__file__).resolve().parents[1]
work = root.parents[1] / "ablation-workers"
source = root.parents[1] / "dmd-impl/skills/report-reality-check/SKILL.md"
full = source.read_text()
def variant(*pairs):
    text = full
    for old, new in pairs:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    return text

policies = {
    "w18": ("full", full),
    "w43": ("remove_attribution", variant(
        ("| HEARSAY | Who reported the result and what they actually said |", "| HEARSAY | The claim and its stated scope |"),
        ("An agent's message can support attribution to that agent. A claim of independent confirmation needs a corresponding observation. ", ""),
        ("quantity, destination, attribution or scope", "quantity, destination or scope"),
        (" For example, if the only evidence is a worker's save report, a Japanese handoff can say 「担当は保存済みと報告しています。指定先にあるかは、この記録からは確認できません。」", ""),
    )),
    "w62": ("remove_final_recheck", variant(
        ("Read the actual final wording against the evidence once more. Check facts introduced by the rewrite, including negatives, causes and words such as “all.” Removing an unsupported claim must still leave the recipient able to identify any consequential gap. ", ""),
    )),
    "w95": ("remove_draft_source_exclusion", variant(
        ("The draft identifies the claim under review. Cite the original record for its outcome. ", ""),
        (" To exclude the draft as its own source when records have block IDs, run this read-only check from the skill folder.", " Run this read-only check from the skill folder."),
        ("--draft DRAFT_ID LEDGER.md RECORD_FILE", "LEDGER.md RECORD_FILE"),
        ("Omit `--draft DRAFT_ID` if there is no identified draft block. With no citation ID beside a quote, the tool checks only for its occurrence, subject to the draft exclusion.", "With no citation ID beside a quote, the tool checks only for its occurrence."),
    )),
}
for worker, (name, policy) in policies.items():
    src = root / "prompts" / name
    src.mkdir(exist_ok=True)
    (src / "policy.md").write_text(policy)
    (src / "diff.patch").write_text("".join(difflib.unified_diff(full.splitlines(True), policy.splitlines(True), "full/policy.md", name + "/policy.md")))
    wd = work / worker
    wd.mkdir(parents=True, exist_ok=True)
    (wd / "policy.md").write_text(policy)
    shutil.copyfile(root / "frozen/cases.md", wd / "cases.md")
    path = str(wd)
    (src / "dispatch.txt").write_text("作業フォルダは " + path + " 。\n" + (root / "frozen/receiver.txt").read_text())
manifest = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file() and p.name != "sha256.json"}
(root / "frozen/sha256.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
