#!/usr/bin/env python3
# DESCRIPTION {{{1
"""
NTlog — append a log file into an running NestedText log

Usage:
    ntlog [options] <logfile>

Options:
    -k, --keep-for [days]    drop entries older than this [default: 7]
    -n, --max-entries [N]    maximum number of log entries to keep
    -N, --min-entries [N]    minimum number of log entries to keep [default: 1]
    -d, --delete             delete given logfile after incorporating it

Copies <logfile> into <logfile>.nt while deleting any log entries that are older 
than the limit specified by --keep-for.
"""
__version__ = '0.2'
__released__ = '2023-04-10'


# IMPORTS {{{1
from docopt import docopt
from inform import fatal, full_stop, os_error
from pathlib import Path
from quantiphy import Quantity, UnitConversion, QuantiPhyError
import nestedtext as nt
import arrow

# UTILITIES {{{1
# to_int() {{{2
def to_int(number):
    try:
        if number:
            number = int(number)
            if number > 0:
                return number
            fatal('expected strictly positive number.', culprit=number)
    except ValueError as e:
        fatal('could not convert to number.', culprit=number)

# trim_dict() {{{2
def trim_dict(d, max_entries):
    # trim the dictionary such that it contains only the max_entries most
    # recently added items
    return dict(list(d.items())[:max_entries])

# TIME CONVERSIONS {{{1
UnitConversion("s", "sec second seconds")
UnitConversion("s", "m min minute minutes", 60)
UnitConversion("s", "h hr hour hours", 60*60)
UnitConversion("s", "d day days", 24*60*60)
UnitConversion("s", "w W week weeks", 7*24*60*60)
UnitConversion("s", "M month months", 30*24*60*60)
UnitConversion("s", "y Y year years", 365*24*60*60)
Quantity.set_prefs(ignore_sf=True)

# MAIN {{{1
def main():
    # Command line {{{2
    cmdline = docopt(__doc__)
    logfile = cmdline['<logfile>']
    try:
        keep_for = Quantity(cmdline['--keep-for'], 'd', scale='s')
    except QuantiPhyError as e:
        fatal(e, culprit=f'--keep-for={cmdline["--keep-for"]}')
    max_entries = to_int(cmdline['--max-entries'])
    min_entries = to_int(cmdline['--min-entries'])
    delete_given_log = cmdline['--delete']
    oldest = arrow.now().shift(seconds=-keep_for)

    # Load the running log, append the logfile, and write it out again {{{2
    try:
        logfile = Path(logfile)
        running_logfile = logfile.with_suffix('.log.nt')

        # load running log
        try:
            running_log = nt.load(running_logfile, dict)
        except FileNotFoundError:
            running_log = {}

        # convert keys to time and sort
        running_log = {arrow.get(k):v  for k,v in running_log.items()}
        running_log = {k:running_log[k] for k in sorted(running_log, reverse=True)}

        # filter running log
        if len(running_log) > min_entries:
            truncated_log = {k:v for k,v in running_log.items() if arrow.get(k) > oldest}
            if len(truncated_log) < min_entries-1:
                truncated_log = trim_dict(running_log, min_entries)
            running_log = truncated_log
        if max_entries and len(running_log) >= max_entries:
            running_log = trim_dict(running_log, max_entries-1)

        # get new log entry and add it to running log
        mtime = arrow.get(logfile.stat().st_mtime).to('local')

        contents = logfile.read_text()
        log = {mtime: contents}
        if mtime in running_log:
            if contents != running_log[mtime]:
                fatal('attempt to overwrite log entry.', culprit=str(mtime))
        log.update(running_log)

        # write out running log
        nt.dump(log, running_logfile, default=str)

        # delete given log file
        if delete_given_log:
            logfile.unlink()

    # Handle exceptions {{{2
    except OSError as e:
        fatal(os_error(e))
    except nt.NestedTextError as e:
        e.terminate()
    except arrow.ParserError as e:
        fatal(full_stop(e), wrap=True, culprit=running_logfile)
