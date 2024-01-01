# encoding: utf8
# DESCRIPTION {{{1
"""
NTlog — Add a log into an accumulating NestedText log file

NTlog is a class that presents a stream interface so it can be used anywhere a
file stream can be used.  Rather than creating a stand alone logfile it
incorporates the log into an accumlating logfile structured as a dictionary in
at NestedText file where the creation time is used as the key for the entries.
"""

# MIT LICENSE {{{1
# Copyright (c) 2020-2024 Ken Kundert
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# IMPORTS {{{1
from inform import Error, is_str
from pathlib import Path
from quantiphy import Quantity, UnitConversion, QuantiPhyError
import arrow
import io
import nestedtext as nt


# UTILITIES {{{1
# Time Conversions {{{2
UnitConversion("s", "sec second seconds")
UnitConversion("s", "m min minute minutes", 60)
UnitConversion("s", "h hr hour hours", 60*60)
UnitConversion("s", "d day days", 24*60*60)
UnitConversion("s", "w W week weeks", 7*24*60*60)
UnitConversion("s", "M month months", 30*24*60*60)
UnitConversion("s", "y Y year years", 365*24*60*60)
Quantity.set_prefs(ignore_sf=True)

# trim_dict() {{{2
# Trim the dictionary such that it contains only the max_entries most
# recently added items.
def trim_dict(d, max_entries):
    return dict(list(d.items())[:max_entries])

# comment() {{{2
# Add comment leader if first non-white-space header is not a #.
def create_header(date, format):
    text = date.format(format)
    prefix = ''
    if text and text.lstrip()[0] != '#':
        prefix = '# '
    return prefix + text


