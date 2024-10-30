# DESCRIPTION {{{1
"""
NTlog — append a log file into an running NestedText log

Usage:
    ntlog [options] <logfile>

Options:
    -k, --keep-for [days]     drop entries older than this [default: 7]
    -n, --max-entries [N]     maximum number of log entries to keep
    -N, --min-entries [N]     minimum number of log entries to keep [default: 1]
    -d, --delete              delete given logfile after incorporating it
    -Y, --year <fmt>          add year headers
    -M, --month <fmt>         add month headers
    -D, --day <fmt>           add day headers
    -H, --hour <fmt>          add hour headers
    -E, --entry <fmt>         add entry headers
    -d, --description <text>  description for entry header for new log entry
    -e, --editor <editor>     add editor mode line, choose from: {editors}
    --fold-marker <mapping>   map fold markers contained in logfile

Copies <logfile> into <logfile>.nt while deleting any log entries that are older 
than the limit specified by --keep-for.
"""
__version__ = '0.5'
__released__ = '2024-10-30'


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
    except ValueError:
        fatal('could not convert to number.', culprit=number)

# MAIN {{{1
def main():
    # Command line {{{2
    editors = ', '.join(NTlog.MODE_LINES)
    cmdline = docopt(__doc__.format(editors=editors), version=__version__)
    input_logfile = Path(cmdline['<logfile>'])
    output_logfile = input_logfile.with_suffix('.log.nt')
    keep_for = cmdline['--keep-for']
    max_entries = to_int(cmdline['--max-entries'])
    min_entries = to_int(cmdline['--min-entries'])
    delete_given_log = cmdline['--delete']
    if cmdline['--fold-marker']:
        fold_marker_mapping = cmdline['--fold-marker'].split()
        if len(fold_marker_mapping) != 2:
            fatal(
                'value must consist of two space separated tokens.',
                culprit='--fold-marker'
            )
    else:
        fold_marker_mapping = None

    # Load the running log, append the logfile, and write it out again {{{2
    try:
        with NTlog(
            output_logfile,
            keep_for = keep_for,
            max_entries = max_entries,
            min_entries = min_entries,
            ctime = input_logfile.stat().st_mtime,
            year_header = cmdline['--year'],
            month_header = cmdline['--month'],
            day_header = cmdline['--day'],
            hour_header = cmdline['--hour'],
            entry_header = cmdline['--entry'],
            fold_marker_mapping = fold_marker_mapping,
            description = cmdline['--description'],
            editor = cmdline['--editor'],
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
