# Ops Reconciliation Engine — Implementation Audit

Audit date: 2026-09-25. Baseline: commit `95daf51`, with pre-existing untracked `reports/` left untouched. This document records the original implementation before remediation; the final section records subsequent verification. No application changes preceded this audit. Running the existing suite did invoke its demo generator test, which rewrites the fixtures with identical bytes.

## 1. Executive Summary

**Mostly complete, but not ready to publish unchanged.** The application implements the intended local CSV → validation → reconciliation → human review → export workflow. Its demo, typed findings, configuration, SQL and headless UI tests are real implementations. It is not a payroll engine and does not approve or resolve findings.

Passing tests conceal material gaps: salary classification rounds before applying thresholds; missing optional columns produce fabricated changes; privacy can be disabled or bypassed through messages; duplicate matching arbitrarily chooses a row. Error handling and UI state also need work. These are operational correctness issues, not reasons to rewrite the application.

Baseline execution: Python 3.14.4; pandas 3.0.2; Streamlit 1.64.0; Pydantic 2.13.4; PyYAML 6.0.3; pytest 9.1.1. `python -m pytest --cov=src --cov-report=term-missing`: **184 passed in 4.43s, 96% statement coverage** (856 statements, 30 missed). `python -m pip check`: no broken requirements. Ruff 0.16.9 reports three findings (unused noqa and two dict-constructor style findings); inherited Ruff settings affect this result. No type-check command is configured.

## 2. Specification Compliance Matrix

