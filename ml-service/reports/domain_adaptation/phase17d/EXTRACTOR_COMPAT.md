# Phase 17D — cicflowmeter 0.5.0 extractor compatibility fix

A runtime bug in `cicflowmeter 0.5.0` was discovered **before any final-test flow was
scored**. No Model A or Model B prediction was inspected; the single failed
`eval-v1-benign-001` attempt was deleted. Per the Phase 17D bug rule, execution stopped,
the bug was documented, and only argument plumbing was changed — never the models,
threshold, selectors, traffic procedure, acceptance criteria, or feature-extraction
semantics.

## 1. Root cause

Authoritative source audited: `cicflowmeter-0.5.0.tar.gz`
sha256 `501d8b78ca6b95a1d1300bf5f9424bbfa1f359d188e0af960920586b4a0d4f0e`
(fetched from PyPI). The installed Kali copy at `/home/kali/.local/bin/cicflowmeter`
matches this source.

In `src/cicflowmeter/sniffer.py`:

- `create_sniffer` is defined (lines **33–35**) as:

  ```python
  def create_sniffer(
      input_file, input_interface, output_mode, output,
      input_directory=None, fields=None, verbose=False
  ):
  ```

- `main()` calls it **positionally** (lines **295–302**):

  ```python
  sniffer, session = create_sniffer(
      args.input_file,
      args.input_interface,
      args.output_mode,
      args.output,
      args.fields,     # lands in input_directory
      args.verbose,    # lands in fields
  )
  ```

The 5th and 6th positionals are misaligned against the signature:

| intended parameter | receives | should receive |
|---|---|---|
| `input_directory` | `args.fields` | (nothing; stays `None`) |
| `fields` | `args.verbose` | `args.fields` |
| `verbose` | default `False` | `args.verbose` |

For the frozen invocation `cicflowmeter -f "$PCAP" -c "$CSV"` (no `--fields`, no `-v`):
`args.fields is None` and `args.verbose is False`, so `create_sniffer` receives
`fields=False`. Then (lines **39–40**):

```python
if fields is not None:
    fields = fields.split(",")
```

`False is not None` is `True`, so `False.split(",")` raises
**`AttributeError: 'bool' object has no attribute 'split'`** — exactly the observed crash.

The `-f` (file) and `-i` (interface) paths in `main()` always crash in 0.5.0 for this
reason. The `-d` (directory) path is unaffected: it calls `create_sniffer` with **keyword
arguments** (lines **183–190**), so its `fields`/`verbose` are routed correctly.

## 2. Classification: upstream bug

This is an **upstream `cicflowmeter 0.5.0` defect**, not a local-package inconsistency:
the misaligned positional call is present in the published PyPI source above, and the
installed Kali copy is byte-consistent with it. The `-d` path proves the intended
mapping (`fields=fields, verbose=verbose`), so `main()`'s positional call is simply wrong.

## 3. Fix — project-controlled compatibility shim (argument plumbing only)

`ml-service/training/phase17d_cicflowmeter_shim.py`
sha256 `ac212bb6a1ec70813ec9b422a664de516dcea117adc5b5364a96c972a5678a70`

The shim is a corrected copy of upstream `main()` that:

- reuses the installed `cicflowmeter.sniffer.create_sniffer`, `process_directory`, and
  `process_directory_merged` **unchanged** (imported at call time);
- parses the identical CLI (`-i/-f/-d`, `-c/-u`, `output`, `--fields`, `--merge`, `-v`);
- calls `create_sniffer` with **keyword arguments**:

  ```python
  create_sniffer(
      input_file=args.input_file,
      input_interface=args.input_interface,
      output_mode=args.output_mode,
      output=args.output,
      fields=args.fields,
      verbose=args.verbose,
  )
  ```

