# Building on IBM's public SRE ecosystem

**Implemented data update:** The retirement lab now defaults to two public IBM Research ITBench-Lite alert captures. See [IBM_DATA.md](IBM_DATA.md) for the actual source, transformations and limits. This is separate from the proposed authenticated Instana integration below.

Research date: 9 October 2026. Audience: an SRE internship interview. This memo distinguishes documented product capabilities from a proposed integration. It does not establish which products a particular IBM team uses internally.

## Follow-up: public IBM datasets are available

The original research below focused too narrowly on product interfaces. Two public data sources deserve evaluation before authoring more fixtures:

- [IBM Research ITBench-Lite](https://huggingface.co/datasets/ibm-research/ITBench-Lite): alert snapshots and other telemetry from running sandbox environments with injected faults. These are benchmark observations, not IBM customer production incidents. Its alert files make it a promising candidate for this replay tool, subject to checking timestamps, rule identity and incident associations.
- [IBM Cloud Console dataset](https://zenodo.org/records/14062900): published production-derived telemetry with anomaly windows from research involving IBM Canada Lab and Toronto Metropolitan University. It supports anomaly analysis; it is not a ready-made paging-history export.

The ITBench-Lite subset is now downloaded and integrated as the default retirement-lab input. The IBM Cloud Console dataset has not been integrated. Public historical datasets do not provide access to live IBM Instana or Maximo environments.

## Recommendation

Extend Alert Retirement Lab into an **alert-change review companion for IBM Instana**, with an optional, explicitly mapped **Maximo IT incident export**. This preserves the current working replay engine while adding a substantive connection to IBM's published interfaces.

The review question remains: if a team removes several paging rules together, which recorded incidents lose their first warning or receive it later? A candidate importer should feed the existing calculation and evidence views, rather than merely rename the demo's alerts.

This is a proposed next implementation. The current application accepts its own normalized JSON format; it does not yet import native Instana or Maximo IT exports or connect to either product.

## Findings from primary sources

| IBM capability | Verified source | Relevance |
| --- | --- | --- |
| Instana exposes historical events through `GET /api/events`, with time-window and update filters. | [Instana OpenAPI description](https://github.com/instana/openapi/blob/master/spec/descriptions/getEvents.md) | A documented history source for a read-only importer. Event records alone do not establish which notifications reached on-call staff. |
| Instana supports webhooks and external alert destinations. Delivery may be retried. | [IBM alerting documentation](https://www.ibm.com/docs/en/instana-observability?topic=integrations-alerting) | An adapter must distinguish event lifecycle updates and retried delivery from new events. |
| IBM maintains a public Python API client. | [instana/client-python](https://github.com/instana/client-python) | Matches the project's Python implementation and provides an integration starting point. |
| Instana webhook alerts can create incidents in Maximo IT. | [IBM's integration architecture](https://www.ibm.com/docs/en/max-it/cd?topic=webhooks-architecture) | A concrete documented relationship between the two products. This does not prove the intern's team uses that integration. |
| Instana Smart Alerts preview thresholds and violations against historical data. | [IBM Smart Alerts documentation](https://www.ibm.com/docs/en/instana-observability?topic=applications-smart-alerts) | Historical alert preview is already present; the proposed focus is combined removal review and independent incident evidence. |
| Certain Maximo Application Suite applications have a serviceability dashboard implemented with Grafana, OpenTelemetry and Prometheus. | [IBM serviceability dashboard documentation](https://www.ibm.com/docs/en/masv-and-l/cd?topic=monitoring-using-serviceability-dashboard) | Establishes a real connection to common observability tools. The page covers named applications, not every Maximo component or deployment. |
| IBM's MAS development team publishes an Ansible collection and a reference CLI built on it. | [MAS DevOps collection](https://ibm-mas.github.io/ansible-devops/) | A stronger alternative if a target role specifically emphasizes Maximo deployment, upgrade or backup automation. |
| IBM Cloud Pak for AIOps already correlates alerts by time, topology and scope. | [IBM alert groups documentation](https://www.ibm.com/docs/en/cloud-paks/cloud-pak-aiops/4.13.0?topic=alerts-about-alert-groups) | Generic alert correlation would substantially overlap existing IBM functionality. |

Maximo IT is the incident/service-management context in the documented integration. It should not be treated as interchangeable with all of Maximo Application Suite's asset-management functions.

## Concrete next version

1. **Native event import.** Parse a pinned, documented Instana event or webhook format into the existing replay schema. Retain source IDs and provenance. Handle lifecycle updates, duplicates and invalid timestamps explicitly.
2. **Explicit paging and rule mapping.** Identify the originating rule and its service from reliable configuration or supplied mappings. Do not equate critical severity with a delivered page. Label results as event coverage unless paging evidence supports the stronger claim.
3. **Independent incident evidence.** Accept a reviewed incident ledger, optionally from Maximo IT, including customer-reported or manually created incidents. Preserve an explicit mapping between Instana event IDs and incident ticket IDs; do not join by similar titles or assume identifiers are interchangeable.
4. **Existing replay engine.** Compare each retirement and the full batch, display lost and delayed first warnings, and retain unknown associations in the evidence summary.
5. **Review artifact.** Export the source provenance, mapping assumptions, input fingerprint, proposed removals, per-incident outcomes and unresolved evidence gaps with the report.

Importing only tickets automatically created by Instana would give a biased ledger: incidents without an alert could disappear from the evaluation. Separately reviewed incident evidence is therefore necessary for the intended coverage interpretation. This is an engineering inference from the documented integration and the replay model, not a claim made by IBM.

## Demo without IBM access

Use authored fixtures conforming to the selected documented IBM payload format. Keep them visibly marked synthetic. Demonstrate conversion, duplicate handling and the existing combined-removal failure case. This can run in the present local Python application without deploying Maximo, Docker or Kubernetes.

Compatibility levels should be named accurately:

- **Designed from public documentation:** field mapping has been researched.
- **Fixture-tested adapter:** implementation passes tests against authored/documented examples.
- **Live-validated integration:** actual output from a permitted IBM product environment has been successfully imported and compared with its source.

The current project has not reached the second or third level for IBM formats. A live validation would require access to an appropriate environment or authorized exports; no accounts, credentials or infrastructure are needed for the initial fixture-based implementation.

## Alternatives and tradeoffs

- **Instana review companion — recommended for this project:** directly extends the existing alert replay work and has documented interfaces. Its relevance to a specific IBM team must still be checked against the job description.
- **Maximo automation contribution:** inspect the public MAS Ansible collection for a reproducible issue, then contribute a test, fix or documentation improvement. A real reviewed contribution would demonstrate work with IBM-maintained code, but a useful issue and adequate validation environment must first be found. No issue or pull request has been selected or submitted.
- **Running a full sample microservice stack:** could produce real local incident telemetry later, but adds setup. The original `instana/robot-shop` repository was archived on September 2, 2026; it should not be presented as an actively maintained starting point. [Repository status](https://github.com/instana/robot-shop)

## Interview positioning

Explain the verified IBM workflow, the adapter and test evidence actually completed, and the assumptions the analysis cannot establish. Do not claim access to IBM's internal operational data, endorsement, or that IBM lacks an equivalent internal tool. A researched technical decision and a demonstrable implementation are stronger evidence of preparation than a company logo or an unsupported uniqueness claim.