| Requirement | Status | Evidence | Problem | Recommended Action |
| ----------- | ------ | -------- | ------- | ------------------ |
| Local two-cycle CSV workflow | PASS | app.py; src/engine.py; AppTest demo | Core path executes | Preserve architecture |
| Synthetic demo without services | PASS | 200 previous / 203 accepted current rows, one skipped row | No duplicate IBAN across distinct employees in demo | Keep focused regression fixtures |
| Expected 13-field schema | PASS | src/models.py EXPECTED_COLUMNS | Domain-specific schema intentionally fixed | Document limitation |
| New / removed records | PARTIAL | reconciliation.detect_new_records / detect_removed_records | Skipped malformed rows can look like lifecycle events | Mark comparisons incomplete |
| End dates added / start dates changed | PASS | compare_dates and tests | Invalid dates also look emptied | Explain usable-value semantics |
| Duplicate ID / email / IBAN | PARTIAL | validators.check_duplicates | ID severity configurable below critical; arbitrary first-row matching | Enforce invariant; skip ambiguous matching |
| Configurable required values | PASS | Rules.required_fields; validator | Key always required | Keep |
| Salary thresholds | FAIL | utils.percentage_change; compare_salary | 15.0001% becomes INFO; 30.0001% becomes WARNING | Classify unrounded percentage |
| IBAN critical + review | FAIL | IbanChangeRules accepts info/false | Mandatory product guarantees can be disabled | Reject unsafe config |
| IBAN masking | FAIL | display_value, validation messages | masked_fields=[] exposes IBAN; IBAN pasted in salary leaks | Enforce masking at output boundaries |
| Contract / hours / department changes | PARTIAL | compare_record | Missing optional column treated as cleared value | Track unavailable columns |
| Bonus 50% / 100% | PASS | anomaly_detection and boundaries | Zero salary deliberately skips ratio | Document undefined ratio |
| Overtime negative / 60 / 100 | PASS | overtime_severity and boundaries | Custom minimum message still says negative | Make explanation reflect configured minimum |
| Negative salary, dates, email, missing ID | PASS | validators; behavior tests | Infinity passes numeric validation | Reject non-finite values |
| Config actually controls engine | PARTIAL | engine threshold / review tests | Not cosmetic, but not every severity configurable; unsafe values accepted | Validate safety invariants; document fixed severity bands |
| Structured findings | PASS | frozen Pydantic Issue, enums, CSV schema | Model alone does not guarantee sanitized strings | Harden construction boundary |
| Simple Python / pandas / Streamlit stack | PASS | requirements and imports | Streamlit minimum not verified against used APIs | Use tested minimum or test lower bound |
| Responsibility separation | PASS | loader / validators / reconciliation / reporting / app | Some privacy policy bypasses cross layers | Small shared sanitization helper |
| Meaningful SQL | PASS | all statements execute in SQLite tests | Illustrative, not full engine parity; joins multiply duplicate keys | Label limitations; safe short-value masking |
| Header / principle / uploads / demo | PASS | app.py, AppTest | Synthetic disclosure missing from active demo UI | Add caption |
| Operational summary | PARTIAL | 17 critical, 19 warning, 10 info; 23 changes; 32 review records | Keyless row numbers merge across cycles | Include cycle in keyless identity |
| Filterable review table | PASS | severity/category/review/ID filters | Previous/current validation findings lack cycle column | Add provenance |
| Detail + suggested checks | PARTIAL | explain.py, record_snapshot | First duplicate row only; masked collisions hide Changed flag | Show affected rows; compare raw normalized values |
| Full and review exports | PARTIAL | 46 full / 36 review findings | Formula-like strings not neutralized for spreadsheets | Escape textual formula cells |
| Empty / error / reset states | PARTIAL | app.py | Failed rerun leaves old downloads; ?demo reset reloads | Clear stale result; reset demo parameter |
| Human-in-the-loop | PARTIAL | no approval/fix action | First duplicate selected as authoritative comparison | Do not select an ambiguous record |
| Optional AI | PARTIAL | explicit button, templates, mocked SDK tests | No live verification; error coverage incomplete; README payload claim inaccurate | Retain optional path, honest limitations |
| Malformed / empty / missing / duplicate headers | PARTIAL | loader tests | Unclosed quote accepted; NUL accepted; config I/O errors uncaught | Strict parse and clean error boundaries |
| Privacy / persistence / logging | PARTIAL | uploads stay in session, CLI writes explicit reports | logger.exception can log sensitive exception values; framework telemetry not configured | Safe logs and disable usage telemetry |
| Behavioral tests | PARTIAL | 184 passing tests | High line coverage misses combined edge cases and UI transitions | Add end-to-end regressions |
| README problem/principle/workflow | PASS | README sections | Clearly explains purpose | Preserve |
| README features/config/privacy/setup | PARTIAL | README vs executed probes | Overclaims masking, skipping checks, universal config, throughput evidence | Correct claims and verify commands |
| Deliberate exclusions / future ideas | PASS | README dedicated sections | Future work clearly separated | Keep out of remediation scope |
| Payroll calculations / infrastructure | NOT APPLICABLE | No taxes, obligations, DB, queues, auth, cloud | Correctly absent | Do not add |

## 3. Critical Gaps

1. **P0: salary thresholds lose precision before classification.** In `src/utils.py:percentage_change`, rounding 2000 → 2300.002 yields 15.00 and INFO; 2000 → 2600.002 yields 30.00 and WARNING. Both contradict strict greater-than thresholds.
2. **P0: sensitive output can leak.** `Rules(masked_fields=[], iban_change={severity: info, requires_review: false})` is accepted; the changed full IBAN appears in exported value columns. A full IBAN supplied as an invalid monthly_salary appears in both values and diagnostic text. Adding first_name to masked_fields does not hide the name in new-record messages.
3. **P0: absent columns create false changes.** Dropping the IBAN column from one cycle emits a critical IBAN removal even though notes say related checks are skipped. Optional contract/date/hours columns have the same issue.
4. **P0: ambiguous IDs silently use the first row.** `index_by_key` drops duplicate rows; reversing their order changes findings. A critical duplicate warning helps, but selecting one row still embeds an unsupported assumption.

## 4. Functional Issues

