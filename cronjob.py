#!/usr/bin/env python3
"""A script run hourly to check which jobs to run now.

The script:
- checks if no other instance of the script is running (using UNIX flock),
- remembers (in a file) when each job last started and finished successfully,
- runs the first job that should be run (synchronously) and then terminates.
A job should be run if between now and the last time it finished there was a
'running moment'. 'Running moments' are 19th and last day of each month.
"""
import typing
from typing import List, Optional, Tuple
from datetime import datetime, timezone
import collections
import json
import fcntl

OrderedDict = dict

LOCK_FILE_NAME = ".cronjob.lock"
STATE_FILE_NAME = ".cronState.json"
# Dict from job id-key to time we last started and finished it.
State = OrderedDict[str, Tuple[Optional[datetime], Optional[datetime]]]
# Representation of State as a JSON object
JSONState = OrderedDict[str, Tuple[Optional[str], Optional[str]]]

# PYTHON = ['/usr/bin/python3.12']
PYTHON = ['/home/token0/workspace/conda/envs/wikipedia/bin/python']

jobs: OrderedDict[str, List[str]] = OrderedDict(
    andBot=PYTHON + ['andBot.py'],
    variantBot=PYTHON + ['variantBot.py'],
    abbrevIsoBot=PYTHON + ['-m', 'abbrevIsoBot', 'fixpages'],
    abbrevIso=['../abbrevIso/exampleScript.js',
               'abbrevIsoBot/abbrevBotState.json'],
    abbrevIsoPost=PYTHON + ['-m', 'abbrevIsoBot', 'report'],
    fillBot=PYTHON + ['-m', 'abbrevIsoBot', 'fill']
)


def main() -> None:
    """Script's entry point."""
    import os
    os.chdir(os.path.dirname(__file__))
    _lock = ExclusiveInstanceLock(os.getcwd() + '/' + LOCK_FILE_NAME)

    lastRunTimes: State = loadState()

    for jobId, jobArgs in jobs.items():
        s, t = lastRunTimes.get(jobId, (None, None))
        if s and ((not t) or t < s):
            send_notification(f'bad times {jobId} s={s} t={t} {jobArgs}')
            raise Exception(f'ERROR: {jobId}: last end time < start time, job killed?')
        if not s or (t and shouldRunJob(max(s, t))):
            s = datetime.now(timezone.utc)
            lastRunTimes[jobId] = (s, t)
            saveState(lastRunTimes)

            runJob(jobId, jobArgs)

            t = datetime.now(timezone.utc)
            lastRunTimes[jobId] = (s, t)
            saveState(lastRunTimes)
            return
    print('No jobs to run.')


def send_notification(message="ERROR"):
    """Send a notification to my phone using Pushover.

    See `https://pushover.net/api`.
    """
    import http.client, urllib
    conn = http.client.HTTPSConnection('api.pushover.net:443')
    with open('.cronConfig.json') as f:
        request = json.load(f)
    assert isinstance(request, dict)  # Should have 'token' and 'user' keys.
    request['message'] = 'workspace/wikipedia/tokenzeroBot/cronjob.py ' + message
    conn.request('POST',
                 '/1/messages.json',
                 urllib.parse.urlencode(request),
                 { 'Content-type': 'application/x-www-form-urlencoded' })
    print(conn.getresponse())


def shouldRunJob(t: datetime) -> bool:
    """Return whether between t and now there was a 'running moment'.

    Running moments are ~every week.
    """
    import calendar
    now = datetime.now(timezone.utc)
    for y in [now.year - 1, now.year]:
        for m in range(1, 13):
            for d in [7, 14, 21, calendar.monthrange(y, m)[1]]:
                for h in [1]:
                    moment = datetime(y, m, d, h, tzinfo=timezone.utc)
                    if moment > now:
                        return False
                    if t < moment:
                        return True
    return False


def runJob(jobId: str, jobArgs: List[str], timeout: int = 8 * 60 * 60) -> None:
    """Run job with same stdout/err, return when done.

    Throw if non-zero return code or killed by timeout (in seconds).
    """
    import subprocess
    import os
    print(f'Running: {jobId} ({" ".join(jobArgs)}).')
    d = datetime.now(timezone.utc).date().isoformat()
    fp = open(f'logs/cron-{jobId}-{d}.txt', 'a')
    fp.write(f'[cronjob starting {datetime.now(timezone.utc).isoformat()}]\n')
    fp.flush()
    if jobArgs[0].startswith('.'):
        jobArgs[0] = os.getcwd() + '/' + jobArgs[0]
    env = os.environ  # | {"PYTHONPATH": "/home/token0/workspace/wikipedia/pywikibot/core/:" + os.environ.get("PYTHONPATH", "")}
    subprocess.run(jobArgs, timeout=timeout, check=True, stdout=fp, stderr=fp, env=env)
    fp.flush()
    fp.write(f'[cronjob finished {datetime.now(timezone.utc).isoformat()}]\n')
    fp.flush()


class ExclusiveInstanceLock:
    """Assert that no other instance of this script is running, or die."""

    def __init__(self, lockFileName: str) -> None:
        import sys
        print(f'Locking: {lockFileName}')
        self.fp = open(lockFileName, 'a')
        try:
            fcntl.flock(self.fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
            print('Locked.')
        except (IOError, OSError):
            print('Another instance running, quitting.')
            sys.exit(-1)


def loadState() -> State:
    """Load lastRunTimes from STATE_FILE_NAME."""
    try:
        with open(STATE_FILE_NAME, 'rt') as f:
            simpleDict: JSONState = \
                json.load(f, object_pairs_hook=OrderedDict)
            assert isinstance(simpleDict, OrderedDict)
            result = State()
            for key, (s, t) in simpleDict.items():
                assert s is None or isinstance(s, str)
                assert t is None or isinstance(t, str)
                ss = datetime.fromisoformat(s) if s else None
                tt = datetime.fromisoformat(t) if t else None
                result[key] = (ss, tt)
            return result
    except FileNotFoundError:
        print('Initiating empty bot state.')
        return State()


def saveState(state: State) -> None:
    """Save lastRunTimes to STATE_FILE_NAME."""
    simpleDict = JSONState()
    for key, (s, t) in state.items():
        ss = s.isoformat(" ") if s else None
        tt = t.isoformat(" ") if t else None
        simpleDict[key] = (ss, tt)
    with open(STATE_FILE_NAME, 'wt') as f:
        json.dump(simpleDict, f, indent="\t")
        f.write("\n")


if __name__ == "__main__":
    main()
