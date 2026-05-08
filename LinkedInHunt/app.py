"""
JobTrack — LinkedIn Job Finder
Flask backend using python-jobspy to scrape LinkedIn directly.
No API key required.
"""

import os
import re
import math
import traceback

import pandas as pd
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

# ── App Setup ──────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="public", static_url_path="")
CORS(app)

PORT = int(os.environ.get("PORT", 3000))

# Words too generic to be useful for matching
_STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "i", "me", "my", "we", "our", "you", "your",
    "it", "its", "this", "that", "these", "those", "want", "looking", "like",
    "work", "job", "role", "position", "seeking", "need", "ideally", "prefer",
    "experience", "years", "year", "also", "about", "some", "any", "all",
    "new", "good", "great", "strong", "excellent", "able", "well",
}


# ── Routes ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the frontend."""
    return send_from_directory("public", "index.html")


@app.route("/api/jobs")
def get_jobs():
    """
    Scrape LinkedIn jobs via python-jobspy, optionally scored against
    user-supplied criteria.

    Query params:
        title    (str)  — job title to search, e.g. "Software Engineer"
        city     (str)  — city, e.g. "San Jose"
        state    (str)  — full state name, e.g. "California"
        criteria (str)  — free-text description of ideal job (optional)
        results  (int)  — how many results to return (default 20, max 50)
    """
    title    = request.args.get("title",    "").strip()
    city     = request.args.get("city",     "").strip()
    state    = request.args.get("state",    "").strip()
    criteria = request.args.get("criteria", "").strip()
    results  = min(int(request.args.get("results", 20)), 50)

    if not title or not city or not state:
        return jsonify({
            "error": "Missing required parameters: title, city, and state are all required."
        }), 400

    location = f"{city}, {state}"
    query    = f"{title} in {location}"

    try:
        from jobspy import scrape_jobs
    except ImportError:
        return jsonify({
            "error": "python-jobspy is not installed. Run: pip install python-jobspy"
        }), 500

    try:
        print(f"[JobTrack] Scraping: {query!r} ({results} results)")

        df = scrape_jobs(
            site_name=["linkedin"],
            search_term=title,
            location=location,
            results_wanted=results,
            hours_old=720,
            country_indeed="USA",
            linkedin_fetch_description=True,
            verbose=0
        )

        jobs = [_serialize_job(row) for _, row in df.iterrows()]
        jobs = [j for j in jobs if j["title"] and j["applyLink"]]

        # ── Score & sort against criteria ──────────────────────────────
        if criteria:
            keywords = _extract_keywords(criteria)
            for job in jobs:
                score, matched = _score_job(job, keywords)
                job["matchScore"]    = score
                job["matchKeywords"] = matched
            jobs.sort(key=lambda j: j["matchScore"], reverse=True)
        else:
            for job in jobs:
                job["matchScore"]    = None
                job["matchKeywords"] = []

        print(f"[JobTrack] Returning {len(jobs)} jobs (criteria={'yes' if criteria else 'no'})")

        return jsonify({
            "query":    query,
            "total":    len(jobs),
            "criteria": criteria,
            "jobs":     jobs
        })

    except Exception as exc:
        traceback.print_exc()
        msg = str(exc)
        if "429" in msg or "rate" in msg.lower():
            msg = "LinkedIn is rate-limiting requests right now. Please wait a few minutes and try again."
        elif "timeout" in msg.lower():
            msg = "The request timed out. LinkedIn may be slow — please try again shortly."
        elif "blocked" in msg.lower() or "captcha" in msg.lower():
            msg = "LinkedIn has temporarily blocked scraping from this server. Try again in a few minutes."
        return jsonify({"error": msg}), 500


# ── Criteria Scoring ───────────────────────────────────────────────────────

