# Contributing to ListingAssistants

Thank you for your interest in contributing to **ListingAssistants** ([ListingAssistants.com](https://ListingAssistants.com)).

Because ListingAssistants operates in a highly regulated domain (residential real estate brokerage, statutory Fair Housing, and escrow fiduciary compliance), all contributions must adhere to strict architectural invariants.

---

## 1. Ground Rules & Invariants

1. **The Invariable Railroad Chassis:** Agents never invent routes. The message track is strictly defined by `identity/routes.json`. Adding a route requires formal ratification, updating `generate_skills.py`, and updating the route test matrix.
2. **Deterministic Edge Handling:** Do not introduce unconstrained stochastic improvisation into decision paths. Sensitive decisions must be governed by deterministic tuples (see `DECISIONS.md` per agent).
3. **No Unsigned Fiduciary Actions:** Pricing, listing status changes, and funds/wire-related items require cryptographic verification.
4. **Zero Tolerance for Fair Housing Violations:** Any marketing generation must pass statutory compliance screening before publication.
5. **No Regressions:** Every PR must maintain a 100% clean test suite pass (`pytest tests_listing/`).

---

## 2. Development Setup

```bash
git clone https://github.com/QuietFireAI/listing-agents.git
cd listing-agents
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