- `inf` salary parses and produces a misleading zero-baseline warning instead of invalid_number; other numeric columns accept infinities too.
- CSV reader is non-strict: an unclosed quoted numeric field is accepted; embedded NULs are accepted.
- A failed run retains the prior result and export buttons, risking use of the wrong reports. Current rules can also be shown beside results generated under older rules.
- Two keyless records at row 2 in different cycles count as one review record (`reporting.build_summary`).
- Snapshot change indicators compare masked/display-rounded values rather than underlying data; two different IBANs with identical visible prefix/suffix appear unchanged.
- Config loading catches YAML errors but not decoding/I/O errors; falsey non-mapping YAML becomes defaults. Non-finite thresholds are not uniformly rejected.
- CLI output filesystem errors occur outside its friendly-error boundary. Unexpected UI exceptions are logged with potentially sensitive values.
- Formula-prefixed uploaded text is exported verbatim. CSV quoting alone does not force a spreadsheet to treat a cell as literal text.

## 5. Architecture Review

The pipeline has coherent responsibilities and no circular imports or unnecessary infrastructure. IssueFactory removes repetitive issue construction without creating a plugin framework. Small CLI orchestration is justified. `utils.py` is cohesive (normalization, formatting, masking). No core TODO placeholders were found.

Weak points are loss of provenance during coercion/alignment, arbitrary duplicate matching and decentralized message formatting. Keep modules; add minimal metadata and a consistent sanitization boundary. `Any` unions in loader/engine provide little static assurance; a configured type checker is absent. This is a maintainability concern, not a release-blocking rewrite request.

## 6. Reconciliation Logic Review

| Rule / manual scenario | Baseline result |
| --- | --- |
| A unchanged | Existing end-to-end/validator tests find no anomaly |
| B/C/D 2000 → 2200/2400/2800 | Algorithm gives INFO/WARNING/CRITICAL; exact fixtures added during remediation |
| Salary 15%, 15.0001%, 30%, 30.0001% | Executed CSV probes: INFO, INFO (wrong), WARNING, WARNING (wrong) |
| Salary decrease / zero / null | Magnitude classification; zero gives WARNING without percent; missing current is validation-only |
| E IBAN change | Default critical, review, masked; configuration can invalidate guarantees |
| F duplicate ID | Default critical; repeated IDs compare first row only |
| G/H bonus 60% / 120% | Warning / critical by implemented ratio checks; existing 50%/100% boundary tests pass |
| I/J/K overtime -1 / 80 / 120 | Critical / warning / critical by implemented checks; boundary tests pass |
| L end before start | Critical finding, tested |
| M/N new / removed | Correct for well-formed unique keys, tested |
| O malformed email | Warning finding, tested; pragmatic format check, no address verification |
| Required fields | Raw blanks flagged without duplicating invalid-number findings |
| Duplicate email / IBAN | Case-normalized emails, whitespace-normalized IBANs; same repeated employee suppressed as redundant |
| Dates / contract / department / hours | Implemented and tested; absent-column caveat above |

Business thresholds genuinely come from YAML. Mirrored schema defaults are explicit and equality-tested, not hidden arbitrary constants. However salary/bonus/overtime severity bands and zero-baseline treatment are fixed in code: README's universal configurability claim is too broad. Hard safety guarantees should remain fixed.

## 7. UI/UX Review

AppTest executes initial state, demo metrics, table and downloads. Local Streamlit startup is separately health-checked. The UI offers meaningful filters and deterministic explanations with operator checks. Seven summary cards can be cramped on narrow screens; this is secondary to accuracy.

Fix stale result state, distinguish cycle/row provenance, show explicit no-findings versus no-filter-matches states and synthetic-demo disclosure. Duplicate snapshots must expose all candidate rows. Reset should actually reset when entered through ?demo=1. Headless tests do not establish browser pixel layout or real upload widget interactions; no fabricated visual sign-off is implied.

## 8. Privacy Review

Default IBAN field changes and duplicate findings are masked, and demo export probes confirm this normal path. No app upload persistence or automatic external AI call exists. However field masking is optional, message interpolation bypasses it, invalid inputs can contain bank identifiers and logger.exception includes exception content. The Issue docstring's safety assertion is not enforced by its original schema. Configured name masking also leaks lifecycle names.

