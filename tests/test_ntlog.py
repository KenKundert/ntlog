from pathlib import Path
from shlib import Run
import nestedtext as nt
import arrow
import os

now = arrow.now()

def create_logfile(age):
    path = Path('test.log')
    path.write_text(f"entry written = {age} days ago.")
    mtime = now.shift(days=-age)
    os.utime(str(path), (mtime.timestamp(), mtime.timestamp()))
    return mtime

def exercise_ntlog(keep_for=None, min_entries=None, max_entries=None, delete=None):
    cmd = ['./run-ntlog']
    if keep_for:
        cmd.extend(['--keep-for', str(keep_for)])
    if min_entries:
        cmd.extend(['--min-entries', str(min_entries)])
    if max_entries:
        cmd.extend(['--max-entries', str(max_entries)])
    if delete:
        cmd.append('--delete')
    cmd.append('test.log')
    keep_for = keep_for if keep_for else 7
    min_entries = min_entries if min_entries else 1
    max_entries = max_entries if max_entries else 0
    upper_bound = max(keep_for, min_entries, max_entries)
    if not max_entries:
        max_entries = 1000
    Path('test.log.nt').unlink(missing_ok=True)

    mtimes = []
    for days in reversed(range(upper_bound + 7)):
        mtime = create_logfile(days)
        mtimes.append(mtime)
        ntlog = Run(cmd, 'sOEW')
        running_log = nt.load('test.log.nt')

        # running log must contain the given log entry
        assert str(mtime) in running_log

        # check to see if given logfile was deleted if requested
        assert os.path.isfile('test.log') != delete

        # check that the number of entries matches our expectations
        num_entries = len(running_log)
        runs = len(mtimes)
        assert num_entries <= min(runs, max_entries)
        assert num_entries >= min(runs, min_entries)

        mtimes_to_check = mtimes[-num_entries:]
        for mtime in mtimes_to_check:
            age = (now - mtime).days
            mtime = str(mtime)
            assert mtime in running_log, mtime
            assert running_log[mtime] == f"entry written = {age} days ago."


def test_defaults():
    exercise_ntlog()

def test_delete():
    exercise_ntlog(delete=True)

def test_keep_for():
    exercise_ntlog(keep_for=3)

def test_min_entries():
    exercise_ntlog(min_entries=3)

def test_max_entries():
    exercise_ntlog(max_entries=3)

    #exercise_ntlog(keep_for=None, min_entries=None, max_entries=None, delete=None)

if __name__ == '__main__':
    test_all()
