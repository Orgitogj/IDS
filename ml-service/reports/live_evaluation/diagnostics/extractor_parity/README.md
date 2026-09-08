# Feature-extraction parity audit (Phase 16E)

**Diagnostic only.** No new traffic, no retraining, no tuning, no threshold change, no
SHAP, no LLM, no PostgreSQL, no frozen result modified. Goal: determine whether the large
residual **non-time** feature differences between canonical CICIDS2017 and the laboratory
runs are consistent with an implementation difference between the original Java
CICFlowMeter and Python `cicflowmeter 0.5.0`, and separate — as far as the retained
evidence allows — **feature-extraction implementation shift** from **true traffic/domain
shift**.

## Availability and decision gate — CASE C

| evidence | status |
|---|---|
| accepted-run PCAP (PortScan) | **not retained** |
| accepted-run PCAP (SSH) | **not retained** |
| how the runs were captured | `cicflowmeter -i eth0 -c csv` — live sniff to CSV; **no packets saved** |
| pcaps on the Kali guest | only metasploit-framework sample/test pcaps; none match the accepted runs |
| Java CICFlowMeter | **not available** (no jar/source in repo or host; a JRE exists, but no extractor; installing an external binary was out of scope) |
| Python `cicflowmeter 0.5.0` source | **available and retained** under `cicflowmeter_0_5_0_source/` |

**Same-PCAP empirical parity is impossible with the retained evidence** — the accepted
runs retained flow-CSV evidence but not packet-level evidence sufficient for dual
extraction. Per protocol §13 we therefore perform a **source/semantic implementation
audit only** and do **not** recreate traffic or substitute a different capture.

## Extractor versions

- Python: `cicflowmeter 0.5.0`, source-verified (constants: EXPIRED_UPDATE 240,
  CLUMP_TIMEOUT 1, ACTIVE_TIMEOUT 5, PACKETS_PER_GC 1000).
- Java: original CICFlowMeter used by CICIDS2017 — documented behavior, **not locally
  executable**, so side-A statements are documented-but-not-verified.

## 78-feature semantic parity (`semantic_parity.csv`)

| classification | count |
|---|---:|
| IMPLEMENTATION_DIFFERENCE | 23 |
| UNIT_DIFFERENCE_ONLY | 15 |
| FLAG_DEFINITION_DIFFERENCE | 11 |
| LIKELY_EQUIVALENT | 9 |
| TIMEOUT_DEPENDENT | 8 |
| UNRESOLVED | 8 |
| AGGREGATION_DIFFERENCE | 4 |

Only side B (Python) is source-verified; every classification is stated relative to that
verified behavior, with the Java side marked documented-not-verified.

## Source-verified implementation differences (side B)

1. **Packet-length basis** — `PacketLength.get_packet_length` uses `len(packet)`, the full
   captured frame (Ethernet + IP + TCP + payload on live eth0). This drives every
   packet-length feature: Fwd/Bwd/overall Packet Length Max/Min/Mean/Std/Variance, Total
   Length of Fwd/Bwd Packets, Average Packet Size, Avg Fwd/Bwd Segment Size, Subflow bytes,
   and the Flow Bytes/s numerator. → **IMPLEMENTATION_DIFFERENCE**.
2. **Header-length basis** — `_header_size` returns the IP header only (`ihl × 4`),
   excluding the TCP header. Drives Fwd/Bwd Header Length and Fwd Seg Size Min. →
   **IMPLEMENTATION_DIFFERENCE**.
3. **Subflow copy** — `subflow_*` are copied directly from flow totals; there is no
   subflow segmentation. → **AGGREGATION_DIFFERENCE**.
4. **Flag counting** — `FlagCount.count` counts packets whose scapy flag string contains
   the flag letter, over both directions; canonical flag-count/segmentation semantics
   differ (canonical PSH Flag Count median 1 vs lab 15). → **FLAG_DEFINITION_DIFFERENCE**.
5. **CWR quirk** — `cwr_flag_count` is set to `fwd_urg_flags`, not an actual CWR count. →
   **IMPLEMENTATION_DIFFERENCE**.
6. **Time unit** — durations/IAT from `packet.time` in seconds vs canonical microseconds
   (already confirmed and corrected by `lab-feature-compat-v1`). →
   **UNIT_DIFFERENCE_ONLY**.

## Top implementation-different residual features

All six named residual features are source-classified:

| feature | classification | SSH residual KS (after unit fix) |
|---|---|---:|
| Total Length of Fwd Packets | IMPLEMENTATION_DIFFERENCE (`len(packet)`) | 1.000 |
| Average Packet Size | IMPLEMENTATION_DIFFERENCE (`len(packet)`) | 1.000 |
| Bwd Packet Length Mean | IMPLEMENTATION_DIFFERENCE (`len(packet)`) | 1.000 |
| Max Packet Length | IMPLEMENTATION_DIFFERENCE (`len(packet)`) | 1.000 |
| Bwd Packet Length Std | IMPLEMENTATION_DIFFERENCE (`len(packet)`) | 0.998 |
| PSH Flag Count | FLAG_DEFINITION_DIFFERENCE | 1.000 |

