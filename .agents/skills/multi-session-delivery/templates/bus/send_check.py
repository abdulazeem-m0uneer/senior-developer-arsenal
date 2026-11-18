"""Check one bus line before send.sh writes it: ETA on everything, evidence on every DONE, weekdays that match dates.

usage: python3 -I send_check.py <message> <sender>
exit 0  ok; stdout holds the open-items record to append (nothing for a line that opens or closes no item):
        <sent at, ISO with offset> TAB <sender> TAB <key, lowercase> TAB <ETA "YYYY-MM-DD HH:MM" local, or DONE> TAB <line>
exit 4  a weekday next to a date is wrong ("Wed 11-26" when 11-26 is a Thursday), or that date does not exist
exit 6  START or BLOCKER without a key or without a valid ETA; DONE or CLEARED without a key and evidence; a
        keyword not in upper case ("Done X"); the old words "started" or "blocked"; an unusable $BUS_NOW
exit 2  wrong number of arguments
Reasons go to stderr. $BUS_NOW (ISO, local time when it has no offset) replaces the clock for tests.

Line forms (leading spaces are ignored; a colon after the keyword is allowed):
  START <key> <what> - ETA [YYYY-MM-DD |MM-DD |MM/DD ]HH:MM          taking an item
  BLOCKER <key> <exact cause> - <who acts> - ETA ...                stopped; the ETA is when it will be solved
  DONE|CLEARED <key> <evidence>                                     merged commit, green run, verified check
A key starts with a letter, a digit or "#"; trailing punctuation is dropped ("#740:" is "#740") and keys compare
in lower case. When a line holds several ETAs, the last one counts. Without a date, a time already past today
means tomorrow; a month-day without a year takes the year that puts it nearest to now. An ETA must not be in the
past nor more than $BUS_ETA_MAX_DAYS days ahead (default 90); times are 24-hour, without am/pm. The weekday
check reads "Thu", "Thur", "Thurs", "Thursday" (and so on) followed by MM-DD, MM/DD or YYYY-MM-DD; single-digit
dates ("Fri 11-6") are not read, since they look like hour ranges ("Mon 9-5"). A two-digit pair can be either: write
hours as times ("Mon 10:00-12:00"). Standard library only.
"""
import datetime as dt
import os
import re
import sys

DAY = (r"(Mon(?:day)?|Tue(?:s|sday)?|Wed(?:s|nesday)?|Thu(?:r|rs|rsday)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)"
       r"(?![\w-])")
# "Thu 11-26", "Monday 2027-01-04", "Wed, 11/26"; not "Mon-Fri", "Tue 10-12 people", "Wed 10-12:30", "Mon 9-5".
WEEKDAY_DATE = re.compile(r"(?<![-\w])" + DAY + r",?\s+(?:(\d{4})-)?(\d{2})[-/](\d{2})"
                          r"(?![\d:/]|-\d|\s*(?:am|pm|h|hrs?|hours?|mins?|minutes?|noon|days?|people|utc|gmt)\b)", re.I)
KEYWORD = re.compile(r"^(START|BLOCKER|DONE|CLEARED)(?::|\b)", re.I)
OLD_WORDS = re.compile(r"^(?:started|blocked)\b", re.I)
ETA = re.compile(r"\bETA:?\s+(?:(?:(\d{4})-)?(\d{1,2})[-/](\d{1,2})\s+)?(\d{1,2}):(\d{2})(?![:\d])"
                 r"(?!\s*\d{1,2}[-/]\d{1,2})(?!\s*[ap]\.?m\b)", re.I)  # 24-hour times only: no am/pm
ETA_WORD = re.compile(r"\bETA\b", re.I)
KEY_SHAPE = re.compile(r"[\w#]")
SPAN_DAYS = 200  # a weekday's date without a year is the one within this many days of today
MAX_DAYS = 90
MAX_DAYS_LIMIT = 36500  # a larger BUS_ETA_MAX_DAYS would overflow the date arithmetic


class Refused(Exception):
    def __init__(self, code, reason):
        super().__init__(reason)
        self.code = code


def weekday_errors(message, today):
    errors = []
    for name, year, month, day in WEEKDAY_DATE.findall(message):
        if year:
            candidates = [int(year)]
        else:
            candidates = [today.year - 1, today.year, today.year + 1]
        dates = []
        for candidate in candidates:
            try:
                dates.append(dt.date(candidate, int(month), int(day)))
            except ValueError:
                continue
        if not year:  # the one date meant: the nearest, if it is near at all
            dates = sorted((date for date in dates if abs((date - today).days) <= SPAN_DAYS),
                           key=lambda date: abs((date - today).days))[:1]
        if not dates:
            errors.append(f"{name} {month}-{day}: no such date")
        elif dates[0].strftime("%a").lower() != name[:3].lower():
            errors.append(f"{name} {dates[0]}: that date is a {dates[0].strftime('%A')}")
    return errors


