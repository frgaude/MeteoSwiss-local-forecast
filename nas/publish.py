"""Render the screens on the NAS and publish them on GitHub Pages.

Runs in the container of nas/compose.yaml, at :12, :32 and :52 (MeteoSwiss
publishes each run 2–7 min past the hour; the T5 fetches at :40). Each round:

1. pull main, so code changes go live without touching the NAS
2. render.py → site/
3. force-push site/ as a single commit to the gh-pages branch, which Pages
   serves at https://frgaude.github.io/MeteoSwiss-local-forecast/ (one commit,
   so the repository does not grow by ~1.5 MB an hour)

A failed round is logged and the next one tries again. GITHUB_TOKEN (a
fine-grained token with Contents read/write on this repository) authorises
the push; without it git uses its own credentials.

Usage: python nas/publish.py [--once]
"""
import base64
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(REPO, "site")
CACHE = os.path.join(REPO, "data", "local_forecast")
REMOTE = "https://github.com/frgaude/MeteoSwiss-local-forecast.git"
MINUTES = (12, 32, 52)
KEEP_DAYS = 7             # forecast runs kept in the cache (~9 MB a day)


def log(msg):
    print(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}Z {msg}", flush=True)


def git(*args, cwd=REPO):
    token = os.environ.get("GITHUB_TOKEN")
    auth = []
    if token:   # a header, so the token never shows in a remote URL or an error message
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        auth = ["-c", f"http.extraHeader=Authorization: Basic {basic}"]
    subprocess.run(["git", *auth, *args], cwd=cwd, check=True)


def next_round(now):
    """The next :12, :32 or :52 after `now`."""
    for m in MINUTES:
        t = now.replace(minute=m, second=0, microsecond=0)
        if t > now:
            return t
    return now.replace(minute=MINUTES[0], second=0, microsecond=0) + timedelta(hours=1)


def prune_cache():
    """Delete forecast runs (data/local_forecast/<YYYYMMDDHHMM>/) older than KEEP_DAYS."""
    if not os.path.isdir(CACHE):
        return
    oldest = (datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)).strftime("%Y%m%d%H%M")
    for name in os.listdir(CACHE):
        if len(name) == 12 and name.isdigit() and name < oldest:
            shutil.rmtree(os.path.join(CACHE, name), ignore_errors=True)


def publish():
    git("pull", "--ff-only", "-q")
    shutil.rmtree(SITE, ignore_errors=True)
    subprocess.run([sys.executable, "render.py", "site"], cwd=REPO, check=True)
    open(os.path.join(SITE, ".nojekyll"), "w").close()   # serve the files as they are
    git("init", "-q", "-b", "gh-pages", cwd=SITE)
    git("add", "-A", cwd=SITE)
    git("-c", "user.name=NAS render", "-c", "user.email=nas@localhost",
        "commit", "-q", "-m", f"Render {datetime.now(timezone.utc):%Y-%m-%d %H:%M}Z", cwd=SITE)
    git("push", "-q", "--force", REMOTE, "gh-pages", cwd=SITE)
    prune_cache()


def main(once):
    while True:
        try:
            publish()
            log("published")
        except Exception as e:
            log(f"failed: {e}")
        if once:
            return
        wake = next_round(datetime.now(timezone.utc))
        time.sleep(max(0, (wake - datetime.now(timezone.utc)).total_seconds()))


if __name__ == "__main__":
    main("--once" in sys.argv)
