"""Verify the incomplete first wave without substituting a CLI rollout for a transport receipt."""
import uuid

from live import STUDY, apply, digest, encode, jobs_for, read, require


def main():
    folder = STUDY / "results/interrupted-wave/review"
    jobs, contexts = jobs_for("review")
    require((folder / "dispatch.json").read_bytes() == encode(jobs), "dispatch differs")
    jobs = {job["unit_id"]: job for job in jobs}
    checkpoint = read(STUDY / "results/interruption.json")["rows"]
    require(len(checkpoint) == len({r["unit_id"] for r in checkpoint}) == 6, "incomplete claim bindings")
    claims = {p.stem: read(p) for p in (folder / "started").glob("*.json")}
    require(claims.keys() == {r["unit_id"] for r in checkpoint}, "claim coverage")
    require(len({r["session_id"] for r in checkpoint}) == len({c["attempt_id"] for c in claims.values()}) == 6,
            "repeated attempt or session")
    for row in checkpoint:
        uid = row["unit_id"]
        job, claim = jobs[uid], claims[uid]
        require(all(claim[k] == v for k, v in job.items()), "claim input differs")
        require(all(row[k] == claim[k] for k in ("attempt_id","packet_sha256","prompt_sha256")), "rollout binding")
        require(str(uuid.UUID(row["session_id"])) == row["session_id"] and
                row["model_settings"] == {"model":"gpt-6.2-astra","effort":"ultra"}, "session")
        if row["task_complete"]:
            raw = row["final_answer"]
            require(digest(raw.encode()) == row["raw_sha256"] and apply(job, contexts[uid], raw) == row["trace"],
                    "supplementary raw replay failed")
        else:
            require(row["final_answer"] is None and "trace" not in row, "unconfirmed reply in checkpoint")
    require(sum(r["task_complete"] for r in checkpoint) == 5, "rollout completion count")
    print("6 first-wave claims, 5 supplementary outputs tied to frozen prompts; no inferred transport status.")


if __name__ == "__main__":
    main()
