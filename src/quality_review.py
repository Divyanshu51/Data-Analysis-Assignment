"""
Section 1 - Metadata Quality Review

Runs the 7 quality checks from the SDA checklist against metadata_submissions.csv,
then cross-checks the results against compliance_tracker.csv.

Outputs (written to data/processed/):
    quality_flags.csv      - submissions failing 1+ checks, with an issues column
    clean_submissions.csv  - submissions passing all checks
    review_summary.txt     - quick data quality report
"""

import pandas as pd
from datetime import datetime
from collections import Counter
import os

DATA_DIR = "data"
OUT_DIR = "data/processed"

VALID_CLASSIFICATIONS = {"Public", "Restricted", "Confidential"}


def is_valid_date(value):
    """Strict YYYY-MM-DD check. Anything else (DD-MM-YYYY, MM/DD/YYYY, blank) fails."""
    if pd.isna(value):
        return False
    value = str(value).strip()
    if value == "":
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def is_live_api_source(formats):
    """formats column is a comma separated list like 'CSV,JSON,API'."""
    if pd.isna(formats):
        return False
    parts = [f.strip().upper() for f in str(formats).split(",")]
    return "API" in parts


def check_submission(row):
    issues = []

    # 1. data owner present
    owner = row["data_owner_name"]
    if pd.isna(owner) or str(owner).strip() == "":
        issues.append("Missing data owner")

    # 2. description adequate (not blank, 20+ chars)
    desc = "" if pd.isna(row["description"]) else str(row["description"]).strip()
    if len(desc) < 20:
        issues.append("Description missing or too short")

    # 3. classification present and valid
    classification = "" if pd.isna(row["data_classification"]) else str(row["data_classification"]).strip()
    if classification not in VALID_CLASSIFICATIONS:
        issues.append("Classification missing/invalid")

    # 4. DPDP flag consistency - only matters when dpdp_personal_data = Yes
    dpdp = "" if pd.isna(row["dpdp_personal_data"]) else str(row["dpdp_personal_data"]).strip()
    if dpdp == "Yes" and classification not in {"Restricted", "Confidential"}:
        issues.append("DPDP flag inconsistent with classification")

    # 5. last_updated date format
    if not is_valid_date(row["last_updated"]):
        issues.append("last_updated format invalid")

    # 6. record count present (blank only ok for live API sources)
    rc = row["record_count"]
    if pd.isna(rc) or str(rc).strip() == "":
        if not is_live_api_source(row["formats"]):
            issues.append("Record count missing")
    else:
        try:
            rc_val = int(float(rc))
            if rc_val <= 0:
                issues.append("Record count not positive")
        except ValueError:
            issues.append("Record count not numeric")

    # 7. submitted_on date format
    if not is_valid_date(row["submitted_on"]):
        issues.append("submitted_on format invalid")

    return issues


def run_quality_review():
    df = pd.read_csv(os.path.join(DATA_DIR, "metadata_submissions.csv"))

    df["issues_list"] = df.apply(check_submission, axis=1)
    df["issues"] = df["issues_list"].apply(lambda x: ", ".join(x))
    df["issue_count"] = df["issues_list"].apply(len)

    flagged = df[df["issue_count"] > 0].copy()
    clean = df[df["issue_count"] == 0].copy()

    flagged_out = flagged[["submission_id", "department", "dataset_title", "issues"]]
    flagged_out.to_csv(os.path.join(OUT_DIR, "quality_flags.csv"), index=False)

    clean_out = clean.drop(columns=["issues_list", "issues", "issue_count"])
    clean_out.to_csv(os.path.join(OUT_DIR, "clean_submissions.csv"), index=False)

    # most common issue types, for the summary report
    all_issues = [i for sub in flagged["issues_list"] for i in sub]
    issue_counts = Counter(all_issues)

    total = len(df)
    n_clean = len(clean)
    n_flagged = len(flagged)

    lines = []
    lines.append("DATA QUALITY REVIEW - SUMMARY")
    lines.append("=" * 40)
    lines.append(f"Total submissions reviewed: {total}")
    lines.append(f"Pass all checks: {n_clean} ({n_clean/total*100:.0f}%)")
    lines.append(f"Fail one or more checks: {n_flagged} ({n_flagged/total*100:.0f}%)")
    lines.append("")
    lines.append("Most common issue types:")
    for issue, count in issue_counts.most_common():
        lines.append(f"  - {issue}: {count}")

    with open(os.path.join(OUT_DIR, "review_summary.txt"), "w") as f:
        f.write("\n".join(lines))

    print("\n".join(lines))

    return df


def cross_check_tracker(df):
    """Section 1.2 - compare our flags against compliance_tracker.csv"""
    tracker = pd.read_csv(os.path.join(DATA_DIR, "compliance_tracker.csv"))
    tracker["final_status"] = tracker["final_status"].astype(str).str.strip()
    tracker["is_approved"] = tracker["final_status"].str.startswith("Approved")

    merged = df.merge(tracker[["submission_id", "final_status", "is_approved", "revised_submission_received"]],
                       on="submission_id", how="left")

    our_flagged = merged[merged["issue_count"] > 0]
    our_clean = merged[merged["issue_count"] == 0]

    mis_approved = our_flagged[our_flagged["is_approved"] == True]
    ready_to_approve = merged[(merged["is_approved"] == False) & (merged["issue_count"] == 0)]

    correctly_approved = our_clean[our_clean["is_approved"] == True]
    correctly_pending = our_flagged[our_flagged["is_approved"] == False]

    print("\n\nCROSS-CHECK AGAINST COMPLIANCE TRACKER")
    print("=" * 40)
    print(f"Flagged by us but tracker shows Approved: {len(mis_approved)}")
    if len(mis_approved) > 0:
        print(mis_approved[["submission_id", "issues"]])

    print(f"\nTracker shows Pending but our checks find no issues: {len(ready_to_approve)}")
    if len(ready_to_approve) > 0:
        print(ready_to_approve[["submission_id", "final_status"]])

    print("\nSummary table:")
    print(f"  Correctly Approved:      {len(correctly_approved)}")
    print(f"  Correctly Pending:       {len(correctly_pending)}")
    print(f"  Potentially mis-approved:{len(mis_approved)}")
    print(f"  Potentially ready:       {len(ready_to_approve)}")

    return merged


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    reviewed = run_quality_review()
    cross_check_tracker(reviewed)
