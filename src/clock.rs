//! Record timestamps.
//!
//! `Local::now()` reads the system clock twice: once for the instant and once
//! more inside chrono's local-offset cache, which re-checks the time zone
//! source about once a second. The local offset only depends on the UTC
//! second (zone transitions fall on whole seconds), so [`local_now`] reads the
//! clock once and reuses the offset chrono gave for the current second. The
//! zone is still re-read by chrono whenever the second changes, so `TZ` or
//! `/etc/localtime` updates propagate within a second, as with `Local::now()`.

use std::sync::atomic::{AtomicU64, Ordering};

use chrono::{DateTime, FixedOffset, Local, TimeZone, Utc};

/// Number of low bits holding the biased offset; the UTC second takes the rest.
const OFFSET_BITS: u32 = 20;
const OFFSET_MASK: u64 = (1 << OFFSET_BITS) - 1;
/// Offsets are within ±1 day, so the biased value fits in `OFFSET_BITS`.
const OFFSET_BIAS: i32 = 1 << (OFFSET_BITS - 1);
/// No biased offset is all ones, so this never matches a real entry.
const EMPTY: u64 = u64::MAX;

/// `(UTC epoch second << OFFSET_BITS) | (offset seconds + OFFSET_BIAS)` of the
/// last lookup. One word, so readers never see a torn pair.
static OFFSET_CACHE: AtomicU64 = AtomicU64::new(EMPTY);

/// The current local time; equal to `Local::now()` with one clock read.
#[inline]
pub fn local_now() -> DateTime<Local> {
    local_from_utc(Utc::now())
}

/// `utc` in local time; equal to `utc.with_timezone(&Local)`.
#[inline]
pub fn local_from_utc(utc: DateTime<Utc>) -> DateTime<Local> {
    let naive = utc.naive_utc();
    let secs = utc.timestamp();
    let offset = match cached_offset(secs) {
        Some(offset) => offset,
        None => lookup_offset(&utc, secs),
    };
    DateTime::from_naive_utc_and_offset(naive, offset)
}

#[inline]
fn cached_offset(secs: i64) -> Option<FixedOffset> {
    let packed = OFFSET_CACHE.load(Ordering::Relaxed);
    if packed == EMPTY || (packed as i64) >> OFFSET_BITS != secs {
        return None;
    }
    FixedOffset::east_opt((packed & OFFSET_MASK) as i32 - OFFSET_BIAS)
}

/// Ask chrono for the offset at `utc` and remember it for its second.
#[cold]
fn lookup_offset(utc: &DateTime<Utc>, secs: i64) -> FixedOffset {
    let offset = Local.offset_from_utc_datetime(&utc.naive_utc());
    let biased = (offset.local_minus_utc() + OFFSET_BIAS) as u64 & OFFSET_MASK;
    OFFSET_CACHE.store(((secs as u64) << OFFSET_BITS) | biased, Ordering::Relaxed);
    offset
}

#[cfg(test)]
fn reset_cache() {
    OFFSET_CACHE.store(EMPTY, Ordering::Relaxed);
}

/// Shared by every test that changes the process-wide `TZ` variable.
#[cfg(all(test, unix))]
pub(crate) mod tz_test {
    use std::sync::Mutex;

    static TZ_LOCK: Mutex<()> = Mutex::new(());

