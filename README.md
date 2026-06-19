# SDA Metadata Review

Metadata quality review, compliance tracking, and a live dashboard for the
UP State Data Authority's Metadata Platform pilot.

**Live dashboard:** (https://data-analysis-assignment-8rfgemyc8qdksarcswn9zh.streamlit.app/)
---

## Folder structure

```
sda-metadata-review/
├── src/
│   ├── quality_review.py       # or .R
│   ├── compliance_analysis.py  # or .R
│   ├── dashboard.py            # or equivalent (Streamlit, Dash, etc.)
│   └── (any helper scripts)
├── data/
│   ├── metadata_submissions.csv
│   ├── compliance_tracker.csv
│   └── processed/
│       ├── quality_flags.csv
│       ├── clean_submissions.csv
│       ├── review_summary.txt
│       └── compliance_report.csv
├── outputs/
│   ├── monthly_progress_report.md  # or .docx / .pdf
│   └── followup_email_draft.md
├── README.md
└── requirements.txt
```

## Setup (fresh machine)

```bash
git clone github.com/Divyanshu51/Data-Analysis-Assignment.git
cd SDA Data Analysis Assignment
pip install -r requirements.txt
```

## Running the scripts

Run both from the repo root, in this order (Section 2 needs Section 1's output):

```bash
python src/quality_review.py
python src/compliance_analysis.py
```

`quality_review.py` reads `data/metadata_submissions.csv`, runs the 7 checks, and
writes `quality_flags.csv`, `clean_submissions.csv`, and `review_summary.txt` to
`data/processed/`. It also cross-checks the flags against `compliance_tracker.csv`
and prints a short comparison to the terminal.

`compliance_analysis.py` reads the outputs above plus `compliance_tracker.csv` and
writes `compliance_report.csv`, `issue_type_analysis.csv`, `dpdp_full_tracker.csv`,
`dpdp_gaps.csv`, and `compliance_notes.txt` to the same folder.

## Running the dashboard locally

From the repo root:

```bash
streamlit run src/dashboard.py
```

Opens at `http://localhost:8501`. It reads straight from `data/processed/`, so if
you re-run the two scripts above with new data, just refresh the browser tab.

## Deploying

Push this whole folder to a GitHub repo, then on
[streamlit.io/cloud](https://streamlit.io/cloud): New app → pick the repo → set
main file path to `src/dashboard.py` → Deploy. Takes a couple of minutes the first
time. Any push to the repo after that redeploys automatically.

---

## Approach to ambiguous data quality decisions

A few of the checks weren't spelled out exactly in the brief, so here's how I
read them and why:

- **Date format check**: I went with a strict `YYYY-MM-DD` match only. Anything
  else — `DD-MM-YYYY`, `MM/DD/YYYY`, blank — fails. I considered being lenient and
  trying to parse multiple formats, but that felt like it would hide a real data
  quality problem rather than fix it, and the whole point of this check is to
  catch departments submitting in the wrong format.

- **Record count and live APIs**: the brief says blank record count is acceptable
  "only if the dataset is a live API." I implemented this by checking the
  `formats` column for the literal value `API` (case-insensitive, comma-split).
  If a department lists `CSV, API` they pass; if they list just `CSV` and leave
  record count blank, they fail. This felt like the most literal, defensible
  reading of the rule.

- **DPDP consistency check**: this only fires when `dpdp_personal_data = Yes`.
  If that field is blank or "No", I don't touch the classification at all — the
  brief only ties DPDP and classification together when personal data is
  confirmed present, so I didn't want to penalize submissions for an
  inconsistency that wasn't actually flagged.

- **Record count as text vs number**: a few entries had record counts that
  weren't cleanly numeric (extra characters, decimals). I cast to float first
  then int, so "1200.0" passes but anything genuinely non-numeric fails as
  "Record count not numeric" rather than crashing the script.

## Assumptions about what counts as a valid entry

- A description needs at least 20 characters to count as "adequate" — this
  isn't stated explicitly as a hard number anywhere except the brief, so I took
  it at face value rather than picking my own threshold.
- Classification has to be exactly one of `Public`, `Restricted`, `Confidential`
  — no partial matches, no case-insensitivity. If a department typed
  "restricted" in lowercase, that fails. I considered being case-insensitive
  here but decided strict matching is safer for a compliance check; better to
  flag a typo and have a human confirm it than silently accept it.
- "Missing data owner" treats both an empty cell and a cell with only
  whitespace as missing, not just a true blank.
- For the 7-day non-response check in Section 2, I'm comparing
  `follow_up_date` against today's date, not against `submitted_on`. The brief
  asks specifically about non-response *after a follow-up*, so the clock starts
  when the follow-up went out, not when the submission first came in.

## What I'd improve with more time

- The DPDP non-response check and the 7-day staleness check are both date-driven
  off "today," so the dashboard's numbers shift every time someone runs it later.
  For a real production version I'd snapshot a fixed "as of" date per report
  rather than recalculating live, so historical reports stay stable.
- Right now department names have to match exactly between
  `metadata_submissions.csv` and `compliance_tracker.csv` for the merge to work.
  A fuzzy-match or a lookup table would make this more robust against typos.
- The dashboard doesn't have any drill-down from the department table down to
  individual `submission_id` rows — useful next step so the Lead can click a
  department and see exactly which submissions are stuck and why.
- I'd add a basic test file for the 7 quality checks in `quality_review.py`,
  since right now correctness is verified by eyeballing the output rather than
  by an actual test suite.
- Email/Slack alerts when a submission crosses the 7-day no-response mark,
  instead of someone having to open the dashboard to notice.
