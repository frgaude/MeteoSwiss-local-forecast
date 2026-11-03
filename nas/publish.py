"""Render the screens on the NAS and publish them on GitHub Pages.

Runs in the container of nas/compose.yaml. Forecast rounds at :12, :37 and
:52 also check MeteoSwiss for a new run (published 2–7 min past the hour);
wind rounds at :02, :25 and :45 re-render the newest cached run, so only the
measurements (WindSpots, SLF) are new and MeteoSwiss is not contacted. The T5
fetches at :40: :37 gives it the freshest measured wind with time for the push
and the Pages deployment (~30 s), and retries a failed :12. Each round:

1. pull main, so code changes go live without touching the NAS
2. render.py → site/ (with the cached run in a wind round)
3. force-push site/ as a single commit to the gh-pages branch, which Pages
   serves at https://frgaude.github.io/MeteoSwiss-local-forecast/ (one commit,
   so the repository does not grow by ~1.5 MB an hour)

A failed round is logged and the next one tries again. GITHUB_TOKEN (a
fine-grained token with Contents read/write on this repository) authorises
the push; without it git uses its own credentials. The pull needs none (the
repository is public).

The loop itself is this file, loaded once: when a pull changes it, it
restarts itself (render.py runs as a new process each round anyway).

Usage: python nas/publish.py [--once | --wait]   (--wait: no round on start)
"""
import base64
import hashlib
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

SELF = os.path.abspath(__file__)
REPO = os.path.dirname(os.path.dirname(SELF))
SITE = os.path.join(REPO, "site")
CACHE = os.path.join(REPO, "data", "local_forecast")
REMOTE = "https://github.com/frgaude/MeteoSwiss-local-forecast.git"
FORECAST_MINUTES = (12, 37, 52)   # also check MeteoSwiss for a new run
WIND_MINUTES = (2, 25, 45)        # newest cached run, fresh measurements only
KEEP_DAYS = 7             # forecast runs kept in the cache (~9 MB a day)


def log(msg):
    print(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}Z {msg}", flush=True)


def git(*args, cwd=REPO, auth=False):
    """Run git; never prompt (fail instead). With `auth`, send GITHUB_TOKEN as
    a header set through the environment, so the token is in neither the
    command line nor an error message (which repeats the command)."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    token = os.environ.get("GITHUB_TOKEN")
    if auth and token:
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="http.extraHeader",
                   GIT_CONFIG_VALUE_0=f"Authorization: Basic {basic}")
    subprocess.run(["git", *args], cwd=cwd, env=env, check=True)


def next_round(now):
    """(time, forecast) of the next round after `now`; `forecast` is True for
    a forecast round."""
    minutes = sorted(FORECAST_MINUTES + WIND_MINUTES)
    for m in minutes:
        t = now.replace(minute=m, second=0, microsecond=0)
        if t > now:
            return t, m in FORECAST_MINUTES
    t = now.replace(minute=minutes[0], second=0, microsecond=0) + timedelta(hours=1)
    return t, minutes[0] in FORECAST_MINUTES


def cached_run():
    """The newest run in the cache (its points.json is written once its
    downloads are complete), or None."""
    if not os.path.isdir(CACHE):
        return None
    return max((n for n in os.listdir(CACHE) if len(n) == 12 and n.isdigit()
                and os.path.exists(os.path.join(CACHE, n, "points.json"))), default=None)


def prune_cache():
    """Delete forecast runs (data/local_forecast/<YYYYMMDDHHMM>/) older than KEEP_DAYS."""
    if not os.path.isdir(CACHE):
        return
    oldest = (datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)).strftime("%Y%m%d%H%M")
    for name in os.listdir(CACHE):
        if len(name) == 12 and name.isdigit() and name < oldest:
            shutil.rmtree(os.path.join(CACHE, name), ignore_errors=True)


def publish(forecast):
    git("pull", "--ff-only", "-q")
    shutil.rmtree(SITE, ignore_errors=True)
    run = None if forecast else cached_run()    # no cache yet: a forecast round after all
    subprocess.run([sys.executable, "render.py", "site", *([run] if run else [])], cwd=REPO, check=True)
    open(os.path.join(SITE, ".nojekyll"), "w").close()   # serve the files as they are
    git("init", "-q", "-b", "gh-pages", cwd=SITE)
    git("add", "-A", cwd=SITE)
    git("-c", "user.name=NAS render", "-c", "user.email=nas@localhost",
        "commit", "-q", "-m", f"Render {datetime.now(timezone.utc):%Y-%m-%d %H:%M}Z", cwd=SITE)
    git("push", "-q", "--force", REMOTE, "gh-pages", cwd=SITE, auth=True)
    prune_cache()


def _digest():
    with open(SELF, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main(once, wait=False):
    loaded = _digest()
    forecast = True                             # the first round, on start
    while True:
        if wait:
            wake, forecast = next_round(datetime.now(timezone.utc))
            time.sleep(max(0, (wake - datetime.now(timezone.utc)).total_seconds()))
        wait = True
        try:
            publish(forecast)
            log("published" if forecast else "published (wind round)")
        except Exception as e:
            log(f"failed: {e}")
        if once:
            return
        if _digest() != loaded:                 # the pull brought a new version of this loop
            log("nas/publish.py changed, restarting it")
            os.execv(sys.executable, [sys.executable, SELF, "--wait"])


if __name__ == "__main__":
    main("--once" in sys.argv, wait="--wait" in sys.argv)
