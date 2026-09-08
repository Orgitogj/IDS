# Empirical extractor parity (Phase 16F) — BLOCKED at the tooling gate

**Diagnostic only. No traffic generated, no PCAP captured, no parity fabricated.**

The goal was a same-PCAP dual extraction (Java CICFlowMeter vs Python cicflowmeter 0.5.0)
to empirically separate feature-extraction implementation shift from true traffic/domain
shift. Per the phase's own gate (B2), diagnostic traffic may be generated **only after** a
reproducible Java extractor passes a smoke test. That gate was **not met**, so the phase
stopped before any traffic.

## What was attempted (B1)

The official upstream source was cloned (outside the repository):

- `ahlashkari/CICFlowMeter`, commit `98a5ebad0df579cc8b43eedd3421b3ae87699901`
- location: `C:/Users/orgit/ids-tooling/CICFlowMeter` (not in this repo)

Its build contract was inspected directly from `build.gradle`, the gradle wrapper, and the
bundled native library.

## Why a reproducible build could not be established

| requirement | available | result |
|---|---|---|
| Java 8 (`sourceCompatibility=1.8`) | host: Java 17; Kali: Java 25 (+ apt Java 11) | **no Java 8 anywhere; not apt-installable on Kali** |
| Gradle 4.2 wrapper (needs Java 7–9) | Java 11 / 25 only | **Gradle 4.2 cannot run on Java 11/25** |
| jnetpcap 1.4.r1425 (2013) JNI native | modern JVMs | **very unlikely to load on Java 11/25** |
| Windows runtime (Npcap/wpcap.dll) | not installed | driver install **out of scope** |

Assembling Java 8 + Gradle 4.2 + jnetpcap 1.4 would require manually downloading a JDK 8
and an old Gradle from third-party sources — **non-reproducible** and against the phase's
guidance ("do not use a random binary from an unverified third-party mirror"; build must be
reproducible). Rewriting `build.gradle` for a modern Gradle would modify the tool and still
leave the jnetpcap-on-modern-JVM runtime problem.

## Decision (B2)

**STOP.** No diagnostic parity traffic was generated; no dual extraction was performed. This
is the honest outcome of the reproducibility gate, not a partial result.

## Consequence

**CASE C persists.** Empirical same-PCAP extractor parity remains infeasible with the
available systems, now for a second, deeper reason (the Java-8 / Gradle-4.2 / jnetpcap-1.4
toolchain cannot be reproducibly built on either the host or the Kali guest). The Phase 16E
**source/semantic** audit — which verified the Python side from source and classified 11 of
15 model-important features as carrying an implementation-class difference — stands as the
strongest available evidence. Its limitation is unchanged and must remain explicit: the
Java side is documented, not locally verified, and the implementation-vs-true-domain split
was not empirically quantified.

## What would unblock this later (not attempted here)

- A reproducible Java 8 environment (e.g., a pinned container image or a controlled JDK-8
  install) plus a jnetpcap build that loads under it; **or**
- a maintained Java extractor that runs on a modern JVM and is documented as
  CICFlowMeter-equivalent; **or**
- capturing a PCAP during a future controlled run (tcpdump is present on Kali) so the
  packet-level evidence at least exists for whenever a working Java extractor is available.

None of these were performed; each is a setup decision for review.

## Artifacts

`tooling_provenance.json` (this blocker, machine-readable). No empirical parity files
(flow matching, feature parity, prediction parity) were created, because no extraction was
performed — empty artifacts were deliberately omitted.

## Albanian thesis paragraph

*Faza 16F synonte një krahasim empirik të të njëjtit PCAP midis Java CICFlowMeter dhe Python
cicflowmeter 0.5.0. Porta metodologjike (B2) lejon gjenerimin e trafikut diagnostik vetëm
pasi një ekstraktues Java i riprodhueshëm të kalojë një test. Kjo portë nuk u plotësua:
CICFlowMeter kërkon Java 8 me Gradle 4.2 dhe jnetpcap 1.4 (2013), ndërsa as hosti as Kali
nuk ofrojnë Java 8 (vetëm Java 11 dhe 25), Gradle 4.2 nuk ekzekutohet në Java 11/25, dhe
jnetpcap 1.4 nuk ngarkohet besueshëm në JVM moderne. Ndërtimi i riprodhueshëm nuk ishte i
mundur pa shkarkime manuale nga burime të palëve të treta, çka do të cenonte
riprodhueshmërinë. Prandaj u ndalua para gjenerimit të çdo trafiku dhe nuk u fabrikua asnjë
rezultat pariteti. Rasti C mbetet: pariteti empirik i të njëjtit PCAP është i parealizueshëm
me sistemet aktuale, dhe auditimi burim/semantik i Fazës 16E mbetet dëshmia më e fortë në
dispozicion, me kufizimin e tij të qartë se ana Java është e dokumentuar por jo e verifikuar
lokalisht.*
