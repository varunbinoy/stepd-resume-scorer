import streamlit as st
import json, math, traceback, re
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).parent
CONFIG = BASE / "config"

st.set_page_config(page_title="STEP D Resume Scorer", layout="wide")

# Win95 Style
st.markdown("""
<style>
.stApp { background: #c0c0c0; }
section[data-testid="stSidebar"] { background:#bdbdbd; border-right:2px solid #808080; }
.stButton > button { border-radius:0px; border:2px solid #808080; background:#e0e0e0; box-shadow:none; font-weight:600; }
div[data-testid="stDataFrame"] { border:2px solid #808080; border-radius:0px; box-shadow:none; background:#ffffff; }
</style>
""", unsafe_allow_html=True)

st.title("STEP D – Sales Resume Scorer ")
st.caption("Competency-based scoring • Evidence extraction • Recency bias ")

# Load config
constants = json.loads((CONFIG / "constants.json").read_text())
weights = json.loads((CONFIG / "weights.json").read_text())
lexicon = json.loads((CONFIG / "lexicon.json").read_text())

import pdfplumber

uploaded_files = st.sidebar.file_uploader("Upload PDF resumes", type=["pdf"], accept_multiple_files=True)
run = st.sidebar.button("Run scoring")

YEAR_PATTERN = re.compile(r"\b(19\d{2}|20\d{2})\b")

def extract_text(file):
    with pdfplumber.open(file) as pdf:
        return " ".join([p.extract_text() or "" for p in pdf.pages])

def normalize(text):
    return re.sub(r"\s+", " ", re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())).strip()

def get_year_span(text):
    years = [int(y) for y in YEAR_PATTERN.findall(text)]
    if not years:
        return None
    return max(years) - min(years)

def detect_recent_grad(text):
    current_year = datetime.now().year
    years = [int(y) for y in YEAR_PATTERN.findall(text)]
    for y in years:
        if current_year - y <= 1:
            return y
    return None

def extract_evidence(tokens, term, window=10):
    snippets = []
    for i, t in enumerate(tokens):
        if t == term:
            start = max(0, i-window)
            end = min(len(tokens), i+window)
            snippets.append(" ".join(tokens[start:end]))
            if len(snippets) >= 2:
                break
    return snippets

def score_resume(raw_text):
    text = normalize(raw_text)
    tokens = text.split()

    subscores = {}
    evidence = {}
    cap = constants["cap_threshold"]

    for comp, words in lexicon.items():
        count = sum(text.count(w) for w in words)
        capped = min(count, cap)
        subscores[comp] = round((capped / cap) * 100, 1)

        comp_evidence = []
        for w in words:
            comp_evidence.extend(extract_evidence(tokens, w))
        evidence[comp] = comp_evidence[:2]

    # Metric boost
    numeric_tokens = sum(1 for t in tokens if any(c.isdigit() for c in t))
    metric_bonus = 1 - math.exp(-constants["metric_k"] * numeric_tokens)
    subscores["targets"] = min(100, subscores.get("targets",0) + metric_bonus*20)

    total = sum(subscores[k]*weights[k] for k in weights)
    total = round(min(100,total),2)

    positives = []
    risks = []

    # WorkEx extreme negative
    


    # Competency positives
    ranked = sorted(subscores.items(), key=lambda x:x[1], reverse=True)
    for comp,score in ranked:
        if score>60 and len(positives)<3:
            positives.append({
                "type":comp,
                "reason":f"Strong {comp} signal ({score})",
                "evidence":evidence[comp]
            })

    # Competency risks
    low = sorted(subscores.items(), key=lambda x:x[1])
    for comp,score in low:
        if score<30 and len(risks)<3:
            risks.append({
                "type":comp,
                "reason":f"Weak {comp} signal ({score})",
                "evidence":[]
            })

    tier="REVIEW"
    if total>constants["shortlist_gt"]:
        tier="SHORTLIST"
    elif total<constants["reject_lt"]:
        tier="REJECT"

    return subscores,total,tier,positives[:3],risks[:3]

if run:
    if not uploaded_files:
        st.warning("Upload at least one PDF first.")
    else:
        results = []
        details = []

        for file in uploaded_files:
            raw = extract_text(file)
            subs, total, tier, pos, risk = score_resume(raw)

            results.append({"File": file.name, "Score": total, "Tier": tier, **subs})
            details.append({
                "File": file.name,
                "Score": total,
                "Tier": tier,
                "Positives": pos,
                "Risks": risk
            })

        import pandas as pd
        df = pd.DataFrame(results).sort_values("Score", ascending=False).reset_index(drop=True)
        df.index += 1

        # STORE RESULTS SO DROPDOWN DOESN'T WIPE THEM
        st.session_state["df"] = df
        st.session_state["details"] = details


# DISPLAY (persists across reruns)
if "df" in st.session_state:
    df = st.session_state["df"]
    details = st.session_state["details"]

    st.subheader("Ranked Results")
    st.dataframe(df, use_container_width=True)

    st.subheader("Explainability")
    selected = st.selectbox("Select Candidate", df["File"].tolist())

    d = next(x for x in details if x["File"] == selected)
    st.write(f"**Tier:** {d['Tier']}  |  **Score:** {d['Score']}")

    st.write("### Top Positives (max 3)")
    st.json(d["Positives"])

    st.write("### Top Risks (max 3)")
    st.json(d["Risks"])

    st.subheader("Download")
    st.download_button(
        "Download CSV",
        df.reset_index(drop=True).to_csv(index=False).encode("utf-8"),
        "ranked_results.csv",
        "text/csv"
    )


st.markdown("---")
st.caption("")

