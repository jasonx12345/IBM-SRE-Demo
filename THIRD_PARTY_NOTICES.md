# Third-party data

`seed/itbench-coverage/` contains the alert snapshots and ground-truth files for 35 experiments from IBM Research's ITBench-Lite dataset, revision `d0916b08ba421ce5e672e9ad68aa947d938dfef0`. The older `seed/itbench/` subset remains in the repository with its dataset card and license text.

Source: https://huggingface.co/datasets/ibm-research/ITBench-Lite

The upstream dataset card declares Apache License 2.0. The manifest records the original file locations and checksums.

`seed/itbench-coverage.json` is a report derived by this project's `ingest/itbench_coverage.py`. The older `seed/itbench-replay.json` was produced by `ingest/itbench.py`. These importers, matching choices, and reports are project additions, not IBM endorsements or claims about IBM production systems.

Suggested dataset citation: Jha et al., *ITBench: Evaluating AI Agents across Diverse Real-World IT Automation Tasks* (2025), https://arxiv.org/abs/2502.05352.
