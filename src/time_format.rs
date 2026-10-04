//! loguru-compatible `{time:<spec>}` formatting.
//!
//! The spec is compiled once (at handler creation) into a [`TimeSpec`]; rendering a record
//! only walks the precompiled pieces.

use std::fmt::{Display, Write as _};

use chrono::format::{Item, StrftimeItems};
use chrono::{DateTime, Datelike, NaiveDateTime, Offset, TimeZone, Timelike, Utc};

const MONTH_NAMES: [&str; 12] = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
];
const MONTH_ABBRS: [&str; 12] = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];
const DAY_NAMES: [&str; 7] = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
];
const DAY_ABBRS: [&str; 7] = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/// loguru's spec for `{time:}` (empty spec): ISO 8601 with microseconds and offset
const ISO_STRFTIME: &str = "%Y-%m-%dT%H:%M:%S%.6f%z";

/// One piece of a compiled loguru time pattern
#[derive(Clone, Debug, PartialEq, Eq)]
enum TimePiece {
    Literal(String),
    /// YYYY
    Year,
    /// YY
    YearShort,
    /// Q
    Quarter,
    /// MMMM
    MonthName,
    /// MMM
    MonthAbbr,
    /// MM / M
    Month {
        pad: bool,
    },
    /// DDDD / DDD
    DayOfYear {
        pad: bool,
    },
    /// DD / D
    Day {
        pad: bool,
    },
    /// dddd
    WeekdayName,
    /// ddd
    WeekdayAbbr,
    /// d (Monday = 0) / E (Monday = 1)
    Weekday {
        from_one: bool,
    },
    /// HH / H
    Hour {
        pad: bool,
    },
    /// hh / h
    Hour12 {
        pad: bool,
    },
    /// mm / m
    Minute {
        pad: bool,
    },
    /// ss / s
    Second {
        pad: bool,
    },
    /// S .. SSSSSS: fraction of second with the given number of digits
    Fraction(u8),
    /// A
    AmPm,
    /// Z (`+09:00`) / ZZ (`+0900`)
    Offset {
        colon: bool,
    },
    /// zz
    TzName,
    /// X
    UnixSeconds,
    /// x
    UnixMicros,
}

#[derive(Clone, Debug)]
enum TimePattern {
    /// loguru tokens (`YYYY-MM-DD`)
    Pieces(Vec<TimePiece>),
    /// strftime directives (spec contains `%`), validated at compile time
    Strftime(String),
}

/// A compiled `{time:<spec>}` format
#[derive(Clone, Debug)]
pub struct TimeSpec {
    utc: bool,
    pattern: TimePattern,
}

/// Length of the loguru token at the start of `s`, if any.
///
/// Mirrors loguru's ordered regex alternation
/// `H{1,2}|h{1,2}|m{1,2}|s{1,2}|S+|YYYY|YY|M{1,4}|D{1,4}|Z{1,2}|zz|A|X|x|E|Q|dddd|ddd|d`.
fn match_token(s: &str) -> Option<usize> {
    let bytes = s.as_bytes();
    let first = *bytes.first()?;
    let run = |c: u8, max: usize| bytes.iter().take(max).take_while(|&&b| b == c).count();
    match first {
        b'H' | b'h' | b'm' | b's' => Some(run(first, 2)),
        b'S' => Some(run(b'S', usize::MAX)),
        b'Y' => {
            if s.starts_with("YYYY") {
                Some(4)
            } else if s.starts_with("YY") {
                Some(2)
            } else {
                None
            }
        }
        b'M' | b'D' => Some(run(first, 4)),
        b'Z' => Some(run(b'Z', 2)),
        b'z' => s.starts_with("zz").then_some(2),
        b'A' | b'X' | b'x' | b'E' | b'Q' => Some(1),
        b'd' => {
            if s.starts_with("dddd") {
                Some(4)
            } else if s.starts_with("ddd") {
                Some(3)
            } else {
                Some(1)
            }
        }
        _ => None,
    }
}

/// True if `s` as a whole is matched by one alternative of the token regex
fn is_whole_token(s: &str) -> bool {
    if s.is_empty() || s == "!UTC" {
        return true;
    }
    let Some(&first) = s.as_bytes().first() else {
        return false;
    };
    let all_same = s.bytes().all(|b| b == first);
    match first {
        b'H' | b'h' | b'm' | b's' | b'Z' => all_same && s.len() <= 2,
        b'S' => all_same,
        b'M' | b'D' => all_same && s.len() <= 4,
        _ => matches!(
            s,
            "YYYY" | "YY" | "zz" | "A" | "X" | "x" | "E" | "Q" | "dddd" | "ddd" | "d"
        ),
    }
}

