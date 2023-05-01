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
__version__ = '0.3'
__released__ = '2023-05-01'


# IMPORTS {{{1
from docopt import docopt
from inform import Error, fatal, full_stop, os_error
from pathlib import Path
from . import NTlog

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

# MAIN {{{1
def main():
    # Command line {{{2
    cmdline = docopt(__doc__)
    input_logfile = Path(cmdline['<logfile>'])
    output_logfile = input_logfile.with_suffix('.log.nt')
    keep_for = cmdline['--keep-for']
    max_entries = to_int(cmdline['--max-entries'])
    min_entries = to_int(cmdline['--min-entries'])
    delete_given_log = cmdline['--delete']

    # Load the running log, append the logfile, and write it out again {{{2
    try:
        with NTlog(
            output_logfile,
            keep_for = keep_for,
            max_entries = max_entries,
            min_entries = min_entries,
            ctime = input_logfile.stat().st_mtime,
        ) as ntlog:
            log = input_logfile.read_text()
            ntlog.write(log)

        if delete_given_log:
            input_logfile.unlink()

    # Handle exceptions {{{2
    except OSError as e:
        fatal(os_error(e))
    except Error as e:
        fatal(full_stop(e))
