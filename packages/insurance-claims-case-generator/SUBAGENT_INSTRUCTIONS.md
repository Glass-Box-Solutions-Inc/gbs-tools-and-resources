# Subagent Instructions — Insurance Claims Case Generator

You are a specialist subagent working on the `insurance-claims-case-generator` package.

**Working directory:** `gbs-tools-and-resources/packages/insurance-claims-case-generator/`
**Linear ticket:** AJC-20
**Parent CLAUDE.md:** Read `CLAUDE.md` in this directory before starting any task.

---

## Your Responsibilities

Execute the assigned implementation phase within scope. Report at phase boundaries. STOP for unplanned architectural decisions.

## Non-Negotiables

1. **100% passing tests + ≥80% coverage** before completing any phase
2. **DocumentType enum** must match `prisma/schema.prisma` EXACTLY (24 values)
3. **TD rate tables** must match `benefit-calculator.service.ts` EXACTLY
4. **No credentials** in any committed file
5. **Synthetic data only** — no real PHI or PII

## Tech Stack

- Python 3.12, Pydantic v2, Click, Faker, pytest, ruff, mypy
- Phase 2+: reportlab, FastAPI

## Test Requirements

```bash
pytest tests/ -v --cov=src/claims_generator --cov-fail-under=80
ruff check src/ tests/
mypy src/
```

## When to STOP

- Unplanned architectural decisions
- Any ambiguity about scope
- Tests failing that you cannot fix in <2 attempts
- Anything touching auth, database, or production systems

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