fn token_piece(token: &str) -> Option<TimePiece> {
    use TimePiece::*;
    Some(match token {
        "YYYY" => Year,
        "YY" => YearShort,
        "Q" => Quarter,
        "MMMM" => MonthName,
        "MMM" => MonthAbbr,
        "MM" => Month { pad: true },
        "M" => Month { pad: false },
        "DDDD" => DayOfYear { pad: true },
        "DDD" => DayOfYear { pad: false },
        "DD" => Day { pad: true },
        "D" => Day { pad: false },
        "dddd" => WeekdayName,
        "ddd" => WeekdayAbbr,
        "d" => Weekday { from_one: false },
        "E" => Weekday { from_one: true },
        "HH" => Hour { pad: true },
        "H" => Hour { pad: false },
        "hh" => Hour12 { pad: true },
        "h" => Hour12 { pad: false },
        "mm" => Minute { pad: true },
        "m" => Minute { pad: false },
        "ss" => Second { pad: true },
        "s" => Second { pad: false },
        "A" => AmPm,
        "Z" => Offset { colon: true },
        "ZZ" => Offset { colon: false },
        "zz" => TzName,
        "X" => UnixSeconds,
        "x" => UnixMicros,
        _ if !token.is_empty() && token.len() <= 6 && token.bytes().all(|b| b == b'S') => {
            Fraction(token.len() as u8)
        }
        _ => return None,
    })
}

fn push_literal(pieces: &mut Vec<TimePiece>, text: &str) {
    if text.is_empty() {
        return;
    }
    if let Some(TimePiece::Literal(prev)) = pieces.last_mut() {
        prev.push_str(text);
    } else {
        pieces.push(TimePiece::Literal(text.to_string()));
    }
}

/// Translate a Python strftime spec to chrono (`%f` is microseconds in Python)
fn python_strftime_to_chrono(spec: &str) -> Result<String, String> {
    let mut out = String::with_capacity(spec.len() + 2);
    let mut chars = spec.chars();
    while let Some(c) = chars.next() {
        if c != '%' {
            out.push(c);
            continue;
        }
        match chars.next() {
            Some('f') => out.push_str("%6f"),
            Some(other) => {
                out.push('%');
                out.push(other);
            }
            None => out.push('%'),
        }
    }
    if StrftimeItems::new(&out).any(|item| matches!(item, Item::Error)) {
        return Err(format!(
            "Invalid time format: unsupported strftime directive in {spec:?}"
        ));
    }
    Ok(out)
}

impl TimeSpec {
    /// Compile a loguru time spec (the part after `time:` in `{time:...}`)
    pub fn parse(spec: &str) -> Result<Self, String> {
        let (spec, utc) = match spec.strip_suffix("!UTC") {
            Some(rest) => (rest, true),
            None => (spec, false),
        };

        if spec.is_empty() {
            return Ok(TimeSpec {
                utc,
                pattern: TimePattern::Strftime(ISO_STRFTIME.to_string()),
            });
        }
        if spec.contains('%') {
            return Ok(TimeSpec {
                utc,
                pattern: TimePattern::Strftime(python_strftime_to_chrono(spec)?),
            });
        }
        if spec.contains("SSSSSSS") {
            return Err(
                "Invalid time format: the provided format string contains more than six \
                 successive 'S' characters. This may be due to an attempt to use nanosecond \
                 precision, which is not supported."
                    .to_string(),
            );
        }

        let mut pieces = Vec::new();
        let mut rest = spec;
        while !rest.is_empty() {
            if let Some(len) = match_token(rest) {
                let token = &rest[..len];
                match token_piece(token) {
                    Some(piece) => pieces.push(piece),
                    None => push_literal(&mut pieces, token),
                }
                rest = &rest[len..];
                continue;
            }
            if rest.starts_with('[')
                && let Some(close) = rest.find(']')
                && is_whole_token(&rest[1..close])
            {
                // `[TOKEN]` escapes a token
                push_literal(&mut pieces, &rest[1..close]);
                rest = &rest[close + 1..];
                continue;
            }
            let ch_len = rest.chars().next().map_or(1, char::len_utf8);
            push_literal(&mut pieces, &rest[..ch_len]);
            rest = &rest[ch_len..];
        }

        Ok(TimeSpec {
            utc,
            pattern: TimePattern::Pieces(pieces),
        })
    }

