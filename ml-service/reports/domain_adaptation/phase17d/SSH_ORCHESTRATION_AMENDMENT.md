# Phase 17D — Amendment 003: SSH capture orchestration

Machine-readable: [`protocol_amendment_003.json`](protocol_amendment_003.json). Supersedes
the SSH *procedure* of [Amendment 002](SSH_PROCEDURE_AMENDMENT.md) (which itself replaced
the frozen hydra step). Changes **only the SSH capture orchestration**. No prediction has
been inspected and no final-test dataset has been sealed.

`PHASE17D_PROTOCOL_HEAD` (`eb4e8979…`) remains valid; this amendment is additive.

## 1. What happened

The Amendment 002 script `phase17d_ssh_capture_v2.sh`, run for `eval-v1-ssh-001`, produced
an **empty capture**: a **24-byte** PCAP (the pcap global header only), **0 packets**,
**0 SYN** to dst port 22, and a CSV with no usable rows — yet its metadata still printed
`ssh_attempts=60`. This is a capture / traffic-generation orchestration failure, not flow
aggregation, selector, model, or support-count behaviour.

## 2. Root cause and responsible lines (`phase17d_ssh_capture_v2.sh`)

The SSH traffic step opened **zero** TCP connections; the failure was silenced and the
attempt count was faked.

- **L2** `set -euo pipefail` — neutralised for the ssh step by the trailing `|| true` on L36.
- **L19** `tcpdump … >/dev/null 2>&1 &` — tcpdump's stderr is discarded, hiding any
  startup problem.
- **L22** `sleep 3` — a blind sleep, **not** a readiness check.
- **L25–L36** the `sshpass … ssh …` attempt forces legacy options
  (`HostKeyAlgorithms=+ssh-dss`, `KexAlgorithms=+diffie-hellman-group1-sha1`) that a modern
  OpenSSH client **rejects at config-parse time** (exit 255 **before** any TCP connect);
  the trailing `>/dev/null 2>&1 || true` hides the error and the loop keeps spinning.
  (Missing `sshpass` would produce identical evidence; both are removed by v3.)
- **L52** `echo "ssh_attempts=$ATTEMPTS"` prints the **static constant 60**, never a count
  of connections actually opened.

**Why the PCAP was only 24 bytes:** tcpdump started and wrote the 24-byte pcap global
header, but no packet ever matched `host 192.168.50.20 and port 22` because no connection
to `:22` was opened, so the file never grew past the header.

**Why metadata still claimed 60 attempts:** the count was a hard-coded echo of the
`ATTEMPTS` constant, decoupled from whether any connection succeeded.

The exact trigger (rejected legacy options vs. missing `sshpass`) cannot be disambiguated
without in-guest execution; both give identical evidence. Amendment 003 removes the
dependence on `ssh` and `sshpass` entirely, so the distinction no longer matters.

## 3. Amendment 003 change

Script: [`../../../training/phase17d_ssh_capture_v3.sh`](../../../training/phase17d_ssh_capture_v3.sh)
· sha256 `33de2449bb2be69f480b29b8a6978fd0fb65c163eebba38c124e3d22314e10ac`.

Orchestration fixes (SSH capture only):

1. **Guaranteed connections** — each of the 60 attempts opens a real TCP connection with
   bash `exec 3<>/dev/tcp/192.168.50.20/22`, sends an `SSH-2.0` client banner, reads the
   server banner, then closes. This produces a genuine SSH-service connection/flow to
   `:22` on every attempt, independent of the OpenSSH client, `sshpass`, and algorithm
   negotiation. (Verified on the host against a local SSH-banner listener: 5/5 opened.)
2. **tcpdump readiness check** — tcpdump's stderr goes to a log and the script polls until
   it prints `listening on` (or the process dies); it **aborts with exit 3** if tcpdump
   never becomes ready, instead of a blind sleep.
3. **Honest counting** — per-attempt outcomes are logged; the RESULT reports
   `ssh_connections_opened` (actual) alongside `ssh_attempts_planned`, not a static
   constant.
4. **Non-empty capture verification** — after capture the script requires the PCAP to
   exceed the 24-byte header (**exit 4** otherwise) and the extracted CSV to contain at
   least one data row (**exit 5** otherwise). The success `PHASE17D_CAPTURE_RESULT` block
   is emitted **only** if both pass, so an empty capture can never masquerade as success.
5. tcpdump uses `-U` (packet-buffered writes) and is stopped with `SIGINT` so packets are
   flushed before extraction.

Extraction still uses `cicflowmeter 0.5.0` via the Amendment 001 compatibility shim,
emitting the same 82-column CSV → 76-feature schema.

A parallel guard was added to the processing tool: `build_final_eval_dataset.process()`
records `pcap_bytes` and `capture_nonempty` and marks a run `INVALID_EMPTY_CAPTURE` when
its PCAP is header-only, so the seal step (which requires all runs `ACCEPTED`) can never
seal an empty SSH capture.

## 4. Unchanged and reaffirmed

SSH selector `.10→.20:22`; SSH floor **≥30**; source/destination; Model A `2b7625fc…`;
Model B `c2bb8f00…`; threshold **0.50**; schema `deployment-cicflowmeter-76-v1`; extractor
`cicflowmeter 0.5.0` (+ Amendment 001 shim); all nine run IDs; benign/portscan runs
untouched; acceptance criteria (the non-empty-capture check is an added integrity guard,
not a relaxation) and scoring rules; frozen `phase17d_capture.sh` byte-identical.

## 5. Run versioning

Run IDs unchanged. Attempt 001 (frozen hydra) = `INVALID_LOW_SUPPORT` (preserved).
Attempt 002 (v2 script) = `INVALID_EMPTY_CAPTURE` (preserved, not canonical). Attempt 003
(this v3 procedure) produces the canonical files and `runs/<id>/provenance.json` for
sealing.

## 6. Status

STOP after this amendment is committed and pushed. Run **only** the non-final smoke test
next (§ commands in the final report), and wait for review before any final SSH recapture.
No seal, no scoring.