Outputs should sanitize configured field values and recognizable IBAN text; IBAN masking must be mandatory. This is not a general DLP product: arbitrary secrets in arbitrary user text cannot be reliably inferred. Disable Streamlit usage telemetry for an accurate local-by-default posture. Preserve explicit opt-in AI and disclose that other displayed personal fields can be sent with the finding.

## 9. Testing Review

Baseline exact result: **184 passed in 4.43s; 96% src statement coverage**. SQL tests execute all examples and assert meaningful demo results. AppTest exercises UI glue. Tests are mostly behavioral; a few assert dtype/schema or exact counts, reasonable as secondary checks.

Weaknesses: salary threshold unit tests bypass the rounded calculation; tests deliberately lock in first-row duplicate matching; privacy checks use narrow Italian/long-IBAN regexes and ordinary field placement; demo generation test writes repository files despite accepting tmp_path; UI errors are tested only with initially empty state; absent-column notes are asserted without asserting absence of false changes. AI tests use a fake SDK and cannot prove live service compatibility. No minimum-version or type-check matrix exists.

Additional read-only probes reproduced every critical gap and the infinity, malformed-quote and cross-cycle keyless-count errors. Existing reports/ was not overwritten. Dependency compatibility check passes. Ruff reports 3 findings. Actual startup/CLI/export results and expanded exact scenario results are recorded after remediation.

## 10. README / Documentation Review

The problem, product principle, workflow, architecture rationale, deliberate exclusions, demo instructions and future list are substantial and mostly accurate. Correct these claims:

- “Related checks skipped” is false for cross-cycle comparisons with absent optional columns.
- “All thresholds and severities” overstates configuration; severity bands contain constants by design.
- “Masks IBANs everywhere” and configurable name masking are false on reproduced paths.
- AI payload contains finding + template, not a separate rules configuration object; no live service call was verified.
- “Every problem ... never as a stack trace” is not true for config read/output-write paths.
- Performance numbers have no reproducible benchmark artifact in the repository. Remove them rather than invent measurements.
- Generator uses random check digits and cannot guarantee every identifier has an invalid checksum; say checksum validity is not guaranteed.
- Clone URL is an explicit placeholder; Python 3.12 minimum is declared but this audit runtime is 3.14.4.

## 11. Overengineering Review

No unnecessary infrastructure was found. Optional LLM rewrites are marginal product value compared with already adequate templates, but they do not gate the core workflow; do not expand them. Existing modules and typed configuration are proportionate. No reason to add Docker, auth, a database, microservices or a new frontend.

## 12. Underengineering Review

Simplicity became fragility at data provenance (absent vs blank, duplicate vs authoritative), precision, sensitive message handling, CSV spreadsheet safety, configuration error boundaries and session transitions. These merit targeted fixes and behavioral regression tests rather than a framework.

## 13. AI-Generated-Code Smells

Code origin cannot be inferred reliably. Observable smells include decorative section dividers throughout small modules, broad documentation claims not matched by tests, repeated Any/type-ignore usage and the unexplained live-model default. Most comments otherwise explain intent rather than obvious syntax. Reduce claims, test cross-layer behavior, and avoid stylistic rewrites of working modules. No dead placeholder modules or commented-out implementations were found.

## 14. Prioritized Remediation Plan

### P0 — Must fix before publishing

- Classify salary with unrounded precision; test both sides of boundaries through CSV loading.
- Preserve absent-column provenance; do not fabricate clearing events.
- Enforce critical/review IBAN and critical duplicate-ID invariants; mask sensitive output and safe-log errors.
- Exclude ambiguous IDs from cross-cycle decisions; expose duplicates for human review.
- Neutralize formula-prefixed exported text.

### P1 — Should fix before publishing