Nothing else changes. The `-d` branches are preserved exactly as upstream (already
correct). The shim is exposed on `PATH` as `cicflowmeter`, so the **frozen, byte-identical
capture script** (`phase17d_capture.sh`, sha256
`6c5c55e1ac74c59924b7ea3ab2f1d7db845e1b3fd420e49afaf139c93fbb3e05`) runs unedited and its
`cicflowmeter -f "$PCAP" -c "$CSV"` call resolves to the corrected driver.

## 4. Feature-extraction semantics unchanged (by construction)

- The shim imports and runs the installed 0.5.0 `create_sniffer` / `FlowSession` /
  feature code with no modification.
- With `--fields` absent, `args.fields is None`, so the shim passes `fields=None`. Then
  `create_sniffer` skips the `.split(",")` branch, `FlowSession(fields=None)` is built,
  and `Flow.get_data(include_fields=None)` returns the **full** column dictionary (the
  field filter in `flow.py` only applies when `include_fields is not None`). This is the
  same full-schema output a fixed upstream would produce.
- Same PCAP input, same csv `output_mode`, same output-file contract, same 82-column CSV
  → same 76-feature deployment schema (`deployment-cicflowmeter-76-v1`) after the six
  identity columns are dropped.

The fix removes a crash on the file path; it does not add, drop, reorder, rescale, or
otherwise transform any feature.

## 5. Verification

- **Root cause** confirmed from the authoritative PyPI 0.5.0 source (above).
- **Regression tests** (`tests/test_phase17d_extractor_compat.py`, deterministic, no real
  provider or network): reproduce the upstream `bool.split` crash and the
  verbose→fields misrouting, and prove the shim passes `fields=None`/`verbose=False`
  (never a bool as `fields`), forwards an explicit `--fields`, and survives the real
  upstream `fields`-handling logic.
- **Real-PCAP extractor smoke test** must be run in Kali (the extractor requires Python
  ≥3.12; the host analysis venv is 3.11, and no cicflowmeter version is installed or
  changed on the host). The exact command is in §7; it verifies CSV creation and the
  expected column schema on a short, non-final temporary capture before any final run.

## 6. Hashes

| artifact | sha256 |
|---|---|
| audited 0.5.0 sdist | `501d8b78ca6b95a1d1300bf5f9424bbfa1f359d188e0af960920586b4a0d4f0e` |
| compatibility shim | `ac212bb6a1ec70813ec9b422a664de516dcea117adc5b5364a96c972a5678a70` |
| frozen capture script (unedited) | `6c5c55e1ac74c59924b7ea3ab2f1d7db845e1b3fd420e49afaf139c93fbb3e05` |

## 7. Kali smoke test + restart (run before final captures)

```bash
mkdir -p ~/phase17d_bin
cp <repo>/ml-service/training/phase17d_cicflowmeter_shim.py ~/phase17d_bin/
printf '#!/usr/bin/env bash\nexec python3 %q "$@"\n' ~/phase17d_bin/phase17d_cicflowmeter_shim.py > ~/phase17d_bin/cicflowmeter
chmod +x ~/phase17d_bin/cicflowmeter
export PATH="$HOME/phase17d_bin:$PATH"
command -v cicflowmeter

sudo timeout 10 tcpdump -i eth0 -w /tmp/smoke.pcap host 192.168.50.20 &
ping -c 3 192.168.50.20 >/dev/null 2>&1 || true
curl -s http://192.168.50.20/ >/dev/null 2>&1 || true
sleep 11
cicflowmeter -f /tmp/smoke.pcap -c /tmp/smoke.csv
head -1 /tmp/smoke.csv | tr ',' '\n' | wc -l
head -1 /tmp/smoke.csv
rm -f /tmp/smoke.pcap /tmp/smoke.csv
```

A column count of **82** and a successful CSV write confirm the extractor is fixed and
schema-faithful. Then run the nine final runs exactly as in the frozen procedure, with
`~/phase17d_bin` still first on `PATH`.
