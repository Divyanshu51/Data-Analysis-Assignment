"""
Section 2 - Compliance Analysis

Builds the department-level tracking view for the Data Governance Lead using
metadata_submissions.csv, compliance_tracker.csv, and the quality_flags.csv
that came out of Section 1.

Outputs (written to data/processed/):
    compliance_report.csv      - one row per department (2.1)
    issue_type_analysis.csv    - issue counts + non-response rate (2.2)
    dpdp_gaps.csv               - personal-data submissions missing a requirement (2.3)
    compliance_notes.txt        - plain-language notes for the Governance Lead

2.2 and 2.3 are point-in-time checks rather than tracked tables, but I'm
saving them anyway so the Lead has something to open without re-running this.
"""

import pandas as pd
from datetime import datetime
from collections import Counter
import os

DATA_DIR = "data"
OUT_DIR = "data/processed"

AS_OF = datetime.now()  # "today" for the 7-day follow-up check


def load_data():
    metadata = pd.read_csv(os.path.join(DATA_DIR, "metadata_submissions.csv"))
    tracker = pd.read_csv(os.path.join(DATA_DIR, "compliance_tracker.csv"))
    flags = pd.read_csv(os.path.join(OUT_DIR, "quality_flags.csv"))

    tracker["final_status"] = tracker["final_status"].astype(str).str.strip()
    tracker["is_approved"] = tracker["final_status"].str.startswith("Approved")
    tracker["is_pending"] = tracker["final_status"].str.startswith("Pending")

    return metadata, tracker, flags


# ---------------------------------------------------------------------------
# 2.1 Department-level compliance table
# ---------------------------------------------------------------------------

def follow_up_status(pending_rows):
    """Yes / No / Partial / N/A depending on follow_up_sent across a dept's pending items."""
    if len(pending_rows) == 0:
        return "N/A"
    sent = pending_rows["follow_up_sent"].astype(str).str.strip() == "Yes"
    if sent.all():
        return "Yes"
    if not sent.any():
        return "No"
    return "Partial"


def has_stale_followup(pending_rows):
    """Yes if any pending item had a follow-up sent 7+ days ago with no department response."""
    if len(pending_rows) == 0:
        return "No"
    no_response = pending_rows[pending_rows["department_responded"].astype(str).str.strip() == "No"]
    no_response = no_response[no_response["follow_up_date"].notna()]
    if len(no_response) == 0:
        return "No"
    days_waiting = (AS_OF - pd.to_datetime(no_response["follow_up_date"])).dt.days
    return "Yes" if (days_waiting >= 7).any() else "No"


def build_department_table(metadata, tracker):
    merged = metadata.merge(tracker, on="submission_id", suffixes=("", "_tracker"))

    rows = []
    for dept, g in merged.groupby("department"):
        submitted = len(g)
        approved = g["is_approved"].sum()
        pending = g["is_pending"].sum()
        pending_rows = g[g["is_pending"]]

        rows.append({
            "department": dept,
            "datasets_submitted": submitted,
            "approved": approved,
            "pending": pending,
            "pct_approved": round(approved / submitted * 100, 1),
            "follow_up_sent_all_pending": follow_up_status(pending_rows),
            "no_response_7plus_days": has_stale_followup(pending_rows),
        })

    table = pd.DataFrame(rows).sort_values("pct_approved", ascending=True).reset_index(drop=True)
    return table


# ---------------------------------------------------------------------------
# 2.2 Issue type analysis
# ---------------------------------------------------------------------------

def analyse_issue_types(flags, tracker):
    """Expand the comma-separated issues column and join back to department_responded."""
    exploded = flags.assign(issue=flags["issues"].str.split(", ")).explode("issue")
    exploded = exploded.merge(
        tracker[["submission_id", "department_responded"]],
        on="submission_id", how="left"
    )

    counts = exploded["issue"].value_counts()

    no_resp = exploded[exploded["department_responded"].astype(str).str.strip() == "No"]
    no_resp_counts = no_resp["issue"].value_counts()

    summary = pd.DataFrame({
        "issue": counts.index,
        "submissions_affected": counts.values,
    })
    summary["no_response_count"] = summary["issue"].map(no_resp_counts).fillna(0).astype(int)
    summary["no_response_rate_pct"] = round(summary["no_response_count"] / summary["submissions_affected"] * 100, 1)
    summary = summary.sort_values("no_response_rate_pct", ascending=False).reset_index(drop=True)
    return summary


# ---------------------------------------------------------------------------
# 2.3 DPDP compliance flag
# ---------------------------------------------------------------------------

