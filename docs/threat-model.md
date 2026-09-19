# Threat model (ADR-008) — stub

| | |
|---|---|
| Status | **STUB.** Headings only; completed in Phase 6. Each item gets Mechanism / Gate / Residual risk. |
| Reads with | `02-architecture-decisions.md` ADR-006, ADR-007, ADR-008; `05-constraint-matrix.md` (Phase 3) |

Mandatory flow: `Internet content → UNTRUSTED DATA → bounded extractor/sample → LLM triage → suggested patch → CI → human`. Never `Internet → LLM → production action`.

## 1. Indirect prompt injection
- Mechanism: —
- Gate: —
- Residual risk: —

## 2. Malicious source response
- Mechanism: —
- Gate: —
- Residual risk: —

## 3. Dependency hallucination / slopsquatting
- Mechanism: hash-pinned `uv.lock`; `deps-allowlist.txt`; ADR per new package (Phase 0, in place)
- Gate: `make deps-allowlist` (CI job `deps-allowlist`)
- Residual risk: —

## 4. Credential exfiltration
- Mechanism: no credential in the repository; `make secret-scan` (Phase 0, in place); secrets only via `secretRef` (ADR-017)
- Gate: CI job `secret-scan`
- Residual risk: —

## 5. Unsafe shell generation
- Mechanism: `subprocess`, `os.system`, `os.popen`, `importlib`, `ctypes` banned outside `energy_platform/fetch/` and `scripts/` (ADR-027 §3, in place); targets cannot import them at all (positive allowlist, ADR-027 §2)
- Gate: `make lint` (ruff TID251 + `check_target_surface.py`)
- Residual risk: platform code in `scripts/` may shell out by design; reviewed by CODEOWNERS

## 6. SSRF via manifest URL
- Mechanism: ADR-026 — host must be in the manifest **and** the CODEOWNERS-protected host registry; https only; resolved addresses checked against private/metadata ranges; NetworkPolicy default deny with public-443-only egress for capture pods (Phase 2 fetch, Phase 5 chart)
- Gate: Phase 3 negative tests (fake transport); Phase 5 live egress test under an enforcing CNI; V-11 on the tenant
- Residual risk: tenant CNI enforcement unverified until V-11; the fetch layer is the control known to hold

## 7. Malicious redirects
- Mechanism: ADR-026 — client never follows redirects; fetch follows up to `max_redirects` and validates every hop like the first request (Phase 2)
- Gate: Phase 3 negative tests: redirect to private address, redirect to unlisted host
- Residual risk: —

## 8. Archive poisoning
- Mechanism: —
- Gate: —
- Residual risk: —

## 9. PR supply-chain attack
- Mechanism: —
- Gate: —
- Residual risk: —

## 10. Mapping-level data poisoning (a patch that silently flips a sign or unit)
- Mechanism: —
- Gate: —
- Residual risk: —
