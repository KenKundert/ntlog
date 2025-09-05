from pathlib import Path
from shlib import Run
import nestedtext as nt
import arrow
import os

now = arrow.now()

def create_logfile(age, extra=''):
    path = Path('test.log')
    path.write_text(f"entry written = {age} days ago.{extra}")
    ctime = now.shift(days=-age, seconds=-600)
    os.utime(str(path), (ctime.timestamp(), ctime.timestamp()))
    return ctime

def exercise_ntlog(
    keep_for = None,
    min_entries = None,
    max_entries = None,
    delete = None,
    delete_running_log = True
):
    cmd = ['ntlog']
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
    if delete_running_log:
        Path('test.log.nt').unlink(missing_ok=True)

    ctimes = []
    for days in reversed(range(upper_bound + 7)):
        ctime = create_logfile(days)
        ctimes.append(ctime)
        Run(cmd, 'sOEW')
        running_log = nt.load('test.log.nt')

        # running log must contain the given log entry
        assert str(ctime) in running_log

        # check to see if given logfile was deleted if requested
        assert os.path.isfile('test.log') != delete

        # check that the number of entries matches our expectations
        num_entries = len(running_log)
        runs = len(ctimes)
        assert num_entries <= min(runs, max_entries)
        assert num_entries >= min(runs, min_entries)

        ctimes_to_check = ctimes[-num_entries:]
        for ctime in ctimes_to_check:
            age = (now - ctime).days
            ctime = str(ctime)
            assert ctime in running_log, ctime
            assert running_log[ctime] == f"entry written = {age} days ago."

def test_defaults():
    exercise_ntlog()

    # now shrink keep_for and check that old entries are deleted
    running_log = nt.load('test.log.nt')
    ctimes = [arrow.get(k) for k in running_log]
    expected_ctimes = [ctime for ctime in ctimes if (now - ctime).days < 3]

    Run(['ntlog', '--keep-for', '3', 'test.log'], 'sOEW')
    running_log = nt.load('test.log.nt')
    ctimes = [arrow.get(k) for k in running_log.keys()]
    assert len(ctimes) == len(expected_ctimes)
    assert ctimes == expected_ctimes

def test_delete():
    exercise_ntlog(delete=True)

def test_keep_for():
    exercise_ntlog(keep_for=3)

def test_min_entries():
    exercise_ntlog(min_entries=3)

def test_max_entries():
    exercise_ntlog(max_entries=3)

def test_retention():
    # checks that you can add a given log file that is beyond the keep_for date
    ctime = create_logfile(21)
    Path('test.log.nt').unlink(missing_ok=True)
    for i in range(5):
        Run(['ntlog', 'test.log'], 'sOEW')
        running_log = nt.load('test.log.nt')
        ctimes = list(running_log.keys())
        assert len(ctimes) == 1
        assert ctimes[0] == str(ctime)

def test_exceptions():
    running_logfile = Path('test.log.nt')

    running_logfile.unlink(missing_ok=True)
    ntlog = Run(['ntlog', 'does-not-exist'], 'sOEW1')
    assert ntlog.status == 1
    assert ntlog.stderr == 'ntlog error: does-not-exist: no such file or directory.\n'

    running_logfile.unlink(missing_ok=True)
    ntlog = Run(['ntlog', '--max-entries', 'infinity', 'does-not-exist'], 'sOEW1')
    assert ntlog.status == 1
    assert ntlog.stderr == 'ntlog error: infinity: could not convert to number.\n'

    running_logfile.unlink(missing_ok=True)
    ntlog = Run(['ntlog', '--min-entries', '0', 'does-not-exist'], 'sOEW1')
    assert ntlog.status == 1
    assert ntlog.stderr == 'ntlog error: 0: expected strictly positive number.\n'

    # try to save a log file with same ctime but differing contents
    running_logfile.unlink(missing_ok=True)
    create_logfile(1)
    ntlog = Run(['ntlog', 'test.log'], 'sOEW1')
    assert ntlog.status == 0
    ctime = create_logfile(1, extra='\na difference')
    ntlog = Run(['ntlog', 'test.log'], 'sOEW1')
    assert ntlog.status == 1
    #assert re.match('ntlog error: [^ ]+: attempt to overwrite log entry.\n', ntlog.stderr)
    assert ntlog.stderr == f'ntlog error: {ctime!s}: attempt to overwrite log entry.\n'

    # attempt to read a running log file with a bogus datestamp
    running_logfile.write_text("not a date: contents")
    ntlog = Run(['ntlog', 'test.log'], 'sOEW1')
    assert ntlog.status == 1
    assert "Expected an ISO 8601-like string, but was given 'not a date'." in ntlog.stderr

    # attempt to read a bogus running log file
    running_logfile.write_text("not a valid NT file")
    ntlog = Run(['ntlog', 'test.log'], 'sOEW1')
    assert ntlog.status == 1
    assert 'unrecognized line.' in ntlog.stderr

    # attempt to read a bogus running log file
    ntlog = Run(['ntlog', '--keep-for', '2fortnight', 'test.log'], 'sOEW1')
    assert ntlog.status == 1
    assert 'unable to convert' in ntlog.stderr

if __name__ == '__main__':
    # As a debugging aid allow the tests to be run on their own, outside pytest.
    # This makes it easier to see and interpret and textual output.

    defined = dict(globals())
    for k, v in defined.items():
        if callable(v) and k.startswith('test_'):
            print()
            print('Calling:', k)
            print((len(k)+9)*'=')
            v()