    /// Render `dt` according to the spec
    pub fn write<Tz: TimeZone>(&self, dt: &DateTime<Tz>, out: &mut String)
    where
        Tz::Offset: Display,
    {
        if self.utc {
            self.write_in(&dt.with_timezone(&Utc), out);
        } else {
            self.write_in(dt, out);
        }
    }

    /// Render `dt` into a new string
    pub fn format<Tz: TimeZone>(&self, dt: &DateTime<Tz>) -> String
    where
        Tz::Offset: Display,
    {
        let mut out = String::with_capacity(32);
        self.write(dt, &mut out);
        out
    }

    fn write_in<Tz: TimeZone>(&self, dt: &DateTime<Tz>, out: &mut String)
    where
        Tz::Offset: Display,
    {
        match &self.pattern {
            TimePattern::Strftime(fmt) => {
                let _ = write!(out, "{}", dt.format(fmt));
            }
            TimePattern::Pieces(pieces) => {
                // Resolve the local date/time once, not per piece
                let local = dt.naive_local();
                for piece in pieces {
                    write_piece(piece, dt, &local, self.utc, out);
                }
            }
        }
    }
}

/// Append `value` in decimal, zero-padded to `width` digits
fn push_num(out: &mut String, mut value: u64, width: usize) {
    let mut buf = [0u8; 20];
    let mut start = buf.len();
    loop {
        start -= 1;
        buf[start] = b'0' + (value % 10) as u8;
        value /= 10;
        if value == 0 {
            break;
        }
    }
    for _ in buf.len() - start..width {
        out.push('0');
    }
    for &digit in &buf[start..] {
        out.push(char::from(digit));
    }
}

/// Append a signed `value` (no padding)
fn push_signed(out: &mut String, value: i64) {
    if value < 0 {
        out.push('-');
    }
    push_num(out, value.unsigned_abs(), 0);
}

#[inline]
fn width(pad: bool, padded: usize) -> usize {
    if pad { padded } else { 0 }
}

fn write_offset(out: &mut String, offset_secs: i32, colon: bool) {
    out.push(if offset_secs >= 0 { '+' } else { '-' });
    let abs = u64::from(offset_secs.unsigned_abs());
    push_num(out, abs / 3600, 2);
    if colon {
        out.push(':');
    }
    push_num(out, (abs % 3600) / 60, 2);
    if abs % 60 > 0 {
        if colon {
            out.push(':');
        }
        push_num(out, abs % 60, 2);
    }
}