- Reject non-finite numerics and malformed CSV; handle config and report I/O cleanly.
- Clear stale UI results, retain rules used by a run, repair reset and snapshot semantics.
- Count keyless review records by cycle and row; expose provenance and empty/demo states.
- Expand scenario/regression tests; isolate generator test writes.
- Correct README, establish tested dependency floor, disable telemetry, document SQL limitations.

### P2 — Nice to improve

- Add minimum-version CI/type checking, browser interaction coverage and reproducible benchmarks later.
- Consider pagination only when demonstrated queue sizes need it.
- Keep optional AI as unverified against a live provider unless explicitly tested with credentials.

## 15. Final Readiness

**YES, AFTER P0 + P1 FIXES.** The repository demonstrates deterministic operational modeling, useful exception review and a suitably simple architecture. Its original implementation needs correctness/privacy fixes before those professional claims are credible. This judges the repository, not its developer.

# Post-Remediation Verification

The preceding sections intentionally preserve the baseline findings; they are not a claim that fixed defects remain open.

## Fixes completed

- **Threshold correctness:** salary classification uses unrounded percentages, with decimal arithmetic to avoid binary floating-point boundary noise. Reports retain six decimals; the compact UI cell remains rounded to two and the finding/detail explains the higher-precision value. Added end-to-end positive/negative 15%, 15.0001%, 30%, 30.0001% cases and an exact fractional baseline.
- **Reliable comparison:** loader/validator retain missing-column metadata. A column absent in either file is excluded from cross-cycle comparison without suppressing available single-cycle validation. Duplicate IDs are excluded from both sides of comparison; all candidates remain visible in the snapshot. Notes warn when skipped malformed rows may distort lifecycle findings.
- **Privacy and review guarantees:** configuration cannot downgrade IBAN changes or duplicate IDs; IBAN masking is mandatory and duplicates always require review. Configured field values are removed from finding messages as well as value slots. Recognizable IBAN text in misplaced cells is redacted in findings, snapshots and loader diagnostics. Unexpected exception values are no longer logged. Streamlit telemetry is disabled. SQL examples fully mask short bank values.
- **Exports:** spreadsheet formula prefixes in string cells are escaped; numeric negative values remain numeric. Keyless review counts distinguish cycle and row.
- **Input/error handling:** non-finite numeric values, broken quoting and NUL bytes are rejected/reported; reserved source_row headers are rejected. Config read/encoding/non-mapping and non-finite-threshold errors are handled. CLI output-write errors produce a clean failure message. Optional AI unexpected request failures retain the template without logging input values.
- **Operator workflow:** failed runs clear stale results and downloads; changed rules invalidate old results; reset works from a demo query link. Added cycle/row columns, explicit empty/filter states and synthetic-data disclosure. Snapshot change detection uses underlying values, so identical masked IBAN displays cannot hide a change.
- **Maintainability/documentation:** generator tests write only to tmp_path. Local Ruff checks are explicitly configured rather than relying on inherited settings. Streamlit dependency floor now matches the tested API version. README describes actual configuration, payload, precision, duplicate handling and limitations; unsupported throughput/checksum claims were removed. Existing screenshots are labeled as the original layout.

## Execution evidence