def _extract_keywords(criteria: str) -> list[str]:
    text = criteria.lower()

    COMPOUND_TERMS = [
        "machine learning", "deep learning", "natural language processing",
        "computer vision", "data science", "data engineering", "data analysis",
        "software engineering", "product management", "project management",
        "artificial intelligence", "full stack", "full-stack", "front end",
        "back end", "backend", "frontend", "devops", "mlops", "ci/cd",
        "react native", "node.js", "next.js", "vue.js", "asp.net",
        "c#", "c++", "objective-c", "ruby on rails",
        "remote work", "work from home", "hybrid",
        "series a", "series b", "series c", "early stage", "startup",
        "stock options", "equity", "base salary", "sign on",
    ]
    found_compounds = []
    for term in COMPOUND_TERMS:
        if term in text:
            found_compounds.append(term.replace(" ", "_"))
            text = text.replace(term, "")

    words = re.findall(r'\b[\w][a-z0-9+#.\-]{1,}\b', text)
    singles = [w for w in words if w not in _STOP_WORDS and len(w) > 1]

    all_keywords = found_compounds + singles
    seen = set()
    unique = []
    for k in all_keywords:
        if k not in seen:
            seen.add(k)
            unique.append(k)
    return unique


def _score_job(job: dict, keywords: list[str]) -> tuple[int, list[str]]:
    if not keywords:
        return 0, []

    title   = (job.get("title")          or "").lower()
    company = (job.get("company")        or "").lower()
    desc    = (job.get("description")    or "").lower()
    loc     = (job.get("location")       or "").lower()
    emp     = (job.get("employmentType") or "").lower()

    max_points = len(keywords) * 6
    earned = 0
    matched = []

    for kw in keywords:
        search_kw = kw.replace("_", " ")
        hit = False
        if search_kw in title:   earned += 3; hit = True
        if search_kw in company: earned += 2; hit = True
        if search_kw in desc:    earned += 1; hit = True
        if search_kw in loc or search_kw in emp: earned += 1; hit = True
        if hit:
            matched.append(search_kw)

    score = round((earned / max_points) * 100) if max_points else 0
    return min(score, 100), matched


# ── Serializers ────────────────────────────────────────────────────────────

def _serialize_job(row: pd.Series) -> dict:
    return {
        "id":             _safe_str(row.get("id")),
        "title":          _safe_str(row.get("title")),
        "company":        _safe_str(row.get("company")),
        "logo":           None,
        "website":        _safe_str(row.get("company_url")),
        "location":       _safe_str(row.get("location")),
        "isRemote":       bool(row.get("is_remote", False)),
        "employmentType": _map_job_type(row.get("job_type")),
        "applyLink":      _safe_str(row.get("job_url")),
        "description":    _truncate(_safe_str(row.get("description")), 300),
        "salary":         _format_salary(row),
        "postedAt":       _format_date(row.get("date_posted")),
    }


def _map_job_type(raw) -> str | None:
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return None
    label_map = {
        "fulltime":   "FULLTIME",
        "parttime":   "PARTTIME",
        "contract":   "CONTRACTOR",
        "internship": "INTERN",
        "temporary":  "TEMPORARY",
    }
    raw_str = str(raw).lower().replace("-", "").replace(" ", "")
    return label_map.get(raw_str, str(raw).upper())


def _format_salary(row: pd.Series) -> str | None:
    lo  = row.get("min_amount")
    hi  = row.get("max_amount")
    per = row.get("interval", "") or ""

    if _is_missing(lo) and _is_missing(hi):
        return None

    period = {
        "yearly": "/yr", "monthly": "/mo",
        "weekly": "/wk", "daily": "/day", "hourly": "/hr",
    }.get(str(per).lower(), "")

    def fmt(n):
        try:    return f"${int(n):,}"
        except: return str(n)

    if not _is_missing(lo) and not _is_missing(hi): return f"{fmt(lo)} – {fmt(hi)}{period}"
    if not _is_missing(lo):  return f"From {fmt(lo)}{period}"
    if not _is_missing(hi):  return f"Up to {fmt(hi)}{period}"
    return None


def _format_date(value) -> str | None:
    if _is_missing(value):
        return None
    if isinstance(value, str):
        return value
    try:
        dt = pd.Timestamp(value)
        if dt.tzinfo is None:
            dt = dt.tz_localize("UTC")
        return dt.isoformat()
    except Exception:
        return None


def _truncate(text: str, max_chars: int) -> str | None:
    if not text or text == "nan":
        return None
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "…"


def _safe_str(value) -> str:
    if _is_missing(value):
        return ""
    return str(value).strip()


def _is_missing(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and value.lower() in ("nan", "none", ""):
        return True
    return False


# ── Entry Point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n🚀  JobTrack running at http://localhost:{PORT}\n")
    app.run(host="0.0.0.0", port=PORT, debug=False)