fn write_piece<Tz: TimeZone>(
    piece: &TimePiece,
    dt: &DateTime<Tz>,
    local: &NaiveDateTime,
    utc: bool,
    out: &mut String,
) where
    Tz::Offset: Display,
{
    match piece {
        TimePiece::Literal(s) => out.push_str(s),
        TimePiece::Year => {
            let year = local.year();
            if year >= 0 {
                push_num(out, year as u64, 4);
            } else {
                push_signed(out, i64::from(year));
            }
        }
        TimePiece::YearShort => push_num(out, local.year().rem_euclid(100) as u64, 2),
        TimePiece::Quarter => push_num(out, u64::from(local.month0() / 3 + 1), 0),
        TimePiece::MonthName => out.push_str(MONTH_NAMES[local.month0() as usize]),
        TimePiece::MonthAbbr => out.push_str(MONTH_ABBRS[local.month0() as usize]),
        TimePiece::Month { pad } => push_num(out, u64::from(local.month()), width(*pad, 2)),
        TimePiece::DayOfYear { pad } => push_num(out, u64::from(local.ordinal()), width(*pad, 3)),
        TimePiece::Day { pad } => push_num(out, u64::from(local.day()), width(*pad, 2)),
        TimePiece::WeekdayName => {
            out.push_str(DAY_NAMES[local.weekday().num_days_from_monday() as usize])
        }
        TimePiece::WeekdayAbbr => {
            out.push_str(DAY_ABBRS[local.weekday().num_days_from_monday() as usize])
        }
        TimePiece::Weekday { from_one } => push_num(
            out,
            u64::from(local.weekday().num_days_from_monday() + u32::from(*from_one)),
            0,
        ),
        TimePiece::Hour { pad } => push_num(out, u64::from(local.hour()), width(*pad, 2)),
        TimePiece::Hour12 { pad } => push_num(out, u64::from(local.hour12().1), width(*pad, 2)),
        TimePiece::Minute { pad } => push_num(out, u64::from(local.minute()), width(*pad, 2)),
        TimePiece::Second { pad } => push_num(out, u64::from(local.second()), width(*pad, 2)),
        TimePiece::Fraction(digits) => {
            // Leap seconds are reported as nanosecond >= 1e9
            let micros = (local.nanosecond() % 1_000_000_000) / 1_000;
            let digits = u32::from(*digits);
            push_num(
                out,
                u64::from(micros / 10u32.pow(6 - digits)),
                digits as usize,
            );
        }
        TimePiece::AmPm => out.push_str(if local.hour() < 12 { "AM" } else { "PM" }),
        TimePiece::Offset { colon } => {
            write_offset(out, dt.offset().fix().local_minus_utc(), *colon)
        }
        TimePiece::TzName => {
            if utc {
                out.push_str("UTC");
            } else {
                // chrono has no zone abbreviation for local time: use the offset
                let _ = write!(out, "{}", dt.offset());
            }
        }
        TimePiece::UnixSeconds => push_signed(out, dt.timestamp()),
        TimePiece::UnixMicros => push_signed(out, dt.timestamp_micros()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::FixedOffset;

    fn sample() -> DateTime<FixedOffset> {
        // 2024-03-05 (Tuesday) 14:07:09.123456 +09:00
        DateTime::parse_from_rfc3339("2024-03-05T14:07:09.123456+09:00").unwrap()
    }

    fn fmt(spec: &str) -> String {
        TimeSpec::parse(spec).unwrap().format(&sample())
    }

    #[test]
    fn test_date_tokens() {
        assert_eq!(fmt("YYYY-MM-DD"), "2024-03-05");
        assert_eq!(fmt("YY/M/D"), "24/3/5");
        assert_eq!(fmt("MMMM MMM Q"), "March Mar 1");
        assert_eq!(fmt("DDDD DDD"), "065 65");
        assert_eq!(fmt("dddd ddd d E"), "Tuesday Tue 1 2");
    }

    #[test]
    fn test_time_tokens() {
        assert_eq!(fmt("HH:mm:ss"), "14:07:09");
        assert_eq!(fmt("H:m:s"), "14:7:9");
        assert_eq!(fmt("hh h A"), "02 2 PM");
        assert_eq!(
            fmt("S SS SSS SSSS SSSSS SSSSSS"),
            "1 12 123 1234 12345 123456"
        );
        assert_eq!(fmt("YYYY-MM-DD HH:mm:ss.SSS"), "2024-03-05 14:07:09.123");
    }

    #[test]
    fn test_timezone_tokens() {
        assert_eq!(fmt("Z"), "+09:00");
        assert_eq!(fmt("ZZ"), "+0900");
        assert_eq!(fmt("HH:mm Z!UTC"), "05:07 +00:00");
        assert_eq!(fmt("zz!UTC"), "UTC");
        assert_eq!(fmt("X"), sample().timestamp().to_string());
        assert_eq!(fmt("x"), sample().timestamp_micros().to_string());
    }

    #[test]
    fn test_escapes_and_literals() {
        assert_eq!(fmt("[YYYY] YYYY"), "YYYY 2024");
        assert_eq!(
            fmt("[]x[!UTC]"),
            format!("{}!UTC", sample().timestamp_micros())
        );
        // Brackets around non-tokens stay literal, tokens inside are still replaced
        assert_eq!(fmt("[at] HH"), "[at] 14");
        assert_eq!(fmt("YYY"), "24Y");
        assert_eq!(fmt("T"), "T");
        assert_eq!(fmt("日付 YYYY"), "日付 2024");
    }

    #[test]
    fn test_strftime_and_empty_spec() {
        assert_eq!(fmt("%Y-%m-%d %H:%M:%S.%f"), "2024-03-05 14:07:09.123456");
        assert_eq!(fmt(""), "2024-03-05T14:07:09.123456+0900");
        assert_eq!(fmt("!UTC"), "2024-03-05T05:07:09.123456+0000");
        assert!(TimeSpec::parse("%Q").is_err());
    }

    #[test]
    fn test_nanosecond_precision_rejected() {
        assert!(TimeSpec::parse("SSSSSSS").is_err());
    }
}
