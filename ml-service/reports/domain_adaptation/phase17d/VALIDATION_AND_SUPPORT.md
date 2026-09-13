# Phase 17D — support validation: tooling bug fix and SSH support failure

Status after acquiring all 9 runs and running blinded support validation (Step 2):
**stopped before sealing and before any scoring.** No Model A or Model B prediction on
final-test data has been generated or inspected. Blinding is intact.

Two findings, in order of discovery.

## 1. Bug in the Phase 17D processing tool (fixed)

`build_final_eval_dataset.py` and `evaluate_phase17d.py` compared the **return of**
`schema_guard.status_from_validation(...)` directly against the string
`protocol.STATUS_VALID`. That function returns a **dict**
(`{"validation_status": "VALID", "validation_errors": [...], ...}`), so the comparison was
always false and every flow was mis-counted as invalid (`valid_flows = 0` for all runs).

This is a defect in the Phase 17D **analysis tooling only**. It does not touch the
capture, the flow CSVs, the models, the threshold, the selectors, the ground-truth rule,
the acceptance floors, or the frozen traffic procedure. It was found during support
validation, before any prediction was produced.

Fix — read the status key:

```python
def flow_is_valid(status):
    return status["validation_status"] == protocol.STATUS_VALID
```

applied in `build_final_eval_dataset.py` (support counting) and `evaluate_phase17d.py`
(flow eligibility). Regression tests in `tests/test_phase17d_extractor_compat.py`
(`TestFlowValidityContract`) pin the contract: `status_from_validation` returns a dict
with a `validation_status` key, `flow_is_valid` reads that key, and the raw dict never
equals the status string.

## 2. Corrected blinded support results

Labels and acceptance come only from the frozen manifest selectors and the pre-registered
support floors; no prediction was consulted.

| run | scenario | total | valid | evaluable | ATTACK | BENIGN | UNLABELLED | support | floor | status |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| eval-v1-benign-001 | benign | 320 | 320 | 320 | 0 | 320 | 0 | 320 | 300 | ACCEPTED |
| eval-v1-benign-002 | benign | 320 | 320 | 320 | 0 | 320 | 0 | 320 | 300 | ACCEPTED |
| eval-v1-benign-003 | benign | 320 | 320 | 320 | 0 | 320 | 0 | 320 | 300 | ACCEPTED |
| eval-v1-portscan-001 | portscan | 393213 | 393210 | 393210 | 393210 | 0 | 3 | 393210 | 300 | ACCEPTED |
| eval-v1-portscan-002 | portscan | 393214 | 393210 | 393210 | 393210 | 0 | 4 | 393210 | 300 | ACCEPTED |
| eval-v1-portscan-003 | portscan | 393228 | 393210 | 393210 | 393210 | 0 | 18 | 393210 | 300 | ACCEPTED |
| eval-v1-ssh-001 | ssh | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 30 | **INVALID_LOW_SUPPORT** |
| eval-v1-ssh-002 | ssh | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 30 | **INVALID_LOW_SUPPORT** |
| eval-v1-ssh-003 | ssh | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 30 | **INVALID_LOW_SUPPORT** |

Benign and PortScan pass. **All three SSH runs fail the pre-registered ≥30
selector-matched-attack floor** — each produced exactly one SSH flow.

## 3. SSH shortfall — observation (no procedure change made)

Each SSH capture window was ~7 s and produced a single TCP flow to `192.168.50.20:22`
(one completed handshake with a clean FIN close). The frozen procedure runs
`hydra -l eval-testuser -P <60-entry wordlist> -t 4 -f ssh://192.168.50.20:22`, which
should yield tens of connection attempts; only one connection was captured, so `hydra`
appears to have aborted after its first connection (a plausible cause is the modern Kali
`hydra`/`libssh` failing to negotiate with the legacy Metasploitable2 OpenSSH, but this
was not confirmed in-guest).

Per the frozen protocol, a run that fails a support floor is re-acquired with the **same**
procedure, and the procedure is **not** changed on the basis of model performance. No
predictions have been seen, so blinding is not at risk either way. The decision on how to
obtain adequate SSH support is deferred to the maintainer:

- **A. Re-acquire SSH with the identical frozen procedure.** Protocol-compliant. If the
  single-flow outcome reproduces, the frozen SSH procedure is structurally inadequate
  against this target.
- **B. Pre-registered procedure amendment (SSH generation only).** If A reproduces the
  shortfall, amend *only* the SSH traffic-generation step so it produces ≥30
  selector-matched attack flows, committed and pushed **before** re-capture, justified on
  capture-adequacy grounds (not predictions), leaving selectors, ground truth, models,
  threshold, and acceptance floors unchanged.

## 4. PortScan volume note

Each PortScan run produced ~393,210 selector-matched attack flows (≈43× the adaptation
PortScan runs), because the frozen procedure issues six aggressive full-range scans. The
resulting CSVs are ~156 MB each and are kept local (like the PCAPs); their SHA-256 hashes
are recorded. This is well above the support floor and is not a blocker, but the seal step
will track hashes rather than commit the raw CSV bytes.

## 5. What did NOT happen

- No final-test dataset was sealed.
- No Model A or Model B prediction was generated or inspected.
- No model, threshold, selector, feature schema, acceptance floor, or frozen traffic
  procedure was changed.
- No run was accepted or rejected on the basis of any prediction.
