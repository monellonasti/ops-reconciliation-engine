"""English texts: the reference catalog. Keys are stable identifiers; placeholders use str.format."""

MESSAGES: dict[str, str | tuple[str, ...]] = {
    # --- labels ---------------------------------------------------------------------
    "category.lifecycle": "Lifecycle",
    "category.duplicate": "Duplicate",
    "category.missing_data": "Missing data",
    "category.invalid_value": "Invalid value",
    "category.salary_change": "Salary change",
    "category.iban_change": "IBAN change",
    "category.contract_change": "Contract change",
    "category.bonus_anomaly": "Bonus anomaly",
    "category.overtime_anomaly": "Overtime anomaly",
    "category.expected_change": "Expected change",
    "severity.info": "Info",
    "severity.warning": "Warning",
    "severity.critical": "Critical",
    "status.open": "Open",
    "status.accepted": "Accepted",
    "status.needs_action": "Needs action",
    "record.row": "row {line}",
    "record.unknown": "unknown record",
    "value.empty": "empty",
    "dataset.previous": "previous",
    "dataset.current": "current",
    "dataset.both": "both",
    # --- loader ---------------------------------------------------------------------
    "loader.empty": "The file is empty.",
    "loader.nul": "The file contains NUL characters. Save it as UTF-8 CSV and retry.",
    "loader.not_utf8": "File was not UTF-8; decoded as {encoding}.",
    "loader.not_found": "File not found: {name}",
    "loader.unreadable": "Could not read {name}: {error}",
    "loader.encoding": "The file encoding is not supported. Save it as UTF-8 and retry.",
    "loader.no_header": "The file has no header row.",
    "loader.parse_error": "The file could not be parsed as CSV: {error}",
    "loader.parse_error_near": "The file could not be parsed as CSV near line {line}: {error}",
    "loader.no_rows": "The file has a header but no data rows.",
    "loader.reserved_header": "Header contains reserved column source_row; rename it before uploading.",
    "loader.unnamed_columns": "Header has unnamed column(s) at position {positions}.",
    "loader.duplicate_columns": "Duplicate column name(s): {names}.",
    "loader.malformed_row": "Row {line} has {found} fields, expected {expected}; the row was skipped.",
    "loader.missing_required_columns": "Missing required column(s): {missing}. Found: {found}.",
    "loader.optional_missing": "Optional column(s) not present, related checks skipped: {columns}",
    "loader.extra_columns": "Column(s) not used by any rule: {columns}",
    "loader.excel_sheet": "Excel workbook: read the first sheet '{sheet}' ({count} sheets in the file).",
    "loader.excel_error": "The Excel file could not be read. Save it as .xlsx or CSV and retry.",
    # --- validators -----------------------------------------------------------------
    "validators.invalid_number": "{column} has an invalid or non-finite numeric value.",
    "validators.invalid_date": "{column} '{value}' is not a valid date (expected format {formats}).",
    "validators.missing_key": (
        "Required field employee_id is empty; the record cannot be matched across cycles."
    ),
    "validators.missing_field": "Required field {column} is empty.",
    "validators.duplicate_key": "employee_id {key} appears {count} times (rows {rows}).",
    "validators.duplicate_value": "{column} is shared with {others}.",
    "validators.negative_salary": "monthly_salary is negative.",
    "validators.end_before_start": "end_date {end} is earlier than start_date {start}.",
    "validators.malformed_email": "email '{email}' does not look like a valid address.",
    # --- reconciliation -------------------------------------------------------------
    "recon.new_record": "New record{name}: not present in the previous cycle.",
    "recon.removed_record": "Record removed{name}: present in the previous cycle only.",
    "recon.salary_set": "Monthly salary set to {current}; no previous value to compare.",
    "recon.salary_from_zero": "Monthly salary changed from 0 to {current}; percentage not meaningful.",
    "recon.salary_increased": "Monthly salary increased by {pct}% (from {previous} to {current}).",
    "recon.salary_decreased": "Monthly salary decreased by {pct}% (from {previous} to {current}).",
    "recon.iban_added": "IBAN added ({current}); no IBAN in the previous cycle.",
    "recon.iban_removed": "IBAN removed (was {previous}).",
    "recon.iban_changed": "IBAN changed from {previous} to {current}.",
    "recon.field_changed": "{field} changed from {previous} to {current}.",
    "recon.end_date_added": "end_date added: {current}.",
    # --- anomalies ------------------------------------------------------------------
    "anomaly.bonus": "Bonus {bonus} is {ratio}% of monthly salary {salary} (threshold {threshold}).",
    "anomaly.overtime_negative": "Overtime hours are negative ({hours}).",
    "anomaly.overtime_below": "Overtime of {hours} hours is below the {minimum}-hour minimum.",
    "anomaly.overtime_exceeds": "Overtime of {hours} hours exceeds the {limit}-hour threshold.",
    # --- expected changes -----------------------------------------------------------
    "expected.matches": "Matches expected change ({reference}).",
    "expected.iban_reviewed": "IBAN changes are always reviewed.",
    "expected.differs": "Differs from the expected value {expected} ({reference}).",
    "expected.row_label": "expected changes row {line}",
    "expected.missing.new_existed": (
        "Expected {key} as a new record ({reference}) but it already existed in the previous cycle."
    ),
    "expected.missing.new_absent": (
        "Expected {key} as a new record ({reference}) but it is not present in the current cycle."
    ),
    "expected.missing.removed_present": (
        "Expected {key} to be removed ({reference}) but it is still present in the current cycle."
    ),
    "expected.missing.removed_absent": (
        "Expected {key} to be removed ({reference}) but it was not present in the previous cycle either."
    ),
    "expected.missing.head": "Expected {field} to become {expected} ({reference})",
    "expected.missing.neither": "{head} but the record is not present in either cycle.",
    "expected.missing.absent": "{head} but the record is absent from the current cycle.",
    "expected.missing.current": "{head} but the current value is {current}.",
    "expected.load.missing_columns": (
        "Expected changes file: missing column(s) {missing}. Required: {required}; optional: reference."
    ),
    "expected.load.bad_rows": "Expected changes file: row(s) {lines} have the wrong number of fields.",
    "expected.load.problems": "Expected changes file: {problems}.",
    "expected.load.more": "; and {count} more",
    "expected.load.empty_id": "row {line}: employee_id is empty",
    "expected.load.bad_field": "row {line}: field '{field}' is not one of {allowed}",
    "expected.load.value_required": "row {line}: expected_value is required for {field}",
    "expected.load.value_forbidden": "row {line}: expected_value must be empty for {field}",
    "expected.load.duplicate": "row {line}: {key} / {field} is listed more than once",
    # --- engine notes and CLI -------------------------------------------------------
    "note.rows_skipped": (
        "Some rows were skipped. Lifecycle findings may reflect incomplete exports; verify the source files."
    ),
    "note.duplicates_excluded": (
        "Duplicate employee IDs were excluded from cross-cycle comparison in both cycles; "
        "review all candidate rows at source."
    ),
    "note.expected": (
        "Expected changes: {listed} listed, {matched} matched (downgraded to info unless IBAN), "
        "{mismatched} applied with a different value, {missing} not found."
    ),
    "history.unavailable": (
        "The review history file ({path}) could not be read or written. Decisions are not shown or "
        "saved until the file is repaired, moved or removed."
    ),
    "history.busy": "The review history file ({path}) is busy with another save. Try again in a moment.",
    "cli.records": "Records processed: {current} (previous cycle: {previous})",
    "cli.counts": "New: {new}  Removed: {removed}  Changes: {changes}",
    "cli.severities": "Critical: {critical}  Warnings: {warnings}  Info: {info}",
    "cli.review": "Records requiring review: {count}",
    "cli.note": "Note: {note}",
    "cli.decided": (
        "Findings with a stored decision: {decided} ({accepted} accepted, {needs_action} need action)"
    ),
    "cli.written": "Reports written to {path}",
    "cli.error": "Error: {error}",
    "cli.write_error": (
        "Error: Could not write both reports. Check the output directory and permissions; "
        "a partial report may exist."
    ),
    # --- explanations ---------------------------------------------------------------
    "explain.text": (
        "What changed: {what}\nWhy it was flagged: {why}\nRule triggered: {rule}\nSuggested checks:\n{actions}"
    ),
    "explain.salary.why_no_pct": (
        "The previous value was zero or missing, so a percentage cannot be computed. "
        "Any change from an empty baseline is surfaced for a human to confirm."
    ),
    "explain.salary.why_critical": (
        "A {pct}% change exceeds the configured {critical}% critical threshold."
    ),
    "explain.salary.why_warning": (
        "A {pct}% change exceeds the {warning}% warning threshold "
        "but does not exceed the {critical}% critical threshold."
    ),
    "explain.salary.why_info": (
        "A {pct}% change is within the {warning}% tolerance; listed for completeness."
    ),
    "explain.salary.rule": "salary_change (warning above {warning}%, critical above {critical}%)",
    "explain.salary.actions_info": ("No action required unless the change is unexpected for this employee.",),
    "explain.salary.actions": (
        "Verify whether a contractual change was approved and by whom.",
        "Verify the effective date of the change.",
        "Determine whether the change is permanent or a one-off adjustment.",
    ),
    "explain.iban.why": (
        "Bank details are a sensitive field. The engine treats every IBAN change as {severity} "
        "and never decides on its own whether it is legitimate."
    ),
    "explain.iban.rule": "iban_change (severity {severity}, requires review: {review})",
    "explain.iban.actions": (
        "Confirm the change request came through the approved channel and matches a signed instruction.",
        "Verify the account holder of the new IBAN is the employee.",
        "Check whether the previous IBAN was used in the last cycle and whether a payment is pending.",
    ),
    "explain.new.why": "The employee_id does not exist in the previous cycle.",
    "explain.new.rule": "lifecycle.new_record (severity {severity})",
    "explain.new.actions": (
        "Confirm onboarding is complete in the source system.",
        "Check the record is not an existing employee re-entered under a new ID.",
    ),
    "explain.removed.why": "The employee_id exists in the previous cycle but not in the current export.",
    "explain.removed.rule": "lifecycle.removed_record (severity {severity})",
    "explain.removed.actions": (
        "Confirm the leaver was processed and an end date was recorded in the source system.",
        "Check whether the record was dropped by an export filter rather than a real exit.",
    ),
    "explain.date.why": "Employment dates drive eligibility and timing; a change is surfaced for confirmation.",
    "explain.date.rule": "lifecycle.{rule} (severity {severity})",
    "explain.date.actions": (
        "Confirm the new date against the signed contract or termination notice.",
        "Check whether related fields (contract type, hours, salary) should have changed too.",
    ),
    "explain.contract.why": "{field} differs between the two cycles.",
    "explain.contract.rule": "contract_changes.{field} (severity {severity})",
    "explain.contract.actions.contract_type": (
        "Confirm the contract amendment was signed and its effective date.",
        "Check that working hours and salary are consistent with the new contract type.",
    ),
    "explain.contract.actions.working_hours": (
        "Confirm the change in hours was agreed and from which date.",
        "Check whether the salary was adjusted proportionally.",
    ),
    "explain.contract.actions.department": (
        "Confirm the transfer with the receiving manager.",
        "Check cost-centre or approval mappings that depend on the department.",
    ),
    "explain.duplicate.key_why": (
        "The record key must be unique; two rows with the same ID cannot be matched reliably."
    ),
    "explain.duplicate.key_actions": (
        "Identify which row is authoritative and remove or merge the other at source.",
        "Check whether the export joined a table that produced multiple rows per employee.",
    ),
    "explain.duplicate.value_why": (
        "Two different records share the same {field}, which usually indicates a data-entry or export error."
    ),
    "explain.duplicate.value_action": "Check which employee the {field} really belongs to and correct the other record.",
    "explain.duplicate.value_action_2": "Confirm the two records are not the same person entered twice.",
    "explain.duplicate.rule": "duplicates.{field} (severity {severity})",
    "explain.missing.why": "{field} is listed in required_fields; the record cannot be processed without it.",
    "explain.missing.rule": "required_fields / missing_data (severity {severity})",
    "explain.missing.actions": (
        "Obtain the missing value from the source system and re-export.",
        "Decide whether the record can be processed this cycle without it.",
    ),
    "explain.invalid.invalid_number": "The value could not be read as a number.",
    "explain.invalid.invalid_date": "The value is not a real date in the expected format ({formats}).",
    "explain.invalid.negative_salary": "A monthly salary cannot be negative.",
    "explain.invalid.end_before_start": "An employment cannot end before it starts.",
    "explain.invalid.malformed_email": "The email address does not follow the expected pattern.",
    "explain.invalid.malformed_row": (
        "The line has a different number of fields than the header, so it could not be read."
    ),
    "explain.invalid.fallback": "The value cannot be right.",
    "explain.invalid.rule": "invalid_values.{rule} (severity {severity})",
    "explain.invalid.actions": (
        "Correct the value in the source system and re-export.",
        "Check whether the same error affects other rows of the export.",
    ),
    "explain.bonus.why": (
        "Bonuses above {warning} of monthly salary are warnings and above {critical} are critical."
    ),
    "explain.bonus.rule": "bonus (warning ratio {warning_ratio}, critical ratio {critical_ratio})",
    "explain.bonus.actions": (
        "Confirm the bonus amount was approved for this cycle.",
        "Check for unit mistakes, for example an annual amount entered as monthly.",
    ),
    "explain.overtime.why_below": "Overtime is below the configured minimum of {minimum} hours.",
    "explain.overtime.why_above": (
        "Overtime above {warning} hours is a warning and above {critical} hours is critical."
    ),
    "explain.overtime.rule": (
        "overtime (minimum {minimum}, warning above {warning}, critical above {critical})"
    ),
    "explain.overtime.actions": (
        "Verify the hours against the timesheet or time-tracking system.",
        "Check for data-entry errors such as a wrong sign or a misplaced digit.",
    ),
    "explain.generic.why": "Rule {rule} fired with severity {severity}.",
    "explain.generic.actions": ("Review the record against the source system.",),
    "explain.expected_missing.why": (
        "The expected changes file lists an approved change for this record that is not "
        "reflected in the current cycle."
    ),
    "explain.expected_missing.rule": "expected_changes.missing (severity {severity})",
    "explain.expected_missing.actions": (
        "Check whether the change was applied in the source system after the export was taken.",
        "Check whether the approval was withdrawn or postponed; update the expected changes file.",
    ),
    "explain.expectation.iban_why": (
        "{why} This change is listed as expected ({reference}); IBAN changes are still confirmed by a person."
    ),
    "explain.expectation.iban_actions": (
        "Confirm the approval reference is genuine and refers to this employee.",
        "Verify the new account holder before the next payment run.",
    ),
    "explain.expectation.matched_why": (
        "Listed as an expected change ({reference}) and the applied value matches, "
        "so the severity was lowered to info. Without the expectation: {why}"
    ),
    "explain.expectation.matched_actions": ("No action needed unless the approval record itself is wrong.",),
    "explain.expectation.mismatch_why": (
        "{why} A change was expected for this field, but to {expected}, not to the value that was applied."
    ),
    "explain.expectation.mismatch_action": (
        "Compare the applied value with the approval record and find out which one is wrong."
    ),
    # --- optional AI ------------------------------------------------------------------
    "ai.unavailable_setup": "AI explanation unavailable: set ANTHROPIC_API_KEY and install the anthropic package.",
    "ai.unavailable_key": "AI explanation unavailable: the API key was rejected.",
    "ai.unavailable_rate": "AI explanation unavailable: rate limited, try again in a moment.",
    "ai.unavailable_status": "AI explanation unavailable: the API returned status {status}.",
    "ai.unavailable_network": "AI explanation unavailable: could not reach the API.",
    "ai.unavailable_failed": "AI explanation unavailable: the request failed; the template explanation applies.",
    "ai.unavailable_refusal": "AI explanation unavailable for this finding; the template explanation applies.",
    "ai.unavailable_empty": "AI explanation unavailable: the model returned no text.",
    "ai.unavailable_truncated": "AI explanation unavailable: the answer was cut off; the template explanation applies.",
    "ai.language_instruction": "Write in English.",
    # --- UI ---------------------------------------------------------------------------
    "ui.subtitle": "Automate deterministic checks. Surface exceptions. Keep humans in control.",
    "ui.rules_error": "The rules file could not be loaded: {error}",
    "ui.rules_changed": "Rules changed. Run reconciliation again to apply them.",
    "ui.start_hint": "Upload the previous and current cycle exports, or load the demo dataset, to start.",
    "ui.demo_notice": "Synthetic demo data. No real people or bank accounts are represented.",
    "ui.comparing": "**Comparing** `{previous}` (previous) **with** `{current}` (current)",
    "ui.expected_entries": "Expected changes: {count} entries from `{name}`.",
    "ui.note": "Note: {note}",
    "ui.sidebar.rules": "Rules in effect",
    "ui.sidebar.loaded_from": "Loaded from `{path}`",
    "ui.sidebar.language": "Language",
    "ui.sidebar.rule": "Rule",
    "ui.sidebar.value": "Value",
    "ui.sidebar.salary_warning": "Salary change: warning above",
    "ui.sidebar.salary_critical": "Salary change: critical above",
    "ui.sidebar.bonus_warning": "Bonus: warning above",
    "ui.sidebar.bonus_critical": "Bonus: critical above",
    "ui.sidebar.of_salary": "{value} of salary",
    "ui.sidebar.overtime_warning": "Overtime: warning above",
    "ui.sidebar.overtime_critical": "Overtime: critical above",
    "ui.sidebar.iban_change": "IBAN change",
    "ui.sidebar.duplicate_id": "Duplicate employee_id",
    "ui.sidebar.required_fields": "Required fields: {fields}",
    "ui.sidebar.masked_fields": "Masked in the UI and exports: {fields}",
    "ui.sidebar.formats": "Input formats: dates {dates}; decimal separator '{decimal}'; thousands separator '{thousands}'.",
    "ui.sidebar.history": "Review history",
    "ui.sidebar.history_disabled": "Disabled in the rules file. Decisions are not stored between runs.",
    "ui.sidebar.history_enabled": (
        "Decisions are saved to `{path}` ({count} stored). A finding keeps its decision when it comes back "
        "in a later cycle with the same values."
    ),
    "ui.sidebar.privacy": "Privacy",
    "ui.sidebar.privacy_text": (
        "Files are processed in memory for this session only. Nothing is stored on disk "
        "except the review decisions you save, and no external service is called unless "
        "you explicitly request an AI explanation."
    ),
    "ui.sidebar.reset": "Reset session",
    "ui.inputs.title": "1. Choose the two cycles",
    "ui.inputs.previous": "Previous cycle (CSV or Excel)",
    "ui.inputs.current": "Current cycle (CSV or Excel)",
    "ui.inputs.expected": "Expected changes (optional, CSV or Excel)",
    "ui.inputs.expected_help": (
        "Columns: employee_id, field, expected_value, reference (optional). field is one of {fields}. "
        "A change that matches an entry is downgraded to info (IBAN changes excepted); "
        "an entry that did not happen becomes a finding."
    ),
    "ui.inputs.run": "Run reconciliation",
    "ui.inputs.demo": "Load demo dataset",
    "ui.inputs.running": "Reconciling the files...",
    "ui.error.previous": "Previous cycle ({name}): {error}",
    "ui.error.current": "Current cycle ({name}): {error}",
    "ui.error.expected": "Expected changes ({name}): {error}",
    "ui.error.unexpected": (
        "Something went wrong while reconciling the files. Check that both files are valid "
        "CSV exports with the expected columns, then try again."
    ),
    "ui.summary.title": "2. Summary",
    "ui.summary.records": "Records processed",
    "ui.summary.records_help": "{count} in previous cycle",
    "ui.summary.new": "New records",
    "ui.summary.removed": "Removed records",
    "ui.summary.critical": "Critical issues",
    "ui.summary.warnings": "Warnings",
    "ui.summary.changes": "Changes detected",
    "ui.summary.review": "Records requiring review",
    "ui.summary.decided": (
        "Findings with a recorded decision: {decided} ({accepted} accepted, excluded from the review "
        "count; {needs_action} needing action)."
    ),
    "ui.queue.title": "3. Review queue",
    "ui.queue.severity": "Severity",
    "ui.queue.category": "Category",
    "ui.queue.review_required": "Review required",
    "ui.queue.review_all": "All issues",
    "ui.queue.review_yes": "Review required",
    "ui.queue.review_no": "No review needed",
    "ui.queue.status": "Review status",
    "ui.queue.search": "Employee ID contains",
    "ui.queue.shown": "{shown} of {total} issues shown. Tick the box at the left of a row to see its details.",
    "ui.queue.none": "No findings detected by the configured checks.",
    "ui.queue.no_match": "No findings match these filters.",
    "ui.column.employee": "Employee ID",
    "ui.column.cycle": "Cycle",
    "ui.column.source_row": "Source row",
    "ui.column.category": "Category",
    "ui.column.field": "Field",
    "ui.column.previous": "Previous",
    "ui.column.current": "Current",
    "ui.column.change": "Change",
    "ui.column.severity": "Severity",
    "ui.column.review_required": "Review Required",
    "ui.column.status": "Status",
    "ui.column.expected": "Expected",
    "ui.column.explanation": "Explanation",
    "ui.column.changed": "Changed",
    "ui.yes": "Yes",
    "ui.no": "No",
    "ui.expected.matches": "matches: {reference}",
    "ui.expected.not_applied": "not applied",
    "ui.expected.differs": "differs, expected {expected}",
    "ui.detail.title": "4. Issue detail",
    "ui.detail.hint": "Tick a row in the review queue to see what changed, why it was flagged and what to check.",
    "ui.detail.header": "**{record}** · {category} · {severity} · Review required: **{review}**",
    "ui.detail.what": "**What changed**",
    "ui.detail.why": "**Why it was flagged**",
    "ui.detail.rule": "**Rule triggered**",
    "ui.detail.actions": "**Suggested operator action**",
    "ui.detail.disclaimer": (
        "The engine detects; it does not decide. Confirm the change with the source of truth before acting on it."
    ),
    "ui.detail.snapshot": "Record snapshot (both cycles)",
    "ui.detail.not_compared": "not compared",
    "ui.detail.changed_yes": "yes",
    "ui.decision.title": "**Review decision**",
    "ui.decision.disabled": "Review history is disabled in the rules file, so decisions are not stored.",
    "ui.decision.current": "Current decision: {status}{who} on {when}.{note}",
    "ui.decision.by": " by {reviewer}",
    "ui.decision.note_suffix": " Note: {note}",
    "ui.decision.status": "Status",
    "ui.decision.note": "Note (optional)",
    "ui.decision.reviewer": "Reviewer (optional)",
    "ui.decision.save": "Save decision",
    "ui.decision.help": (
        "Accepted: verified, leaves the open queue and stays accepted if the same finding returns "
        "with the same values. Needs action: known problem, stays in the queue until corrected. "
        "Open: no decision yet."
    ),
    "ui.decision.saved": "Decision saved for {record}: {status}.",
    "ui.ai.title": "**Optional: explain with AI**",
    "ui.ai.not_configured": (
        "Not configured. Set `ANTHROPIC_API_KEY` and install the `anthropic` package to enable "
        "a natural-language rewrite of this finding. The application does not need it."
    ),
    "ui.ai.button": "Explain this finding",
    "ui.ai.spinner": "Asking the model to rephrase the finding...",
    "ui.ai.disclaimer": (
        "Generated text. It rephrases the deterministic finding and does not judge whether the change is correct."
    ),
    "ui.export.title": "5. Export",
    "ui.export.full": "Download Full Report",
    "ui.export.queue": "Download Review Queue",
    "ui.export.caption": (
        "Full report: {total} issues with their review status. "
        "Review queue: {queue} issues flagged for a human decision and not yet accepted."
    ),
}