## Top-15 model-important parity (`model_relevant_parity.csv`)

**11 of the top 15** model-important features carry an implementation-class difference. The
most-important feature (Idle Mean, imp 0.239) is TIMEOUT_DEPENDENT and constant (0) in
both. Ranks 1, 3, 5, 6, 7, 9, 11, 14 are packet-length/header IMPLEMENTATION_DIFFERENCE;
rank 2 (PSH Flag Count) is FLAG_DEFINITION_DIFFERENCE. Ranks 4, 8, 10, 12 are
LIKELY_EQUIVALENT (counts/rates).

## PortScan vs SSH

Kept separate. Both scenarios' residual shift lands on the same source-verified
implementation-difference features (packet-length basis, header basis, flag counting).
PortScan's residual is somewhat lower (non-time median KS 0.85) than SSH's (1.0), but the
*kind* of difference is common. No empirical magnitude can be attributed because no
same-PCAP extraction exists.

## Interpretation

**Both scenarios: source evidence B / empirical D.** Source-verified implementation
differences (packet-length full-frame basis, IP-only header length, subflow copy, flag-count
semantics, CWR quirk) **plausibly explain a substantial part** of the residual non-time
shift, and they coincide precisely with the model-important residual features. But because
**same-PCAP empirical parity could not be performed**, the implementation-vs-true-domain
split **cannot be quantified**; a genuine traffic/domain component (SSH cipher/MAC/config,
real packet sizes, network conditions) cannot be ruled out and is likely intertwined.

We do **not** say the extractor "caused" the failure. We say the residual shift is
**consistent with** a combination of confirmed extraction-implementation differences and
unquantified true-domain differences.

## Five distinct concepts (kept separate)

1. **Benchmark**: random-v2 Macro F1 0.8805600093815694.
2. **Original laboratory deployment**: PortScan 2/1362 (0.00147); SSH 0/69 (0.0).
3. **Unit-contract corrected**: PortScan 2/1362; SSH 0/69 (unchanged, `lab-feature-compat-v1`).
4. **Extractor implementation difference**: source-confirmed on packet-length,
   header-length, subflow, flags, CWR; magnitude not empirically isolated.
5. **Residual traffic/domain difference**: cannot be separated from concept 4 with the
   retained evidence.

## Limitation

The audit verifies only the Python side from source. The Java side is documented but not
locally executable, and no accepted-run PCAP exists, so the two extractors could not be run
on the same packets. This audit establishes that concrete implementation differences exist
and align with the residual model-relevant shift; it does **not** measure how much of the
shift each cause contributes.

## Albanian thesis subsection

*Pse u desh auditimi: eksperimenti i mëparshëm i kontratës së njësive tregoi se korrigjimi
i mospërputhjes sekonda-mikrosekonda nuk e ndryshoi detektimin, dhe zhvendosja e mbetur
dominohet nga veçori jo-kohore (madhësi paketash, flamuj). Ky fazë kërkoi të ndajë
zhvendosjen e implementimit të nxjerrjes së veçorive nga zhvendosja e vërtetë e domenit.
Evidenca në dispozicion: u ruajtën vetëm CSV-të e flukseve, jo PCAP-të e ekzekutimeve të
pranuara (kapja u bë me `cicflowmeter -i eth0 -c csv`, që nuk ruan paketa), dhe Java
CICFlowMeter nuk është i disponueshëm lokalisht — pra nxjerrja mbi të njëjtin PCAP është e
pamundur (RASTI C). U krye vetëm një auditim i kodit/semantikës. Ndryshime të konfirmuara
nga burimi te `cicflowmeter 0.5.0`: gjatësia e paketës përdor `len(packet)` (korniza e
plotë me Ethernet/IP/TCP), gjatësia e header-it përfshin vetëm header-in IP (`ihl×4`),
subflow-t kopjohen nga totalet, dhe numërimi i flamujve ndjek një semantikë të ndryshme.
11 nga 15 veçoritë më të rëndësishme për modelin kanë një ndryshim të klasës së
implementimit. Interpretim: zhvendosja e mbetur jo-kohore është **në përputhje me** një
kombinim ndryshimesh të konfirmuara të implementimit të nxjerrjes dhe ndryshimesh të
vërteta të domenit; madhësia e secilit shkak nuk mund të matet pa nxjerrje mbi të njëjtin
PCAP. Nuk pretendohet shkakësi dhe nuk thuhet se ndonjë mjet është "i gabuar". Kufizim:
vetëm ana Python u verifikua nga burimi; ana Java është e dokumentuar por jo e ekzekutueshme
lokalisht.

## Artifacts

`availability_audit.json`, `extractor_versions.json`, `semantic_parity.csv`,
`model_relevant_parity.csv`, `summary.json`, and the retained
`cicflowmeter_0_5_0_source/`. No empirical parity files (flow-matching, same-PCAP feature
parity, counterfactual predictions) were produced, because same-PCAP extraction was not
possible — empty artifacts were deliberately omitted.
