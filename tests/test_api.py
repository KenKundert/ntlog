from pathlib import Path
from ntlog import NTlog, NTlogError
from inform import Error
import nestedtext as nt
import arrow
import os
import pytest
import re

def time_matches(found, expected, tolerance=5):
    return (
        found > expected.shift(seconds=-tolerance)
        and
        found < expected.shift(seconds=tolerance)
    )

def times_match(found, expected, tolerance=5):
    return any(time_matches(f, e) for f in found for e in expected)

def find_key(expected, entries):
    for key in entries:
        if time_matches(key, expected):
            return key

def exercise_ntlog(delete_running_log=True, extra="", **kwargs):
    assert 'mtime' not in kwargs
    if 'running_log_file' not in kwargs:
        kwargs['running_log_file'] = 'test.log.nt'
    keep_for = kwargs.get('keep_for', 7)
    min_entries = kwargs.get('min_entries', 1)
    max_entries = kwargs.get('max_entries', 0)
    days_upper_bound = max(keep_for, min_entries, max_entries)
        # this assumes one entry per day
    if not max_entries:
        max_entries = 1000
    if delete_running_log:
        Path('test.log.nt').unlink(missing_ok=True)

    mtimes = []
    for days in reversed(range(days_upper_bound + 7)):
        now = arrow.now()
        mtime = now.shift(days=-days)
        mtimes.append(mtime)
        mtime_to_use = mtime if days else None
        temp_log_file = kwargs.get('temp_log_file')
        retain_temp = kwargs.get('retain_temp')

        # run ntlog and retrieve the results
        with NTlog(mtime=mtime_to_use, **kwargs) as ntlog:
            ntlog.write(f"entry written = {days} days ago.{extra}")
            if temp_log_file:
                assert os.path.isfile(temp_log_file)
        running_log = nt.load(kwargs['running_log_file'])
        running_log = {arrow.get(k): v for k, v in running_log.items()}

        # running log must contain the given log entry
        assert find_key(mtime, running_log)

        # check to see if given temp log was created if requested
        if temp_log_file:
            assert os.path.isfile(temp_log_file) == bool(retain_temp)

        # check that the number of entries matches our expectations
        num_entries = len(running_log)
        runs = len(mtimes)
        assert num_entries <= min(runs, max_entries)
        assert num_entries >= min(runs, min_entries)

        mtimes_to_check = mtimes[-num_entries:]
        for mtime in mtimes_to_check:
            age = (now - mtime).days
            key = find_key(mtime, running_log)
            assert key, str(mtime)
            assert running_log[key] == f"entry written = {age} days ago."

    return mtimes

def test_defaults():
    mtimes = exercise_ntlog(running_log_file='test.log.nt')

    # now shrink keep_for and check that old entries are deleted
    now = arrow.now()
    expected_mtimes = [mtime for mtime in mtimes if (now - mtime).days < 3]

    with NTlog('test.log.nt', keep_for='3d') as nt_log:
        pass
    running_log = nt.load('test.log.nt')
    mtimes = [arrow.get(k) for k in running_log.keys()]
    # trim off last update and reverse order
    mtimes = list(reversed(mtimes[1:]))
    assert len(mtimes) == len(expected_mtimes)
    assert times_match(mtimes, expected_mtimes)

def test_delete():
    exercise_ntlog(temp_log_file='test.log')
    exercise_ntlog(temp_log_file='test.log', retain_temp=False)
    exercise_ntlog(temp_log_file='test.log', retain_temp=True)

def test_keep_for():
    exercise_ntlog(keep_for=3)

def test_min_entries():
    exercise_ntlog(min_entries=3)

def test_max_entries():
    exercise_ntlog(max_entries=3)

def test_retention():
    # checks that you can add a given log file that is beyond the keep_for date
    Path('test.log.nt').unlink(missing_ok=True)
    for i in range(5):
        age = 21 + i
        mtime = arrow.now().shift(days=-age)
        with NTlog('test.log.nt', keep_for=14*86400, mtime=mtime) as ntlog:
            ntlog.write(f"entry written = {age} days ago.")
            ntlog.flush()
        running_log = nt.load('test.log.nt')
        mtimes = list(running_log.keys())
        assert len(mtimes) == 1
        assert mtimes[0] == str(mtime)

def test_flush():
    # checks that you can add a given log file that is beyond the keep_for date
    running_log_file = Path('test.log.nt')
    temp_log_file = Path('test.log')
    running_log_file.unlink(missing_ok=True)
    temp_log_file.unlink(missing_ok=True)
    with NTlog(running_log_file, temp_log_file, retain_temp=False) as ntlog:
            ntlog.write(f"Hey now!")
            ntlog.flush()
            contents = temp_log_file.read_text()
            assert contents == "Hey now!"
    assert not temp_log_file.is_file()

def test_exceptions():
    running_logfile = Path('test.log.nt')

    # try to save a log file with same mtime but differing contents
    Path('test.log.nt').unlink(missing_ok=True)
    now = arrow.now()
    mtime = now.timestamp()
    with pytest.raises(NTlogError) as exception:
        with NTlog('test.log.nt', mtime=mtime) as ntlog:
            ntlog.write('Hey now!')
        with NTlog('test.log.nt', mtime=mtime) as ntlog:
            ntlog.write('Hey there!')
    assert isinstance(exception.value, Error)
    assert str(exception.value) == f"{now!s}: attempt to overwrite log entry."
    assert exception.value.args == ('attempt to overwrite log entry.',)

    # attempt to read a running log file with a bogus datestamp
    Path('test.log.nt').write_text("not a date: contents")
    with pytest.raises(NTlogError) as exception:
        with NTlog('test.log.nt', mtime=mtime) as ntlog:
            pass
    expected = "Expected an ISO 8601-like string, but was given 'not a date'."
    assert isinstance(exception.value, Error)
    assert str(exception.value) == f"test.log.nt: {expected}"
    assert exception.value.args == (expected,)

    # attempt to read a running log file that is not valid NestedText
    Path('test.log.nt').write_text("not valid NestedText")
    with pytest.raises(NTlogError) as exception:
        with NTlog('test.log.nt', mtime=mtime) as ntlog:
            pass
    expected = "unrecognized line."
    assert isinstance(exception.value, Error)
    assert isinstance(exception.value, nt.NestedTextError)
    assert str(exception.value) == f"test.log.nt, 1: {expected}"
    assert exception.value.args == ()
    assert exception.value.kwargs == dict(
        codicil = ("   1 ❬not valid NestedText❭\n      ▲",),
        colno = 0,
        culprit = ("test.log.nt", 1),
        line = "not valid NestedText",
        lineno = 0,
        source = "test.log.nt",
        template = "unrecognized line.",
    )
    assert exception.value.get_culprit() == ("test.log.nt", 1)
    assert exception.value.get_codicil() == ("   1 ❬not valid NestedText❭\n      ▲",)


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
