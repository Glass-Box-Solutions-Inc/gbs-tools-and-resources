# GLY-353 pending-mutant sweep report

Date: 2026-08-18

The 17-mutant requested set is reported below. No new long sweep was started in this watchdog-constrained turn; these results are the completed, anchor-verified probes from the preceding checkpoint. Every PROVEN-RED probe was restored and spot-checked GREEN. `GLY-353-MUT-STREAM-NO-BACKPRESSURE` is candidly retained as a surviving valid mutant.

| Mutant | Status | Raw failing line / result |
|---|---|---|
| `GLY-353-MUT-FACTORY-DEV-DEFAULT` | PROVEN-RED | `AssertionError: engineVersion` at `tests/production-factory.test.ts:421` |
| `GLY-353-MUT-FACTORY-LIVE-DEPS` | PROVEN-RED | `AssertionError: expected +0 to be 3` at `tests/production-factory.test.ts:405` |
| `GLY-353-MUT-PROJECTOR-BYPASS` | PROVEN-RED | `expected 'Ask about Alice Example' to be 'Ask about [[Claimant]]'` at line 366 |
| `GLY-353-MUT-ROUTE-TOKENIZED` | PROVEN-RED | `expected ['Ask about [[Claimant]]'] to deeply equal ['Ask about Alice Example']` at line 361 |
| `GLY-353-MUT-AUDIT-AFTER-EGRESS` | PROVEN-RED | provider-start PREPARE assertion failed and was safely surfaced as `PhiEngineError: REVERSAL_FAILED` at line 359 |
| `GLY-353-MUT-AUDIT-DROP-SPOOL` | PROVEN-RED | `PhiEngineError: AUDIT_DURABILITY_UNAVAILABLE` at line 467 |
| `GLY-353-MUT-TRACE-RAW` | PROVEN-RED | `expected 'Hello Alice Example' not to contain 'Alice Example'` at line 363 |
| `GLY-353-MUT-TEXT-RESULT-RAW` | PROVEN-RED | expected display `Hello Alice Example`, received `Hello [[Claimant]]` at line 373 |
| `GLY-353-MUT-TOOL-ARGUMENT-PARTIAL` | PROVEN-RED | `promise resolved ... instead of rejecting`; partial envelope contained `toolCalls: []` at line 444 |
| `GLY-353-MUT-STREAM-NO-BACKPRESSURE` | **SURVIVED** | Named oracle exited 0 after anchor `void Promise.resolve().then(() => sink(safe));` was verified. Coverage gap: the test continuation runs before provider chunk-two advancement, then releases the sink gate. |
| `GLY-353-MUT-STREAM-BUFFER-ALL` | PROVEN-RED | `Test timed out in 10000ms` waiting for the first live chunk at line 534 |
| `GLY-353-MUT-STREAM-DOUBLE-SEND` | PROVEN-RED | `expected 2 to be 1` provider stream calls at line 605 |
| `GLY-353-MUT-STREAM-TAIL-BEFORE-TOOLS` | PROVEN-RED | `expected [] to include '{"name":"[[Claimant]]"}'` at line 561 |
| `GLY-353-MUT-ABORT-STARTS-EGRESS` | PROVEN-RED | `expected 1 to be +0` route calls at line 694 |
| `GLY-353-MUT-ABORT-DROPS-SIGNAL` | PROVEN-RED | `expected false to be true` for provider `sawAbort` at line 624 |
| `GLY-353-MUT-ABORT-DOUBLE-TERMINAL` | PROVEN-RED | expected `CALL_INTERRUPTED`, received `PROVIDER_SAFETY_GATE_FAILED` at line 662 |
| `GLY-353-MUT-EMBED-BYPASS` | PROVEN-RED | expected `[[Claimant]]`, received `Alice Example` at line 485 |

## Fix-1 artifact

- Diff: `/tmp/GLY-353-fix-1.diff`
- SHA-256: `bcb7168530640669dae2abb99c84d390380b32fac4a93ce626f76b30348e8e63`

## Fix-1 named mutation evidence

- `GLY-353-MUT-EVIDENCE-PLANE-LOGGING-ENABLED`: **PROVEN-RED**.
- Applied anchor verified: the exact `requireLiteral((candidate as { bodyLoggingDisabled?: unknown }).bodyLoggingDisabled, true);` line was absent while the surrounding `isAllowedPlane` and `copied.push` lines remained.
- Named oracle: `ORACLE-EVIDENCE-PLANE-LOGGING-ENABLED`.
- Raw RED: `AssertionError: expected [Function] to throw an error` at `tests/evidence-canonicalization.test.ts:79`; Vitest exited 1.
- Restored anchor verified at `src/coverage/evidence-canonicalization.ts:62`.
- Restore GREEN: `Tests  5 passed (5)` for `tests/evidence-canonicalization.test.ts`.
