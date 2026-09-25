-- Field-level changes between two cycles for records present in both.
--
-- Tables: employees_previous, employees_current (same columns as the CSV exports).
-- Thresholds (15% / 30%) are written inline here for readability; the Python
-- engine reads the same values from rules/validation_rules.yaml.

-- 1. Salary changes with the percentage difference and a severity band.
SELECT
    p.employee_id,
    p.monthly_salary                                   AS previous_salary,
    c.monthly_salary                                   AS current_salary,
    ROUND((c.monthly_salary - p.monthly_salary) * 100.0 / p.monthly_salary, 2) AS change_pct,
    CASE
        WHEN ABS((c.monthly_salary - p.monthly_salary) * 100.0 / p.monthly_salary) > 30 THEN 'critical'
        WHEN ABS((c.monthly_salary - p.monthly_salary) * 100.0 / p.monthly_salary) > 15 THEN 'warning'
        ELSE 'info'
    END AS severity
FROM employees_previous AS p
JOIN employees_current  AS c ON c.employee_id = p.employee_id
WHERE p.monthly_salary IS NOT NULL AND p.monthly_salary <> 0
  AND c.monthly_salary IS NOT NULL
  AND c.monthly_salary <> p.monthly_salary
ORDER BY ABS(change_pct) DESC;

-- 2. Every change to contract-related fields, one row per changed field.
SELECT employee_id, 'contract_type' AS field, p_value AS previous_value, c_value AS current_value
FROM (
    SELECT p.employee_id, p.contract_type AS p_value, c.contract_type AS c_value
    FROM employees_previous p JOIN employees_current c ON c.employee_id = p.employee_id
) WHERE COALESCE(LOWER(p_value), '') <> COALESCE(LOWER(c_value), '')
UNION ALL
SELECT employee_id, 'working_hours', p_value, c_value
FROM (
    SELECT p.employee_id, p.working_hours AS p_value, c.working_hours AS c_value
    FROM employees_previous p JOIN employees_current c ON c.employee_id = p.employee_id
) WHERE COALESCE(p_value, -1) <> COALESCE(c_value, -1)
UNION ALL
SELECT employee_id, 'department', p_value, c_value
FROM (
    SELECT p.employee_id, p.department AS p_value, c.department AS c_value
    FROM employees_previous p JOIN employees_current c ON c.employee_id = p.employee_id
) WHERE COALESCE(LOWER(p_value), '') <> COALESCE(LOWER(c_value), '')
ORDER BY employee_id, field;

-- 3. IBAN changes. Only masked values are returned.
SELECT
    p.employee_id,
    CASE WHEN p.iban IS NULL OR p.iban = '' THEN NULL
         WHEN LENGTH(REPLACE(p.iban, ' ', '')) < 12 THEN '****'
         ELSE SUBSTR(REPLACE(UPPER(p.iban), ' ', ''), 1, 5) || '****' || SUBSTR(REPLACE(UPPER(p.iban), ' ', ''), -4) END AS previous_iban_masked,
    CASE WHEN c.iban IS NULL OR c.iban = '' THEN NULL
         WHEN LENGTH(REPLACE(c.iban, ' ', '')) < 12 THEN '****'
         ELSE SUBSTR(REPLACE(UPPER(c.iban), ' ', ''), 1, 5) || '****' || SUBSTR(REPLACE(UPPER(c.iban), ' ', ''), -4) END AS current_iban_masked
FROM employees_previous AS p
JOIN employees_current  AS c ON c.employee_id = p.employee_id
WHERE COALESCE(REPLACE(UPPER(p.iban), ' ', ''), '') <> COALESCE(REPLACE(UPPER(c.iban), ' ', ''), '');

-- 4. Leavers: an end_date that appeared this cycle.
SELECT p.employee_id, c.end_date
FROM employees_previous AS p
JOIN employees_current  AS c ON c.employee_id = p.employee_id
WHERE (p.end_date IS NULL OR p.end_date = '')
  AND c.end_date IS NOT NULL AND c.end_date <> '';