| Verification | Actual result |
| --- | --- |
| Final `python -m pytest --cov=src --cov-report=term-missing` | **271 passed in 8.57s**, zero failures; **97% src statement coverage**, 921 statements / 30 missed |
| Change from baseline | 184 → 271 tests; new tests exercise behavior rather than only module presence |
| `python -m ruff check .` | All checks passed; explicit E4/E7/E9/F selection; no configured type checker |
| `python -m pip check` | No broken requirements in existing and clean virtual environments |
| Clean README setup | Created isolated venv outside repository; `pip install -r requirements.txt` exited 0. Resolved pandas 3.0.6, Streamlit 1.64.0, Pydantic 2.13.5, PyYAML 6.0.3, pytest 9.1.1 on Python 3.14.4 |
| Clean-environment suite | **269 passed in 7.51s** at that checkpoint; two additional UI/AI regression tests subsequently passed in the final 271-test run |
| Clean-environment CLI | `python -m src.engine data/demo_previous.csv data/demo_current.csv --output-dir <temporary reports>` exited 0 and wrote both CSVs |
| Export read-back | pandas successfully read **46 full findings** and **36 review findings**; every review row has requires_review=true |
| Demo summary | 200 previous / 203 current accepted rows; 1 malformed row surfaced; 4 new / 3 removed; 17 critical / 19 warning / 10 info; 23 changes; 32 records requiring review |
| IBAN export check | Compared both report byte streams against **every non-null source IBAN in both demo files**: none present in full; regression cases also cover misplaced bank values and configured name/email/department masking |
| YAML behavior | Temporary YAML actually changes salary/bonus/overtime classification, required email validation and INFO review policy; unsafe overrides fail |
| UI | AppTest covers startup/demo, filter/no-match, reset including ?demo=1, rule-change invalidation, failed reruns, duplicate candidates and masked-collision snapshots |
| Streamlit startup | Baseline and final clean-environment local server returned **HTTP 200, `ok`** from `/_stcore/health`; audit-owned processes stopped afterwards |
| SQL | All example statements execute and assertions pass, including new short-bank-value masking test |
| Git diff | Reviewed changes; `git diff --check` passes. Demo CSVs unchanged. Pre-existing untracked reports/ left untouched (6,493 / 5,122 bytes) |
| Secrets/private data | No matches for checked private-key/API-key/token patterns or tracked .env/secrets/key files; tracked CSVs are the two reproducible synthetic datasets. Both existing screenshots visually inspected: synthetic demo and masked bank values |

Manual scenario coverage now includes unchanged, all requested salary/bonus/overtime severities, dates/email validation, lifecycle and duplicate cases through real CSV loading. Exact and just-over bonus/overtime boundaries pass. The original SQL test connection added during remediation was explicitly closed after a ResourceWarning was observed; the final suite has no such warning.

## Remaining limitations and intentionally deferred work

- **No live AI provider call:** model availability, remote output quality and provider compatibility remain unverified. The existing optional path is tested with fakes, not advertised as verified live. Templates remain fully usable without credentials. AI text cannot alter classification or approve records.
- **No browser interaction/pixel sign-off of the edited UI:** AppTest and real server startup are verified; existing screenshots were inspected, not regenerated or represented as new screenshots. Real file-picker interaction and responsive layout are deferred.
- **No Python 3.12 or minimum-pandas matrix, type checker or reproducible large-file benchmark.** Runtime setup is verified on Python 3.14.4 in two dependency resolutions. Future version compatibility is not promised.
- Empty/header-only cycles remain unsupported. Malformed rows produce findings and an incomplete-input warning; lifecycle results on incomplete files require source verification. Invalid dates still generate both validation and usable-value change findings. Zero/missing salary has no meaningful bonus ratio; negative bonus has no dedicated rule. These are explicitly documented MVP semantics.
- IBAN text recognition is defensive, not a general secret-discovery guarantee. Configurable masking is field-based; arbitrary unrelated secrets pasted into arbitrary text cannot all be inferred. Secret-pattern inspection covered the current tracked tree, not an exhaustive forensic review of Git history. No real private data was identified in the reviewed artifacts.
- SQL remains educational and is not fully equivalent to the Python engine's duplicate handling, normalization and configurable policy. No database, authentication, cloud infrastructure, payroll rules or new product scope was introduced.
- A partial CLI report may remain if writing the second file fails; the CLI returns failure and states this explicitly. Export transactions are deferred rather than introducing storage machinery for this MVP.

## Final repository readiness

**YES — suitable to publish as a local MVP portfolio project with the documented limitations.** Identified P0 and P1 correctness/privacy/workflow gaps were addressed and behaviorally verified. This is not production payroll software, an autonomous decision system or a claim of deployment hardening. The initial audit, remediation and evidence remain in this file so reviewers can assess the result rather than rely on a success assertion.