# NTlog class {{{1
class NTlog:
    # description {{{2
    """ NTlog

    NTlog instances can be used as an output file stream, but instead of writing
    to stand-alone files their output is incorporated into a NestedText_ logfile.

    Arguments:
        running_log_file: (str, os.PathLike):
            The path to the composite log file.  Normally this uses .log.nt as
            the suffix.
        temp_log_file: (str, os.PathLike):
            The path to the temporary log file.  Normally this uses .log.nt as
            the suffix.  This is optional; if not given a temporary log file is
            not created.
        keep_for (float, str):
            Any entries older than keep_for (in seconds) are dropped.
            If keep_for is a string, it is converted to seconds.  In this case
            it assumed to be a number followed by a unit.  For example, '1w',
            '6M', etc.
        max_entries (int):
            Maximum number of log entries to keep.
        min_entries (int):
            Minimum number of log entries to keep.
        retain_temp (bool):
            Do not delete the temporary log file after writing composite log
            file.
        ctime (string, float, datetime):
            Used as the creation time of the log entry.
            If not specified, the current time is used.
        year_header (string):
            When specified, this header is added above the first entry from a new year.
        month_header (string):
            When specified, this header is added above the first entry from a new month.
        day_header (string):
            When specified, this header is added above the first entry from a new day.
        hour_header (string):
            When specified, this header is added above the first entry from a new hour.
        entry_header (string):
            When specified, this header is added above every entry.
        fold_marker_mapping ([str, str]):
            When specified, any instances of the first string in a log file are
            replaced by the second string when incorporating that log into the
            output NestedText file.

    Raises:
        OSError, NTlogError

        *NTlogError* is a clone of the Error_ exception from Inform_.

    The use of *temp_log_file* is optional.  It is helpful with long running 
    processes as it provides a way of monitoring the progress of the process, 
    especially if the logfile is routinely flushed.

    Example (no temp log with error reporting)::

        from ntlog import NTlog, NTlogError
        from inform import fatal, os_error

        try:
            with NTlog('appname.log.nt', keep_for='7d', max_entries=20):
                ntlog.write('log message')
        except OSError as e:
            fatal(os_error(e))
        except NTlogError as e:
            e.terminate()

    Example (with temp log)::

        with NTlog('appname.log.nt', 'appname.log', keep_for='7d', retain_temp=True):
            ntlog.write('log message')
            ntlog.flush()
            ...

    Example (with inform)::

        from ntlog import NTlog
        from inform import Inform, display, error, log

        with (
            NTlog('appname.log.nt', keep_for='7d') as ntlog,
            Inform(logfile=ntlog) as inform,
        ):
            display('status message')
            log('log message')
            if there_is_a_problem:
                error('error message')
            ...

    Example (with temp log and inform)::

        with (
            NTlog('appname.log.nt', 'appname.log', keep_for='7d') as ntlog,
            Inform(logfile=ntlog, flush=True) as inform,
        ):
            display('status message')
            log('log message')
            if there_is_a_problem:
                error('error message')
            ...

    .. _NestedText: https://nestedtext.org
    .. _Inform: https://inform.readthedocs.io
    .. _Error: https://inform.readthedocs.io/en/stable/api.html#inform.Error
    """

    # constructor {{{2
    def __init__(
        self, running_log_file, temp_log_file=None,
        *,
        keep_for=None, max_entries=None, min_entries=1,
        retain_temp=False, ctime=None,
        year_header=None, month_header=None, day_header=None, hour_header=None,
        entry_header=None, fold_marker_mapping=None
    ):
        self.year_header = year_header
        self.month_header = month_header
        self.day_header = day_header
        self.hour_header = hour_header
        self.entry_header = entry_header
        self.fold_marker_mapping = fold_marker_mapping

        # preliminaries {{{3
        self.log = io.StringIO()
        self.running_log_file = Path(running_log_file)
        self.ctime = ctime
        if is_str(keep_for):
            keep_for = Quantity(keep_for, 'd', scale='s')
        if keep_for:
            oldest = arrow.now().shift(seconds=-keep_for)
        else:
            oldest = arrow.get(0)

        # load running log {{{3
        try:
            running_log = nt.load(self.running_log_file, dict)
        except FileNotFoundError:
            running_log = {}

        # convert keys to time and sort {{{3
        try:
            running_log = {arrow.get(k):v  for k,v in running_log.items()}
        except arrow.ParserError as e:
            raise Error(str(e).partition(' Try passing')[0], culprit=running_log_file)
        running_log = {k:running_log[k] for k in sorted(running_log, reverse=True)}

        # filter running log {{{3
        if len(running_log) >= min_entries:
            truncated_log = {k:v for k,v in running_log.items() if k > oldest}
            if len(truncated_log) < min_entries-1:
                truncated_log = trim_dict(running_log, min_entries-1)
            running_log = truncated_log
        if max_entries and len(running_log) >= max_entries:
            running_log = trim_dict(running_log, max_entries-1)

        self.running_log = running_log

        # open temporary log file {{{3
        if temp_log_file:
            self.temp_log_file = Path(temp_log_file)
            self.temp_log = self.temp_log_file.open('w')
            self.delete_temp = not retain_temp
        else:
            self.temp_log_file = None

    # write() {{{2
    def write(self, text):
        if self.temp_log_file:
            self.temp_log.write(text)
        if self.fold_marker_mapping:
            text = text.replace(*self.fold_marker_mapping)
        self.log.write(text)

    # flush() {{{2
    def flush(self):
        if self.temp_log_file:
            self.temp_log.flush()

    # close() {{{2
    def close(self):
        # create new log entry and add it to running log {{{3
        if self.ctime:
            ctime = arrow.get(self.ctime).to('local')
        else:
            ctime = arrow.get().to('local')
        contents = self.log.getvalue()
        log = {ctime: contents}

        if ctime in self.running_log:
            if contents != self.running_log[ctime]:
                raise Error('attempt to overwrite log entry.', culprit=str(ctime))
        log.update(self.running_log)

        # write out running log {{{3
        self.dump(log)

    def dump(self, log):
        output = []
        year = month = day = hour = None
        for date, text in log.items():

            # add year header if requested
            if self.year_header and date.year != year:
                output.append(create_header(date, self.year_header))
                year = date.year
                month = day = hour = None

            # add month header if requested
            if self.month_header and date.month != month:
                output.append(create_header(date, self.month_header))
                month = date.month
                day = hour = None

            # add day header if requested
            if self.day_header and date.day != day:
                output.append(create_header(date, self.day_header))
                day = date.day
                hour = None

            # add hour header if requested
            if self.hour_header and date.hour != hour:
                output.append(create_header(date, self.hour_header))
                hour = date.hour

            # add entry header if requested
            if self.entry_header:
                output.append(create_header(date, self.entry_header))

            # add entry
            output.append(nt.dumps({date: text}, default=str))
            output.append('')

        self.running_log_file.write_text('\n'.join(output) + '\n')


        # close and remove temp_log {{{3
        if self.temp_log_file:
            self.temp_log.close()
            if self.delete_temp:
                self.temp_log_file.unlink()

    # context manager methods {{{2
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
