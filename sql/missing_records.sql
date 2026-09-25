-- Records that exist in one cycle but not the other.
--
-- Tables: employees_previous, employees_current (same columns as the CSV exports).

-- 1. New records: present now, absent in the previous cycle.
SELECT
    c.employee_id,
    c.first_name,
    c.last_name,
    c.department,
    c.start_date
FROM employees_current AS c
LEFT JOIN employees_previous AS p ON p.employee_id = c.employee_id
WHERE p.employee_id IS NULL
  AND c.employee_id IS NOT NULL AND c.employee_id <> ''
ORDER BY c.employee_id;

-- 2. Removed records: present before, absent now.
SELECT
    p.employee_id,
    p.first_name,
    p.last_name,
    p.department,
    p.end_date AS end_date_in_previous_cycle
FROM employees_previous AS p
LEFT JOIN employees_current AS c ON c.employee_id = p.employee_id
WHERE c.employee_id IS NULL
ORDER BY p.employee_id;

-- 3. Records that cannot be matched at all because the key is missing.
SELECT
    ROWID       AS source_row,
    first_name,
    last_name,
    email
FROM employees_current
WHERE employee_id IS NULL OR employee_id = '';
