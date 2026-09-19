# Primary-source checks

Checked on 19 September 2026 with the web retrieval tool. This is a selective corroboration ledger for material technical claims, not a repeat of S01–S17 or an authoritative legal assessment. Retrieved pages can be cached; no SOAP operation or polling campaign was executed.

| Source | What it supports | Limit |
|---|---|---|
| [Helm 3 chart tests](https://docs.helm.sh/docs/v3/topics/chart_tests/) | Test hooks are invoked through `helm test` | Does not certify a chart or deploy wrapper that has not been written |
| [Helm 3 hook lifecycle](https://docs.helm.sh/docs/v3/topics/charts_hooks/) | Install/upgrade hooks and test hooks have different lifecycle triggers; failed blocking Job hooks affect the release | Supports F07; proposed rollback flow still needs an actual drill |
| [Helm 3 upgrade command](https://helm.sh/docs/v3/helm/helm_upgrade/) | Atomic upgrade rollback and wait behavior | A later command is not part of an already completed atomic upgrade |
| [Kubernetes NetworkPolicy](https://kubernetes.io/docs/concepts/services-networking/network-policies/) | Policy works through pod/namespace/IP selectors and requires an enforcing network plugin | Supports F08; does not establish the actual reference cluster's effective egress controls |
| [Kubernetes NetworkPolicy API](https://kubernetes.io/docs/reference/kubernetes-api/networking/network-policy-v1/) | Egress peers and IPBlock schema | Standard schema does not express the hostname allowlist promised in ADR-008 |
| [Astral locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/) | `--frozen` uses the lock without checking freshness; locked mode has a different purpose | Supports F11; no successful fresh online install was attempted |
| [OTE public-web documentation index](https://www.ote-cr.cz/cs/dokumentace/xsd-wsdl-manual-pubweb) | Official index links the public-service manual | Documentation availability is not a live ingestion result |
| [OTE public-service manual, 13 April 2026](https://www.ote-cr.cz/cs/dokumentace/xsd-wsdl-manual-pubweb/cs/dokumentace/xsd-wsdl-manual-pubweb/uzivatelsky-manual_webove_sluzby_ote_k.pdf) | Revision date and endpoint-change history; section 1.3.4.2 describes intraday weighted prices and volumes, PT15M/PT60M and period indices; EUR/MWh and MWh precision agree with the proposed T1 contract | Does not verify the missing dated response captures, live latency or ČEPS interval semantics |
| [OTE continuous intraday results](https://www.ote-cr.cz/en/short-term-markets/electricity/intra-day-market) | Retrieved page displayed 17 September 2026, matching the first three sample price/volume pairs cited in the scope document, and the richer buy/sell/min/max/last columns | This is corroboration of that displayed page, not a current full-day capture or proof of rolling publication cadence |
| [OTE terms of use](https://www.ote-cr.cz/en/documentation/term-of-use) | The page contains copying restrictions and disclaims guaranteed uninterrupted service | Confirms the importance of the repository's open reuse question; does not decide the legal applicability of each planned use |

The OTE manual was read for the narrow facts above. Its contents and market datasets were not copied wholesale into this review.

## Unresolved source checks

- The retrieval tool could not access the [ČEPS web-services page](https://www.ceps.cz/en/web-services) or [ČEPS WSDL](https://www.ceps.cz/_layouts/CepsData.asmx?WSDL). This is not a finding that ČEPS is down. Start/end interval semantics, cadence and service-use terms remain unverified here.
- The tool reported unsupported XML content when opening the [OTE WSDL](https://www.ote-cr.cz/pw-data/services/PublicDataService?wsdl). The manual supports the basic contract; exact live schema optionality was not independently checked. Do not silently replace a live-WSDL claim with a manual-only claim.
- Original S01–S17 request/response evidence, hashes and DST workbooks were not supplied. No attempt was made to locate them in unrelated folders or private accounts.
- Private e-INFRA/Rancher/OpenStack/object-store capabilities were not queried. The recorded log in `docs/00-assumptions.md` is historical repository evidence, not a current independent verification.
- The regulatory references and entity-specific applicability mentioned in the architecture were not adjudicated. They are not needed to determine whether the software fulfills this brief. Preserve their unresolved status rather than presenting the design as legal or regulatory compliance.
