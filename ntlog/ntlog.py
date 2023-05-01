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
# Copyright (c) 2020-2023 Ken Kundert
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
def trim_dict(d, max_entries):
    # trim the dictionary such that it contains only the max_entries most
    # recently added items
    return dict(list(d.items())[:max_entries])


# NTlog class {{{1
class NTlog:
    # description {{{3
    """ NTlog

    NTlog instances can be used as an output file stream, but instead of writing
    to stand-alone files their output is incorporated into a NestedText logfile.

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

    Raises:
        OSError, NTlogError

        *NTlogError* is a clone of the *Error* exception from
        `Inform <https://inform.readthedocs.io/en/stable/api.html#inform.Error>`_.

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
            ...

    Example (with inform)::

        from ntlog import NTlog
        from inform import Inform, error, log

        with (
            NTlog('appname.log.nt', keep_for='7d') as ntlog,
            Inform(logfile=ntlog) as inform,
        ):
            log('log message')
            if there_is_a_problem:
                error('error message')
            ...

    Example (with temp log and inform)::

        with (
            NTlog('appname.log.nt', 'appname.log', keep_for='7d') as ntlog,
            Inform(logfile=ntlog, flush=True) as inform,
        ):
            log('log message')
            if there_is_a_problem:
                error('error message')
            ...

    """

    # constructor {{{3
    def __init__(
        self, running_log_file, temp_log_file=None,
        *,
        keep_for=None, max_entries=None, min_entries=1,
        retain_temp=False, ctime=None
    ):
        self.log = io.StringIO()
        self.running_log_file = Path(running_log_file)
        self.ctime = ctime
        if is_str(keep_for):
            keep_for = Quantity(keep_for, 'd', scale='s')
        if keep_for:
            oldest = arrow.now().shift(seconds=-keep_for)
        else:
            oldest = arrow.get(0)

        # load running log
        try:
            running_log = nt.load(self.running_log_file, dict)
        except FileNotFoundError:
            running_log = {}

        # convert keys to time and sort
        try:
            running_log = {arrow.get(k):v  for k,v in running_log.items()}
        except arrow.ParserError as e:
            raise Error(str(e).partition(' Try passing')[0], culprit=running_log_file)
        running_log = {k:running_log[k] for k in sorted(running_log, reverse=True)}

        # filter running log
        if len(running_log) >= min_entries:
            truncated_log = {k:v for k,v in running_log.items() if k > oldest}
            if len(truncated_log) < min_entries-1:
                truncated_log = trim_dict(running_log, min_entries-1)
            running_log = truncated_log
        if max_entries and len(running_log) >= max_entries:
            running_log = trim_dict(running_log, max_entries-1)

        self.running_log = running_log

        # open temporary log file
        if temp_log_file:
            self.temp_log_file = Path(temp_log_file)
            self.temp_log = self.temp_log_file.open('w')
            self.delete_temp = not retain_temp
        else:
            self.temp_log_file = None

    # write() {{{3
    def write(self, text):
        if self.temp_log_file:
            self.temp_log.write(text)
        self.log.write(text)

    # flush() {{{3
    def flush(self):
        if self.temp_log_file:
            self.temp_log.flush()

    # close() {{{3
    def close(self):
        # create new log entry and add it to running log
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

        # write out running log
        nt.dump(log, self.running_log_file, default=str)

        # close and remove temp_log
        if self.temp_log_file:
            self.temp_log.close()
            if self.delete_temp:
                self.temp_log_file.unlink()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
