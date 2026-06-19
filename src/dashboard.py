"""
Section 3 - Compliance Dashboard

Reads the processed CSVs from Section 1 & 2 (data/processed/) and shows
the Data Governance Lead an at-a-glance view of the registry.

Run locally from repo root with:
    streamlit run src/dashboard.py

Deploy on Streamlit Community Cloud by pointing it at src/dashboard.py in a
GitHub repo that also contains the data/processed/ folder.
"""

import pandas as pd
import streamlit as st
import plotly.express as px
import os

st.set_page_config(page_title="UP Metadata Platform - Compliance Dashboard", layout="wide")

# resolve data/processed relative to this file, so it works no matter where
# `streamlit run` is launched from
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(THIS_DIR, "..", "data", "processed")


@st.cache_data
def load_data():
    compliance_report = pd.read_csv(os.path.join(DATA_DIR, "compliance_report.csv"))
    issue_analysis = pd.read_csv(os.path.join(DATA_DIR, "issue_type_analysis.csv"))
    dpdp_full = pd.read_csv(os.path.join(DATA_DIR, "dpdp_full_tracker.csv"))
    return compliance_report, issue_analysis, dpdp_full


compliance_report, issue_analysis, dpdp_full = load_data()

st.title("UP Metadata Platform - Compliance Dashboard")
st.caption("Source: data/processed/ outputs from Section 1 (Quality Review) and Section 2 (Compliance Analysis)")

# ---------------------------------------------------------------------------
# Panel 1: Overview
# ---------------------------------------------------------------------------
st.header("Overview")

total_submitted = int(compliance_report["datasets_submitted"].sum())
total_approved = int(compliance_report["approved"].sum())
total_pending = int(compliance_report["pending"].sum())
dpdp_flagged = int((~dpdp_full["compliant"]).sum())

pct_approved = round(total_approved / total_submitted * 100, 1) if total_submitted else 0
pct_pending = round(total_pending / total_submitted * 100, 1) if total_submitted else 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Submissions", total_submitted)
c2.metric("Approved", f"{total_approved} ({pct_approved}%)")
c3.metric("Pending", f"{total_pending} ({pct_pending}%)")
c4.metric("DPDP Issues Flagged", dpdp_flagged)

st.divider()

# ---------------------------------------------------------------------------
# Panel 2: Department Status
# ---------------------------------------------------------------------------
st.header("Department Status")

status_filter = st.selectbox(
    "Filter by status",
    ["All", "Has pending items", "Fully approved", "Follow-up not sent to everyone pending"],
)

dept_view = compliance_report.copy()
if status_filter == "Has pending items":
    dept_view = dept_view[dept_view["pending"] > 0]
elif status_filter == "Fully approved":
    dept_view = dept_view[dept_view["pending"] == 0]
elif status_filter == "Follow-up not sent to everyone pending":
    dept_view = dept_view[dept_view["follow_up_sent_all_pending"].isin(["No", "Partial"])]

dept_search = st.text_input("Search department name")
if dept_search:
    dept_view = dept_view[dept_view["department"].str.contains(dept_search, case=False, na=False)]

st.dataframe(
    dept_view.sort_values("pct_approved"),
    use_container_width=True,
    hide_index=True,
)

fig_dept = px.bar(
    dept_view.sort_values("pct_approved"),
    x="pct_approved", y="department", orientation="h",
    labels={"pct_approved": "% Approved", "department": ""},
    title="Approval Rate by Department",
)
fig_dept.update_layout(yaxis={"categoryorder": "total ascending"})
st.plotly_chart(fig_dept, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Panel 3: Issue Breakdown
# ---------------------------------------------------------------------------
st.header("Issue Breakdown (Pending Submissions)")

fig_issue = px.bar(
    issue_analysis.sort_values("submissions_affected", ascending=True),
    x="submissions_affected", y="issue", orientation="h",
    labels={"submissions_affected": "Submissions Affected", "issue": ""},
    title="Most Common Quality Issues",
)
st.plotly_chart(fig_issue, use_container_width=True)

st.caption("Non-response rate = share of submissions with this issue where the department hasn't replied to a follow-up.")
st.dataframe(issue_analysis, use_container_width=True, hide_index=True)

st.divider()

# ---------------------------------------------------------------------------
# Panel 4: DPDP Flag Tracker
# ---------------------------------------------------------------------------
st.header("DPDP Flag Tracker (Personal Data Submissions)")

show_only_noncompliant = st.checkbox("Show only non-compliant", value=False)

dpdp_view = dpdp_full.copy()
if show_only_noncompliant:
    dpdp_view = dpdp_view[~dpdp_view["compliant"]]


def highlight_noncompliant(row):
    color = "" if row["compliant"] else "background-color: #ffe3e3"
    return [color] * len(row)


st.dataframe(
    dpdp_view.style.apply(highlight_noncompliant, axis=1),
    use_container_width=True,
    hide_index=True,
)

n_compliant = int(dpdp_full["compliant"].sum())
n_noncompliant = int((~dpdp_full["compliant"]).sum())
st.caption(f"{n_compliant} compliant, {n_noncompliant} non-compliant out of {len(dpdp_full)} datasets flagged as containing personal data.")
