Run manifests for the Phase 16 laboratory experiment (protocol live-lab-v1).

Every manifest is validated by app/live/manifest.py before a run may start. The model
block is checked against the frozen primary model, so a manifest cannot silently point
the laboratory at a different classifier. Topology addresses live here and not in the
inference code, so a different testbed only needs new manifests.

Ground truth modes:
  run_level_uniform   every flow in the capture carries the run expected label; only
                      permitted for an attack run when capture_is_filtered_to_scenario
                      is declared true
  per_flow_selector   flows matching attack_selector are ATTACK; everything else follows
                      unmatched_policy (UNLABELLED by default, never silently ATTACK)