def check_dpdp(metadata):
    personal = metadata[metadata["dpdp_personal_data"].astype(str).str.strip() == "Yes"].copy()

    personal["classification_ok"] = personal["data_classification"].isin(["Restricted", "Confidential"])
    personal["steward_ok"] = personal["data_steward_assigned"].astype(str).str.strip() == "Yes"
    personal["compliant"] = personal["classification_ok"] & personal["steward_ok"]

    full_tracker = personal[["submission_id", "department", "dataset_title", "data_classification",
                              "classification_ok", "data_steward_assigned", "steward_ok", "compliant"]]

    gaps = personal[~personal["compliant"]].copy()
    gaps["missing"] = gaps.apply(
        lambda r: ", ".join(filter(None, [
            "" if r["classification_ok"] else "classification not Restricted/Confidential",
            "" if r["steward_ok"] else "no data steward assigned",
        ])), axis=1
    )
    gaps = gaps[["submission_id", "department", "dataset_title", "data_classification",
                 "data_steward_assigned", "missing"]]

    return full_tracker, gaps


# ---------------------------------------------------------------------------
# Plain-language notes for the Governance Lead
# ---------------------------------------------------------------------------

def write_notes(dept_table, issue_summary, dpdp_gaps, path):
    worst = dept_table.iloc[0]
    best = dept_table[dept_table["pct_approved"] == 100]
    stale_depts = dept_table[dept_table["no_response_7plus_days"] == "Yes"]["department"].tolist()
    top_issue = issue_summary.iloc[0]

    n_pending_depts = (dept_table["pending"] > 0).sum()

    lines = []
    lines.append("Metadata Platform - compliance check-in")
    lines.append(AS_OF.strftime("%d %b %Y"))
    lines.append("")
    lines.append(
        f"{n_pending_depts} out of {len(dept_table)} departments have something pending right now, "
        f"the other {len(best)} are fully cleared."
    )
    lines.append("")
    lines.append(
        f"{worst['department']} is the one to watch - {worst['pct_approved']}% approved so far "
        f"({worst['approved']} of {worst['datasets_submitted']})."
    )
    lines.append("")
    if stale_depts:
        lines.append(
            "Follow-ups went out a while back and these departments still haven't replied: "
            + ", ".join(stale_depts) + ". Probably need a nudge, maybe a phone call at this point "
            "rather than another email."
        )
    else:
        lines.append("Nobody is overdue on a follow-up reply right now.")
    lines.append("")
    lines.append(
        f"'{top_issue['issue']}' is still the most common reason submissions get bounced back "
        f"({int(top_issue['submissions_affected'])} cases), and departments aren't responding to it - "
        f"{top_issue['no_response_rate_pct']}% non-response rate, the worst of any issue type."
    )
    lines.append("")
    if len(dpdp_gaps) > 0:
        lines.append(
            f"On the DPDP side, {len(dpdp_gaps)} submissions marked as containing personal data still "
            "haven't got the classification and steward sign-off sorted - see dpdp_gaps.csv for which ones."
        )
    else:
        lines.append("DPDP-wise we're fine - every submission with personal data has classification and a steward.")
    lines.append("")
    lines.append("Full department breakdown is in compliance_report.csv, worst to best.")

    with open(path, "w") as f:
        f.write("\n".join(lines))

    print("\n".join(lines))


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)

    metadata, tracker, flags = load_data()

    dept_table = build_department_table(metadata, tracker)
    dept_table.to_csv(os.path.join(OUT_DIR, "compliance_report.csv"), index=False)

    issue_summary = analyse_issue_types(flags, tracker)
    issue_summary.to_csv(os.path.join(OUT_DIR, "issue_type_analysis.csv"), index=False)

    dpdp_full, dpdp_gaps = check_dpdp(metadata)
    dpdp_full.to_csv(os.path.join(OUT_DIR, "dpdp_full_tracker.csv"), index=False)
    dpdp_gaps.to_csv(os.path.join(OUT_DIR, "dpdp_gaps.csv"), index=False)

    print("\nDEPARTMENT COMPLIANCE TABLE (2.1)")
    print("=" * 40)
    print(dept_table.to_string(index=False))

    print("\n\nISSUE TYPE ANALYSIS (2.2)")
    print("=" * 40)
    print(issue_summary.to_string(index=False))

    print("\n\nDPDP GAPS (2.3)")
    print("=" * 40)
    print(dpdp_gaps.to_string(index=False) if len(dpdp_gaps) else "None")

    write_notes(dept_table, issue_summary, dpdp_gaps, os.path.join(OUT_DIR, "compliance_notes.txt"))