    /// Run `f` on a fresh thread (chrono caches the zone per thread) with
    /// `TZ=tz`, then restore the previous `TZ`. Calls are serialized across
    /// the whole crate because the environment is process-wide.
    pub(crate) fn with_tz(tz: &str, f: impl FnOnce() + Send) {
        let _guard = TZ_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        let previous = std::env::var_os("TZ");
        // SAFETY: tests touching the environment are serialized by `TZ_LOCK`
        unsafe { std::env::set_var("TZ", tz) };
        super::reset_cache();
        std::thread::scope(|scope| {
            scope.spawn(f);
        });
        // SAFETY: as above
        unsafe {
            match previous {
                Some(value) => std::env::set_var("TZ", value),
                None => std::env::remove_var("TZ"),
            }
        }
        super::reset_cache();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn matches_local_now() {
        let a = local_now();
        let b = Local::now();
        assert_eq!(a.offset(), b.offset());
        assert!((b - a).num_milliseconds().abs() < 1000);
        // Second call hits the cache for this second
        let c = local_now();
        assert_eq!(c.offset(), b.offset());
    }

    #[test]
    fn packs_extreme_offsets_and_seconds() {
        for secs in [-1i64, 0, 1, -86_400 * 365 * 100, 253_402_300_799] {
            for offset in [-86_399, -43_200, 0, 19_800, 50_400, 86_399] {
                let biased = (offset + OFFSET_BIAS) as u64 & OFFSET_MASK;
                let packed = ((secs as u64) << OFFSET_BITS) | biased;
                assert_eq!((packed as i64) >> OFFSET_BITS, secs);
                assert_eq!((packed & OFFSET_MASK) as i32 - OFFSET_BIAS, offset);
                assert_ne!(packed, EMPTY);
            }
        }
    }

    /// `TZ` is process-wide, so these tests run one at a time and restore it.
    #[cfg(unix)]
    mod with_tz {
        use chrono::{Duration, Offset};

        use super::*;

        use crate::clock::tz_test::with_tz;

        fn utc(s: &str) -> DateTime<Utc> {
            DateTime::parse_from_rfc3339(s).unwrap().with_timezone(&Utc)
        }

        /// Compare against chrono around `transition`, including repeated
        /// instants within one second (cache hits) and the roll-over between
        /// seconds (cache misses).
        fn check_around(transition: DateTime<Utc>) -> (FixedOffset, FixedOffset) {
            let steps = [
                -2_000_000_000i64,
                -1_000_000_000,
                -999_999_999,
                -500_000_000,
                -1,
                0,
                1,
                500_000_000,
                999_999_999,
                1_000_000_000,
                2_000_000_000,
            ];
            for nanos in steps {
                let t = transition + Duration::nanoseconds(nanos);
                for _ in 0..2 {
                    let ours = local_from_utc(t);
                    let chrono = t.with_timezone(&Local);
                    assert_eq!(ours, chrono, "{t}");
                    assert_eq!(ours.offset().fix(), chrono.offset().fix(), "{t}");
                    assert_eq!(ours.naive_local(), chrono.naive_local(), "{t}");
                }
            }
            let before = (transition - Duration::seconds(1)).with_timezone(&Local);
            let after = transition.with_timezone(&Local);
            (before.offset().fix(), after.offset().fix())
        }

        #[test]
        fn posix_rule_dst_transitions() {
            // Needs no zoneinfo files, so the offsets are known to change
            with_tz("EST5EDT,M3.2.0,M11.1.0", || {
                let (before, after) = check_around(utc("2024-03-10T07:00:00Z"));
                assert_eq!(before.local_minus_utc(), -5 * 3600);
                assert_eq!(after.local_minus_utc(), -4 * 3600);
                let (before, after) = check_around(utc("2024-11-03T06:00:00Z"));
                assert_eq!(before.local_minus_utc(), -4 * 3600);
                assert_eq!(after.local_minus_utc(), -5 * 3600);
            });
        }

        #[test]
        fn zoneinfo_dst_transitions() {
            let zones: [(&str, &[&str]); 5] = [
                (
                    "America/New_York",
                    &["2024-03-10T07:00:00Z", "2024-11-03T06:00:00Z"],
                ),
                (
                    "Europe/Berlin",
                    &["2024-03-31T01:00:00Z", "2024-10-27T01:00:00Z"],
                ),
                (
                    "Australia/Sydney",
                    &["2024-04-06T16:00:00Z", "2024-10-05T16:00:00Z"],
                ),
                ("Asia/Kolkata", &["2024-03-10T07:00:00Z"]),
                ("UTC", &["2024-03-10T07:00:00Z"]),
            ];
            let have_zoneinfo = std::path::Path::new("/usr/share/zoneinfo/Europe/Berlin").exists();
            for (zone, transitions) in zones {
                with_tz(zone, || {
                    for &t in transitions {
                        let (before, after) = check_around(utc(t));
                        if have_zoneinfo && zone != "Asia/Kolkata" && zone != "UTC" {
                            assert_ne!(before, after, "{zone} {t}");
                        }
                    }
                });
            }
        }

        #[test]
        fn zone_change_is_picked_up_on_the_next_second() {
            let t = utc("2024-06-01T12:00:00Z");
            with_tz("UTC", || {
                assert_eq!(local_from_utc(t).offset().fix().local_minus_utc(), 0);
            });
            with_tz("EST5EDT,M3.2.0,M11.1.0", || {
                // Same second as before: the cache was reset with the zone
                assert_eq!(
                    local_from_utc(t).offset().fix().local_minus_utc(),
                    -4 * 3600
                );
                // A later second is looked up afresh
                let later = t + Duration::seconds(1);
                assert_eq!(local_from_utc(later), later.with_timezone(&Local));
            });
        }
    }
}
