"""
data_files.py - where Dugout Data finds its two data files.

READ-ONLY for data. Locally it uses the files on this computer:
  psl.sqlite           data/psl.sqlite next to app/
  psl_insights.sqlite  ../private/psl_insights.sqlite beside the project folder (or DD_INSIGHTS_DB)
On Streamlit Cloud those are absent, so it downloads them once per server from the private
GitHub repo named in Streamlit secrets, with a read-only token (never in any file):
  [data]
  github_token = "..."       fine-grained token: Contents read-only on that repo only
  repo = "owner/dugout-data-files"
psl.sqlite is a file in that repo; psl_insights.sqlite is a release file (tag "data").
Downloads go to a temporary folder named after app/DATA_VERSION (written by tools/publish.py),
so a new publish downloads fresh files and an unchanged one reuses them.
"""

import os
import shutil
import sqlite3
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import streamlit as st

APP = Path(__file__).resolve().parent
ROOT = APP.parent
LOCAL_PSL = ROOT / "data" / "psl.sqlite"
LOCAL_INSIGHTS = Path(os.environ.get("DD_INSIGHTS_DB") or ROOT.parent / "private" / "psl_insights.sqlite")
RELEASE_TAG = "data"
API = os.environ.get("DD_GITHUB_API", "https://api.github.com")     # tests use a local stand-in
AGENT = "dugout-data-app"


def data_version():
    f = APP / "DATA_VERSION"
    return f.read_text(encoding="utf-8").strip() if f.exists() else "local"


def valid(path, table):
    """True if path is a readable SQLite file with the expected table."""
    try:
        with sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True) as con:
            ok = con.execute("PRAGMA quick_check").fetchone()[0] == "ok"
            return ok and con.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (table,)).fetchone() is not None
    except sqlite3.Error:
        return False


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _get(url, token, accept, follow=True):
    """GET with the token. Release files redirect to a storage link that must be fetched without it."""
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": accept,
                                               "User-Agent": AGENT, "X-GitHub-Api-Version": "2022-11-28"})
    opener = urllib.request.build_opener() if follow else urllib.request.build_opener(_NoRedirect)
    try:
        return opener.open(req, timeout=120)
    except urllib.error.HTTPError as e:
        if not follow and e.code in (301, 302, 303, 307, 308):
            plain = urllib.request.Request(e.headers["Location"], headers={"User-Agent": AGENT})
            return urllib.request.urlopen(plain, timeout=120)
        raise


def _save(resp, dest):
    tmp = dest.with_name(dest.name + ".part")
    with open(tmp, "wb") as f:
        shutil.copyfileobj(resp, f, length=1 << 20)
    os.replace(tmp, dest)


def _download(name, dest, token, repo):
    if name == "psl.sqlite":
        resp = _get(f"{API}/repos/{repo}/contents/{name}", token, "application/vnd.github.raw")
    else:
        import json
        rel = json.load(_get(f"{API}/repos/{repo}/releases/tags/{RELEASE_TAG}", token, "application/vnd.github+json"))
        asset = next(a for a in rel["assets"] if a["name"] == name)
        resp = _get(asset["url"], token, "application/octet-stream", follow=False)
    _save(resp, dest)


@st.cache_resource(show_spinner="Loading the PSL data")
def paths():
    """(psl_path, insights_path or None, problem or ''). Local files win; otherwise download."""
    if LOCAL_PSL.exists():
        return LOCAL_PSL, (LOCAL_INSIGHTS if LOCAL_INSIGHTS.exists() else None), ""
    try:
        cfg = st.secrets["data"]
        token, repo = cfg["github_token"], cfg["repo"]
    except (KeyError, FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return None, None, "The data files are not set up on this server."
    folder = Path(tempfile.gettempdir()) / "dugout_data" / data_version()
    folder.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, table in (("psl.sqlite", "export_info"), ("psl_insights.sqlite", "zone")):
        dest = folder / name
        try:
            if not valid(dest, table):
                _download(name, dest, token, repo)
            out[name] = dest if valid(dest, table) else None
        except Exception:                      # network, token or missing file: no details on screen
            out[name] = None
    if out["psl.sqlite"] is None:
        return None, None, "The PSL data could not be loaded. Please try again in a few minutes."
    return out["psl.sqlite"], out["psl_insights.sqlite"], ""
