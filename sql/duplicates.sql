-- Duplicate detection within one cycle.
--
-- Assumes two tables with the same columns as the CSV exports:
--   employees_previous, employees_current
-- The queries are plain SQLite/PostgreSQL SQL; tests/test_sql.py runs them
-- against the demo data in an in-memory SQLite database.

-- 1. employee_id exported more than once (critical: the key must be unique).
SELECT
    employee_id,
    COUNT(*)                          AS occurrences,
    GROUP_CONCAT(monthly_salary, ' | ') AS salaries_seen
FROM employees_current
WHERE employee_id IS NOT NULL AND employee_id <> ''
GROUP BY employee_id
HAVING COUNT(*) > 1;

-- 2. The same email on two different employees (case-insensitive).
SELECT
    LOWER(TRIM(email))          AS email_normalized,
    COUNT(DISTINCT employee_id) AS employees,
    GROUP_CONCAT(DISTINCT employee_id) AS employee_ids
FROM employees_current
WHERE email IS NOT NULL AND email <> ''
GROUP BY LOWER(TRIM(email))
HAVING COUNT(DISTINCT employee_id) > 1;

-- 3. The same IBAN on two different employees. Only a masked form is selected,
--    so the result can be shared without exposing full bank details.
SELECT
    CASE WHEN LENGTH(REPLACE(iban, ' ', '')) < 12 THEN '****'
         ELSE SUBSTR(REPLACE(UPPER(iban), ' ', ''), 1, 5) || '****' ||
              SUBSTR(REPLACE(UPPER(iban), ' ', ''), -4) END AS iban_masked,
    COUNT(DISTINCT employee_id)                        AS employees,
    GROUP_CONCAT(DISTINCT employee_id)                 AS employee_ids
FROM employees_current
WHERE iban IS NOT NULL AND iban <> ''
GROUP BY REPLACE(UPPER(iban), ' ', '')
HAVING COUNT(DISTINCT employee_id) > 1;