def nearest_year(month, day, hour, minute, now):
    """The datetime with this month and day nearest to now (last, this or next year); None if it never exists."""
    found = []
    for year in (now.year - 1, now.year, now.year + 1):
        try:
            found.append(dt.datetime(year, month, day, hour, minute))
        except ValueError:  # 02-29 outside a leap year
            continue
    return min(found, key=lambda at: abs(at - now)) if found else None


def max_days():
    value = os.environ.get("BUS_ETA_MAX_DAYS") or MAX_DAYS
    try:
        days = int(value)
    except ValueError:
        days = 0
    if not 1 <= days <= MAX_DAYS_LIMIT:
        raise Refused(6, f"BUS_ETA_MAX_DAYS {value!r} is not a whole number of days from 1 to {MAX_DAYS_LIMIT}")
    return days


def eta_of(message, now):
    """The ETA as a local datetime; raises Refused when it is missing or not usable."""
    matches = list(ETA.finditer(message))
    if not matches:
        if ETA_WORD.search(message):
            raise Refused(6, "the ETA is not 'ETA HH:MM' or 'ETA MM-DD HH:MM' (24-hour time, no seconds, no am/pm, "
                             "nothing date-like right after it)")
        raise Refused(6, "a START or BLOCKER line needs 'ETA HH:MM' or 'ETA MM-DD HH:MM' (when it will be done)")
    year, month, day, hour, minute = matches[-1].groups()
    hour, minute = int(hour), int(minute)
    if hour > 23 or minute > 59:
        raise Refused(6, f"ETA time {hour}:{minute:02d} does not exist")
    this_minute = now.replace(second=0, microsecond=0)
    if month is None:
        at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        at = at + dt.timedelta(days=1) if at < this_minute else at
    else:
        month, day = int(month), int(day)
        if year:
            try:
                at = dt.datetime(int(year), month, day, hour, minute)
            except ValueError:
                at = None
        else:
            at = nearest_year(month, day, hour, minute, now)
        if at is None:
            raise Refused(6, f"ETA date {month:02d}-{day:02d} does not exist")
        if at < this_minute:
            raise Refused(6, f"ETA {at:%Y-%m-%d %H:%M} has already passed; give the new time")
    limit = max_days()
    if at > now + dt.timedelta(days=limit):
        raise Refused(6, f"ETA {at:%Y-%m-%d %H:%M} is more than {limit} days ahead; split the item or give a "
                         "nearer time")
    return at


def key_of(word, keyword):
    key = word.rstrip(":,;.)")
    if not KEY_SHAPE.match(key) or key.upper() == "ETA":
        raise Refused(6, f"'{keyword} <key> ...': the key must start with a letter, a digit or '#'")
    return key.lower()


def check(message, sender, now):
    """The open-items record for the line ('' when it opens or closes nothing); raises Refused."""
    message = message.strip()
    bad = weekday_errors(message, now.date())
    if bad:
        raise Refused(4, "a weekday does not match its date (check with a calendar): " + "; ".join(bad)
                      + ". If these numbers are hours, write them as times: 10:00-12:00")
    if OLD_WORDS.match(message):
        raise Refused(6, "use 'START <key> <what> - ETA HH:MM' or 'BLOCKER <key> <cause> - <who> - ETA HH:MM' "
                         "instead of 'started' or 'blocked'")
    found = KEYWORD.match(message)
    if not found:
        return ""
    keyword = found.group(1)
    if keyword != keyword.upper():
        raise Refused(6, f"write the keyword in upper case: {keyword.upper()} (a lower-case one would skip the check)")
    words = message[found.end():].split()
    text = " ".join(message.split())  # one line, no tabs: the record is tab-separated
    sent = now.astimezone().isoformat(timespec="seconds")
    if keyword in ("START", "BLOCKER"):
        if not words:
            raise Refused(6, f"'{keyword} <key> <what> - ETA HH:MM': no key")
        key = key_of(words[0], keyword)
        return "\t".join([sent, sender, key, f"{eta_of(message, now):%Y-%m-%d %H:%M}", text])
    if not words or not any(re.search(r"\w", word) for word in words[1:]):
        raise Refused(6, f"'{keyword} <key> <evidence>': the merged commit, green run or check that proves it")
    return "\t".join([sent, sender, key_of(words[0], keyword), "DONE", text])


def clock():
    value = os.environ.get("BUS_NOW")
    if not value:
        return dt.datetime.now()
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        raise Refused(6, f"BUS_NOW is not an ISO time ({value}); it is for tests: unset it") from None
    return parsed.astimezone().replace(tzinfo=None) if parsed.tzinfo else parsed


def main(argv):
    if len(argv) != 3:
        print("usage: send_check.py <message> <sender>", file=sys.stderr)
        return 2
    try:
        record = check(argv[1], argv[2], clock())
    except Refused as refusal:
        print(f"refused: {refusal}", file=sys.stderr)
        return refusal.code
    if record:
        print(record)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
