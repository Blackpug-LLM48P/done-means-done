# Semantic handoff through Codex app-server

One synthetic North Annex shift record tests whether a model can recover the current plan, source documents, a superseded revision, an outstanding lift permit, and the difference between a routing notice being sent and its receipt being confirmed. The task, source, twelve field values and exact-type scoring rule were fixed before the compression worker received its request.

## Observed on 21 November 2026

| Evidence available to the answering model | Source length | Exact field scores |
| --- | ---: | ---: |
| Original synthetic shift record | 181 words / 1,150 characters | 12/12 |
| Model-authored handoff | 60 words / 361 characters | 12/12 |

Both models recovered revision C, the four-crate Birch Gate pickup at 14:25, the cancelled worksheet, the packing authorization, the pending lift permit, and the distinction between a sent notice and an unconfirmed receipt. The final JSON answers were identical. The host recorded `item/completed` with `kind=contextCompaction` at 01:57:35.342 UTC. Its next provider request arrived at 01:57:35.382 UTC. That request contained the entire handoff exactly once. The full input record and page watermark were absent. None of nine preregistered case fingerprints occurred elsewhere in the captured input message text. The adapter passed exactly the handoff and question to the answering worker.

A fourth fresh model audited both anonymized answers against the original record. It saw the original question, the two returned texts and the source, without the condition labels or scoring key. It classified all twelve fields in each answer as supported. Its twelve exact supporting quotations all match the source. See `source-review/input.json`, `source-review/review.json` and `workers.json` for the review packet, ballot and decoded labels.

The compression worker returned this handoff.

> Follow signed slip MV-493 rev C for the 14:25 pickup of four crates at Birch Gate. It cancels W-12 rev B’s five-crate Alder Door pickup at 13:40. EM-76 authorizes packing. Hold the lift until the site electrician approves permit LP-28. TX-816 records the routing notice as sent to dispatch at 10:04. Follow up with dispatch because receipt is still unconfirmed.

The 13 recorded transport checks passed. Words here are whitespace-delimited, and character counts use Unicode code points. One successful handoff gives no estimate of loss frequency. No model had access to unit-level performance feedback during the run.

## What runs where

A clean Codex app-server process dispatches HTTP Responses requests to a local Python adapter in a private Linux user/network namespace. Its only network interface is loopback. The ephemeral CLI home and whitelisted environment contain no user session or API credentials. The adapter never exports host instructions, account content, tool definitions or the full provider body. It checks the message role and exact text before exporting the experiment-authored task and evidence.

The two seed turns replay the same synthetic case as an assistant entry. The seed user message contains no case facts. This placement allows the experiment to test replacement of assistant history even when the host retains user messages. Each subsequent answer comes from a fresh collaboration worker. The adapter emits that worker's text as a Responses stream only after receiving its reply. The worker sees the task and evidence in a dedicated two-field packet; its only requested file operations are reading its packet and delivering its own reply. The workers share the workspace by platform design. Their task data access is instruction-scoped.

| Provider phase | Input to worker | Host action |
| --- | --- | --- |
| compact | Case record and generic handoff instruction, with an 80-word budget | The coordinator calls `thread/compact/start` and waits for completion |
| after | Handoff copied from the next actual host request, and the audit question | The same host thread receives the new audit turn |
| original | Complete case record and the identical audit question | A separate fresh ephemeral host thread receives the same seed and audit turn |

The compression worker does not receive the subsequent question or answer key. Neither answering worker receives the frozen key or the other worker's answer. A fixed local scorer compares each submitted JSON field against the preregistered reference. Its twelve rows cover one case. The original-record condition controls the effect of replacing the source with this particular handoff. It does not control model variation between participants.

The model inference service is ChatGPT collaboration, reached by the study coordinator outside the host namespace. Codex itself only makes local HTTP requests. The local provider wraps the actual separately authored responses; model identity, native provider token usage, and the vendor's proprietary compactor are outside this measurement. The generic compact prompt and manual compaction trigger are study inputs. The experiment does not evaluate an automatic compression threshold, any workflow-skill effect, or long-horizon natural tasks.

## Replay

From this directory, run `python -B verify.py` for integrity and provenance checks and `python -B score.py` for twelve field-level scores per answering condition. Static replay uses the saved synthetic responses. A new live run needs three fresh model sessions.

To repeat the live protocol on Linux with the Codex CLI available, choose a new exchange directory path that does not exist and an output JSON path. Run `unshare -Urn python -B relay.py EXCHANGE OUT.json`. As each of `compact.request.json`, `after.request.json`, and `original.request.json` appears, give that packet to a new model participant. Deliver its exact response using `python participant.py EXCHANGE PHASE WORKER` with the response on standard input. Each call references the specific request's SHA-256. Preserve the six packets and the host output. Using different model-authored outputs can change the score and transport observations.

The abbreviated host trace in `observation.json` supplies event types, phase boundaries, UTC timestamps and SHA-256 receipts for emitted agent text. The packets preserve the exact text used for inference. The record and scoring code digests in the trace allow verification of the frozen inputs.
