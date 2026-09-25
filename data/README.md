# Demo datasets (synthetic)

**Everything in this folder is invented.** Names are drawn from short lists,
emails use the reserved `example.com` domain and IBANs are random digits
without valid check digits. No real person or organisation is represented.

The files are produced by `scripts/generate_demo_data.py` with a fixed seed,
so regenerating them gives identical output.

| File | Rows | Content |
|---|---|---|
| `demo_previous.csv` | 200 | A clean export of the previous cycle. |
| `demo_current.csv` | 203 + 1 broken line | The same population one cycle later, with the changes below injected. |

## What the current cycle contains

Lifecycle

- 3 removed records: `EMP-00017`, `EMP-00088`, `EMP-00143`
- 4 new records: `EMP-00201` to `EMP-00204`; `EMP-00203` is missing `contract_type`
- 2 leavers with an `end_date` added: `EMP-00045`, `EMP-00172`
- 1 corrected `start_date`: `EMP-00102`

Salary

- Within tolerance: `EMP-00005` (+3%), `EMP-00042` (+8%), `EMP-00061` (+12%), `EMP-00112` (-10%)
- Warnings: `EMP-00077` (+18%), `EMP-00099` (+22%)
- Critical: `EMP-00136` (-35%), `EMP-00125` (2,100 to 3,000, +42.86%), `EMP-00150` (2,800 to 28,000, a typo-like +900%)

Sensitive fields

- IBAN changed: `EMP-00023`, `EMP-00158`

Duplicates and missing data

- `EMP-00064` appears twice with two different salaries
- `EMP-00183` reuses the email of `EMP-00019`
- `EMP-00071` has no `last_name`; `EMP-00093` has no `monthly_salary`
- One row has an empty `employee_id`

Contract changes

- `EMP-00034`: part-time to full-time, hours and salary adjusted
- `EMP-00147`: contract type changed to fixed-term
- `EMP-00108`: working hours 40 to 32
- `EMP-00012`, `EMP-00119`: department changed

Anomalies and invalid values

- Overtime: `EMP-00050` (72 h), `EMP-00081` (110 h), `EMP-00164` (-5 h)
- Bonus: `EMP-00029` (60% of salary), `EMP-00176` (150% of salary)
- `EMP-00131` has the impossible date `2024-02-30`
- `EMP-00188` has an `end_date` earlier than its `start_date`
- `EMP-00056` has a malformed email
- The last line of the file has one field too many and is skipped by the loader
