# Threats to validity — deployment-domain adaptation (design)

These threats apply to any Model B built under this design and must be reported with the
results.

1. **Small laboratory environment.** A single isolated two-host VirtualBox testbed is not
   representative of production networks; adaptation may overfit to this one lab.
2. **Old target services.** Metasploitable2 runs 2008-era services (OpenSSH 4.7, vsftpd,
   Apache), whose traffic profiles differ from modern deployments.
3. **Single attacker/target topology.** One source (192.168.50.10) and one target
   (192.168.50.20); no topological diversity.
4. **Python extractor implementation.** All lab flows use `cicflowmeter 0.5.0`, whose
   feature semantics differ from the original CICFlowMeter (Phase 16E). Model B would be
   tuned to this extractor, which is the intent for deployment consistency but limits
   external validity.
5. **Limited attack families.** Only PortScan and SSH (and later, if approved, others);
   conclusions do not generalise to unseen families.
6. **Run dependence and flow autocorrelation.** Flows within one capture share timing and
   host state; run-level separation mitigates leakage but pooled per-flow metrics can
   overstate certainty. Report run-level variability.
7. **Domain-adaptation overfitting to one lab.** Model B may learn lab artifacts rather
   than generalisable attack structure.
8. **No independent network environment.** No second, differently-built testbed to test
   whether adaptation transfers.
9. **Ground truth at binary/family level.** SSH lacks a defensible exact SSH-Patator
   mapping; primary objective is therefore binary, and exact-label claims are avoided.
10. **Java/Python same-PCAP parity unquantified.** Phase 16F could not build a reproducible
    Java extractor, so the extractor-vs-domain split remains unmeasured; Strategy B fixes
    both at once and cannot separate them.
11. **Replication limits.** Even with ≥3 runs per scenario, the sample of sessions is
    small; confidence intervals will be wide, especially for SSH (thin support).
12. **Paired-comparison dependence on one extractor.** Model A vs Model B are compared on
    Python-extracted flows; Model A was trained on Java-extracted flows, so the comparison
    measures deployment behaviour, not benchmark behaviour, and must be labelled as such.
