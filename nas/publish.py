"""Render the screens on the NAS and publish them on GitHub Pages.

Runs in the container of nas/compose.yaml. One round every 3 hours, at :37
of 00, 03, 06, ... 21 Swiss time (user's choice, 9 Nov 2026: fewer Pages
deployments, after GitHub's Pages service got stuck on one). MeteoSwiss
publishes each hourly run 2–7 min past the hour; the T5 still fetches every
hour at :40 and gets the same files in between. A failed round is retried
once at :52 of the same hour. Each round:

1. pull main, so code changes go live without touching the NAS
2. render.py → site/ (checks MeteoSwiss for a new run, fetches WindSpots and SLF)
3. force-push site/ as a single commit to the gh-pages branch, which Pages
   serves at https://frgaude.github.io/MeteoSwiss-local-forecast/ (one commit,
   so the repository does not grow by ~1.5 MB an hour)

A failed round is logged; after the retry, the next round tries again.
GITHUB_TOKEN (a fine-grained token with Contents read/write on this repository) authorises
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
from zoneinfo import ZoneInfo

SELF = os.path.abspath(__file__)
REPO = os.path.dirname(os.path.dirname(SELF))
SITE = os.path.join(REPO, "site")
CACHE = os.path.join(REPO, "data", "local_forecast")
REMOTE = "https://github.com/frgaude/MeteoSwiss-local-forecast.git"
TZ = ZoneInfo("Europe/Zurich")
EVERY_HOURS = 3           # a round at :ROUND_MINUTE of every 3rd local hour (00, 03, ...)
ROUND_MINUTE = 37         # just before the T5 fetches at :40
RETRY_MINUTE = 52         # one retry in the same hour after a failed round
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
    """The next round after `now`: :ROUND_MINUTE of the next local hour that
    is a multiple of EVERY_HOURS."""
    t = now.astimezone(TZ).replace(minute=ROUND_MINUTE, second=0, microsecond=0)
    while t <= now or t.hour % EVERY_HOURS:
        t += timedelta(hours=1)
    return t


def sleep_until(t):
    time.sleep(max(0, (t - datetime.now(timezone.utc)).total_seconds()))


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
    git("push", "-q", "--force", REMOTE, "gh-pages", cwd=SITE, auth=True)
    prune_cache()


def _digest():
    with open(SELF, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main(once, wait=False):
    loaded = _digest()
    while True:
        if wait:
            sleep_until(next_round(datetime.now(timezone.utc)))
        wait = True
        for attempt in (1, 2):
            try:
                publish()
                log("published")
                break
            except Exception as e:
                log(f"failed: {e}")
                retry = datetime.now(TZ).replace(minute=RETRY_MINUTE, second=0, microsecond=0)
                if once or attempt == 2 or retry <= datetime.now(timezone.utc):
                    break
                sleep_until(retry)
        if once:
            return
        if _digest() != loaded:                 # the pull brought a new version of this loop
            log("nas/publish.py changed, restarting it")
            os.execv(sys.executable, [sys.executable, SELF, "--wait"])


if __name__ == "__main__":
    main("--once" in sys.argv, wait="--wait" in sys.argv)
