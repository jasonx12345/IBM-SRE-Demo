# Simple IBM SRE demo script

[Open the report.]

> “I made this project to show that **observability can be tested**. If we deliberately cause a fault, we should be able to ask: *did the warning we expected actually appear?*
>
> I used real, public data from [IBM Research's ITBench-Lite dataset](https://huggingface.co/datasets/ibm-research/ITBench-Lite), not alerts I made up. IBM published the alerts expected in each test and snapshots of the alerts that appeared. My software compares the two.
>
> Across 35 tests, there were **96 expected alerts**. The report found **61**, did **not find 30** in the published snapshots, and marked **5 unknown** because the evidence was incomplete.”

[Open **Scenario-1**.]

> “Here, both expected alerts appeared.”

[Choose **Needs review**, then open **Scenario-4**.]

> “Here, two of the four expected alerts did not appear in the snapshots. That gives an SRE a focused place to investigate: these particular warnings and their alert rules, instead of searching through countless files without knowing where to start.
>
> A missing match does not prove a monitor was broken or that nobody was paged. My goal is to make fault tests more useful by showing **what monitoring caught, what it did not show, and what needs a closer look**.”
