# Contributing to ListingAssistants

Thank you for your interest in contributing to **ListingAssistants** ([ListingAssistants.com](https://ListingAssistants.com)).

Because ListingAssistants operates in a highly regulated domain (residential real estate brokerage, statutory Fair Housing, and escrow fiduciary compliance), all contributions must adhere to strict architectural invariants.

---

## 1. Ground Rules & Invariants

1. **The Invariable Railroad Chassis:** Agents never invent routes. The message track is strictly defined by `identity/routes.json`. Adding a route requires the owner's ratification, the change in `identity/routes.json` and the affected SKILL.md and DECISIONS.md files in this repository (the single source), `python tools/gen_job_descriptions.py`, and tests that drive the new lane through the hub with the payload the real sender produces.
2. **Deterministic Edge Handling:** Do not introduce unconstrained stochastic improvisation into decision paths. Sensitive decisions must be governed by deterministic tuples (see `DECISIONS.md` per agent).
3. **No unsigned authority actions:** listing changes, configuration updates, disclosure releases and human decisions require a verified signature.
4. **Zero Tolerance for Fair Housing Violations:** Any marketing generation must pass statutory compliance screening before publication.
5. **No Regressions:** Every PR must maintain a 100% clean test suite pass (`pytest tests_listing/`).
6. **All agent traffic through the dispatcher:** every message to or from an agent travels through the hub (or the HITL protocol). No code calls an agent's methods directly in production paths.

---

## 2. Development Setup

```bash
git clone https://github.com/QuietFireAI/listing-assistants.git
cd listing-assistants
pip install -r requirements.txt
```

Verify your setup by running the test suite:
```bash
python -m pytest tests_listing/
```
All tests must pass.

---

## 3. Pull Request Guidelines

1. **Branch Naming:** Use clear branch names (`feat/feature-name`, `fix/bug-name`, `docs/doc-update`).
2. **Test Coverage:** Every bug fix or feature must include automated regression tests in `tests_listing/`.
3. **Documentation:** Update relevant documents (`TUNING_MANUAL.md`, `OPERATOR_TUNING_GUIDE.md`, or `AGENT_USER_MANUAL.md`) in the same commit.
4. **Commit Messages:** Use conventional commit formatting (`feat: ...`, `fix: ...`, `docs: ...`, `test: ...`).

---

## 4. Licensing of Contributions

All contributions made to this repository will be licensed under the project's dual-licensing framework (QuietFire Identity License over an AGPL-3.0 floor). By submitting a pull request, you confirm that you have the right to contribute the code.
