-- Values in the current cycle that look wrong on their own.
--
-- Table: employees_current (same columns as the CSV export).
-- Thresholds are inline for readability; the Python engine reads them from
-- rules/validation_rules.yaml.

-- 1. Missing required fields, one row per missing field.
SELECT employee_id, 'first_name' AS missing_field FROM employees_current WHERE first_name IS NULL OR first_name = ''
UNION ALL
SELECT employee_id, 'last_name'      FROM employees_current WHERE last_name IS NULL OR last_name = ''
UNION ALL
SELECT employee_id, 'contract_type'  FROM employees_current WHERE contract_type IS NULL OR contract_type = ''
UNION ALL
SELECT employee_id, 'monthly_salary' FROM employees_current WHERE monthly_salary IS NULL OR monthly_salary = ''
ORDER BY employee_id, missing_field;

-- 2. Bonus unusually high compared with monthly salary.
SELECT
    employee_id,
    monthly_salary,
    bonus,
    ROUND(bonus * 100.0 / monthly_salary, 1) AS bonus_pct_of_salary,
    CASE
        WHEN bonus > monthly_salary * 1.0 THEN 'critical'
        WHEN bonus > monthly_salary * 0.5 THEN 'warning'
    END AS severity
FROM employees_current
WHERE monthly_salary > 0 AND bonus > monthly_salary * 0.5
ORDER BY bonus_pct_of_salary DESC;

-- 3. Overtime outside the plausible range.
SELECT
    employee_id,
    overtime_hours,
    CASE
        WHEN overtime_hours < 0   THEN 'critical'
        WHEN overtime_hours > 100 THEN 'critical'
        WHEN overtime_hours > 60  THEN 'warning'
    END AS severity
FROM employees_current
WHERE overtime_hours < 0 OR overtime_hours > 60
ORDER BY overtime_hours DESC;

-- 4. Impossible values: negative salary, end before start, malformed email.
SELECT employee_id, 'negative_salary' AS problem, CAST(monthly_salary AS TEXT) AS value
FROM employees_current
WHERE monthly_salary < 0
UNION ALL
SELECT employee_id, 'end_before_start', end_date
FROM employees_current
WHERE end_date <> '' AND start_date <> '' AND end_date < start_date
UNION ALL
SELECT employee_id, 'malformed_email', email
FROM employees_current
WHERE email <> '' AND email NOT LIKE '%_@_%.__%'
ORDER BY employee_id;
