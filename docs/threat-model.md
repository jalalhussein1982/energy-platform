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
- Mechanism: —
- Gate: —
- Residual risk: —

## 6. SSRF via manifest URL
- Mechanism: —
- Gate: —
- Residual risk: —

## 7. Malicious redirects
- Mechanism: —
- Gate: —
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
