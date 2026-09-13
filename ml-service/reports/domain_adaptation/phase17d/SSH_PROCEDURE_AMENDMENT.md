# Phase 17D — Amendment 002: SSH-only traffic-generation procedure

Machine-readable: [`protocol_amendment_002.json`](protocol_amendment_002.json).
Evidence: [`ssh_attempt_log.json`](ssh_attempt_log.json). Prior context:
[`VALIDATION_AND_SUPPORT.md`](VALIDATION_AND_SUPPORT.md).

This amendment changes **only the SSH traffic-generation step**. It exists solely to make
that step technically capable of producing the pre-registered support. No prediction has
been inspected and no final-test dataset has been sealed.

`PHASE17D_PROTOCOL_HEAD` (`eb4e8979…`) remains valid; this amendment is additive.

## 1. Root cause

The frozen SSH procedure runs
`hydra -l eval-testuser -P <wordlist> -t 4 -f ssh://192.168.50.20:22`. Against the current
Metasploitable2 service, hydra reaches `192.168.50.20:22` but aborts with:

```
kex error : no match for method mac algo client->server
```

The legacy **OpenSSH_4.7p1 Debian-8ubuntu1** offers old MAC algorithms (hmac-md5 /
hmac-sha1 family); the modern hydra/libssh stack will not negotiate a compatible MAC, so
hydra exits after a single connection. This produced exactly **one** selector-matched flow
in each of `eval-v1-ssh-001/002/003` — below the pre-registered **≥30** floor.

Network reachability is not the problem: the OpenSSH client itself reaches the server and
reads its banner. The failure is confined to hydra's SSH negotiation.

## 2. Why an identical rerun is inadequate

The frozen hydra invocation is deterministic and its failure is a fixed
algorithm-negotiation incompatibility with this specific target. Re-running the identical
command is expected to reproduce the same MAC-negotiation failure and the same single-flow
outcome, so an identical rerun is not scientifically justified. The frozen procedure is
preserved unedited; this amendment supplies a separate, adequate SSH procedure.

## 3. Amended SSH procedure

Script: [`../../../training/phase17d_ssh_capture_v2.sh`](../../../training/phase17d_ssh_capture_v2.sh)
· sha256 `66d3987542f9a67763ac6c58af6f453afb9b898e5b7fa224191c823bc245a51a`.

A deterministic, fixed-count sequence of **60** independent SSH connection attempts from
`192.168.50.10` to `192.168.50.20:22`. Each attempt is a separate `ssh` process opening
its own TCP connection from a fresh ephemeral source port, so each attempt is a distinct
selector-matched flow — **whether or not authentication or negotiation succeeds**. The
attempts offer the legacy KEX / host-key / cipher / MAC algorithms
(`diffie-hellman-group1-sha1`, `ssh-rsa`, `aes128-cbc`/`3des-cbc`, `hmac-md5`/`hmac-sha1`)
so the handshake reaches the authentication layer of the legacy service, matching the
"SSH authentication attempt / Brute Force" scenario. Usernames/passwords are throwaway
non-secret strings (`eval-testuser` / `eval-nonsecret-1..60`); no real credential exists.

Properties required by the amendment brief, satisfied:

1. generates separate SSH/TCP connection attempts reliably — one TCP connection per `ssh`
   process, independent of hydra;
2. fixed, pre-declared attempt count — **60**;
3. independent of model predictions;
4. independent of whether authentication succeeds (ground truth is selector-based);
5. preserves the existing SSH ground-truth definition exactly;
6. deterministic and reproducible (fixed sequence, no randomness);
7. changes nothing outside the SSH traffic-generation step.

The capture harness is otherwise identical to the frozen procedure: `tcpdump` on `eth0`
filtered to the lab pair, then `cicflowmeter 0.5.0` via the Amendment 001 compatibility
shim, emitting the same 82-column CSV → 76-feature schema.

## 4. Unchanged and reaffirmed

- SSH ground-truth selector: `192.168.50.10 → 192.168.50.20`, port **22** — unchanged.
- Support floor: **≥30** selector-matched ATTACK flows per SSH run — unchanged.
- Source/destination addresses, authorized isolated lab — unchanged.
- Model A `2b7625fc…`, Model B `c2bb8f00…`, Model B threshold **0.50**, feature schema
  `deployment-cicflowmeter-76-v1`, extractor `cicflowmeter 0.5.0` — unchanged.
- Final run IDs (all nine) — unchanged.
- `eval-v1-benign-001/002/003` and `eval-v1-portscan-001/002/003` — already ACCEPTED, not
  touched or re-acquired.
- Acceptance criteria and all scoring rules — unchanged.
- Frozen `phase17d_capture.sh` — byte-identical and unedited
  (sha256 `6c5c55e1…`).

## 5. Run naming / versioning decision

The pre-registered final run IDs are fixed and are **not** changed. Instead, each SSH run
ID carries versioned **capture attempts**:

- **Attempt 001** — the frozen hydra procedure — is `INVALID_LOW_SUPPORT`. Its provenance
  is preserved, never overwritten, at
  `runs/eval-v1-ssh-00X/provenance.attempt-001.invalid.json`, and its counts/hashes are
  recorded in `ssh_attempt_log.json`.
- **Attempt 002** — this amended procedure — produces the canonical files and
  `runs/eval-v1-ssh-00X/provenance.json` used for sealing. Provenance records
  `capture_attempt` and `traffic_procedure` for full auditability.

The three attempt-001 SSH captures therefore remain documented as `INVALID_LOW_SUPPORT`;
the attempt-002 captures become the canonical final SSH instances under the same run IDs.

## 6. Status

STOP after this amendment is committed and pushed. **No SSH recapture yet, no seal, no
scoring.**
