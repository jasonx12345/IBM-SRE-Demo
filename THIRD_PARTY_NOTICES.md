# Third-party data

`seed/itbench/` contains a small, unmodified subset of IBM Research's ITBench-Lite dataset, revision `d0916b08ba421ce5e672e9ad68aa947d938dfef0`.

Source: https://huggingface.co/datasets/ibm-research/ITBench-Lite

The upstream dataset card declares Apache License 2.0. The card and license text are retained alongside the source data. The manifest contains original file locations and checksums. No upstream NOTICE file was present in the repository file listing at this revision.

`seed/itbench-replay.json` is a derived, filtered and deduplicated representation produced by this project's `ingest/itbench.py`; source labels and timestamps are retained. The importer, matching choices and locally summarized scenario titles are project additions, not IBM endorsements or claims about IBM production systems.

Suggested dataset citation: Jha et al., *ITBench: Evaluating AI Agents across Diverse Real-World IT Automation Tasks* (2025), https://arxiv.org/abs/2502.05352.
