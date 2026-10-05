//! loguru-shaped values for the record dict passed to filters and raw callbacks.
//!
//! Only the paths that already build a full record dict call into this module;
//! the default (no filter, no callback) logging path never does.
//!
//! The level, file, thread and process values are cached per distinct value, so
//! a record usually costs a few hash lookups plus one `datetime` and one
//! `timedelta` construction.

use std::collections::HashMap;
use std::sync::atomic::Ordering;
use std::sync::{LazyLock, Mutex};

use chrono::{DateTime, Datelike, Local, Offset, Timelike};
use pyo3::intern;
use pyo3::prelude::*;
use pyo3::sync::PyOnceLock;
use pyo3::types::{PyDateTime, PyDelta, PyDict, PyTzInfo};

use crate::format::LOGGER_START_TIME;
use crate::handler::LogRecord;
use crate::level::{LEVEL_GENERATION, get_level_info};

/// Bound the per-value caches so unusual workloads (many threads, generated
/// file names) cannot grow them without limit.
const CACHE_LIMIT: usize = 1024;

/// Python classes from `logust._record`
struct RecordTypes {
    level: Py<PyAny>,
    file: Py<PyAny>,
    thread: Py<PyAny>,
    process: Py<PyAny>,
    elapsed: Py<PyAny>,
}

/// `None` if `logust._record` cannot be imported (plain values are used instead)
static RECORD_TYPES: PyOnceLock<Option<RecordTypes>> = PyOnceLock::new();

fn record_types(py: Python<'_>) -> Option<&RecordTypes> {
    RECORD_TYPES
        .get_or_init(py, || {
            let module = py.import("logust._record").ok()?;
            let get = |name: &str| module.getattr(name).ok().map(Bound::unbind);
            Some(RecordTypes {
                level: get("RecordLevelStr")?,
                file: get("RecordFile")?,
                thread: get("RecordThread")?,
                process: get("RecordProcess")?,
                elapsed: get("RecordElapsed")?,
            })
        })
        .as_ref()
}

#[derive(Default)]
struct Caches {
    /// Level registry generation the level cache was built for
    level_generation: u64,
    levels: HashMap<String, Py<PyAny>>,
    files: HashMap<String, Py<PyAny>>,
    threads: HashMap<u64, (String, Py<PyAny>)>,
    processes: HashMap<u32, (String, Py<PyAny>)>,
    /// `datetime.timezone` for the last seen UTC offset (seconds)
    tz: Option<(i32, Py<PyTzInfo>)>,
}

static CACHES: LazyLock<Mutex<Caches>> = LazyLock::new(|| Mutex::new(Caches::default()));

fn caches() -> std::sync::MutexGuard<'static, Caches> {
    CACHES.lock().unwrap_or_else(|e| e.into_inner())
}

fn insert_bounded<K: std::hash::Hash + Eq, V>(map: &mut HashMap<K, V>, key: K, value: V) {
    if map.len() >= CACHE_LIMIT {
        map.clear();
    }
    map.insert(key, value);
}

/// Cached `RecordLevelStr` for the level `name` (`no`/`icon` resolved on a miss).
///
/// Python objects are created with the cache lock released, so a constructor
/// that releases the GIL cannot deadlock against another logging thread.
fn level_value<'py>(
    py: Python<'py>,
    types: &RecordTypes,
    name: &str,
    record: &LogRecord,
) -> PyResult<Bound<'py, PyAny>> {
    let generation = LEVEL_GENERATION.load(Ordering::Acquire);
    {
        let mut c = caches();
        if c.level_generation != generation {
            c.levels.clear();
            c.level_generation = generation;
        } else if let Some(obj) = c.levels.get(name) {
            return Ok(obj.bind(py).clone());
        }
    }
    let (no, icon) = match record.level_info.as_ref() {
        Some(info) => (info.no, info.icon.clone().unwrap_or_default()),
        None => get_level_info(name).map_or((record.level as u32, String::new()), |info| {
            (info.no, info.icon.unwrap_or_default())
        }),
    };
    let obj = types.level.bind(py).call1((name, no, icon))?;
    let mut c = caches();
    if c.level_generation == generation {
        insert_bounded(&mut c.levels, name.to_owned(), obj.clone().unbind());
    }
    Ok(obj)
}

fn file_value<'py>(
    py: Python<'py>,
    types: &RecordTypes,
    record: &LogRecord,
) -> PyResult<Bound<'py, PyAny>> {
    let path = record.caller.file.as_str();
    if let Some(obj) = caches().files.get(path) {
        return Ok(obj.bind(py).clone());
    }
    let obj = types
        .file
        .bind(py)
        .call1((record.caller.file_name(), path))?;
    insert_bounded(&mut caches().files, path.to_owned(), obj.clone().unbind());
    Ok(obj)
}

fn thread_value<'py>(
    py: Python<'py>,
    types: &RecordTypes,
    record: &LogRecord,
) -> PyResult<Bound<'py, PyAny>> {
    let t = &record.thread;
    if let Some((name, obj)) = caches().threads.get(&t.id)
        && *name == t.name
    {
        return Ok(obj.bind(py).clone());
    }
    let obj = types.thread.bind(py).call1((t.id, t.name.as_str()))?;
    insert_bounded(
        &mut caches().threads,
        t.id,
        (t.name.clone(), obj.clone().unbind()),
    );
    Ok(obj)
}

fn process_value<'py>(
    py: Python<'py>,
    types: &RecordTypes,
    record: &LogRecord,
) -> PyResult<Bound<'py, PyAny>> {
    let p = &record.process;
    if let Some((name, obj)) = caches().processes.get(&p.id)
        && *name == p.name
    {
        return Ok(obj.bind(py).clone());
    }
    let obj = types.process.bind(py).call1((p.id, p.name.as_str()))?;
    insert_bounded(
        &mut caches().processes,
        p.id,
        (p.name.clone(), obj.clone().unbind()),
    );
    Ok(obj)
}

/// Aware `datetime` for the record timestamp (loguru's `record["time"]`)
fn time_value<'py>(py: Python<'py>, ts: &DateTime<Local>) -> PyResult<Bound<'py, PyDateTime>> {
    let offset = ts.offset().fix().local_minus_utc();
    let cached = caches()
        .tz
        .as_ref()
        .filter(|(o, _)| *o == offset)
        .map(|(_, tz)| tz.clone_ref(py));
    let tz = match cached {
        Some(tz) => tz.into_bound(py),
        None => {
            let delta = PyDelta::new(py, 0, offset, 0, true)?;
            let tz = PyTzInfo::fixed_offset(py, delta)?;
            caches().tz = Some((offset, tz.clone().unbind()));
            tz
        }
    };
    PyDateTime::new(
        py,
        ts.year(),
        ts.month() as u8,
        ts.day() as u8,
        ts.hour() as u8,
        ts.minute() as u8,
        // Leap seconds are reported by chrono as second 59 + >1s of nanos
        ts.second().min(59) as u8,
        (ts.nanosecond() / 1_000).min(999_999),
        Some(&tz),
    )
}

/// `RecordElapsed` (a `timedelta`) since logger start, clamped at zero
fn elapsed_value<'py>(
    py: Python<'py>,
    types: &RecordTypes,
    ts: &DateTime<Local>,
) -> PyResult<Bound<'py, PyAny>> {
    let micros = (*ts - *LOGGER_START_TIME)
        .num_microseconds()
        .unwrap_or(i64::MAX)
        .max(0);
    let secs = micros / 1_000_000;
    let days = (secs / 86_400) as i32;
    let secs = (secs % 86_400) as i32;
    let micros = (micros % 1_000_000) as i32;
    types.elapsed.bind(py).call1((days, secs, micros))
}

/// Module name derived from the file name, like loguru's `record["module"]`
fn module_name(file_name: &str) -> &str {
    file_name.rfind('.').map_or(file_name, |i| &file_name[..i])
}

/// Set the loguru-shaped fields (`level`, `file`, `module`, `thread`, `process`,
/// `time`, `elapsed`) on a full record dict.
///
/// Returns `false` if the compat types are unavailable; the caller then sets the
/// plain string values.
pub fn set_compat_fields(
    py: Python<'_>,
    dict: &Bound<'_, PyDict>,
    level_name: &str,
    record: &LogRecord,
) -> PyResult<bool> {
    let Some(types) = record_types(py) else {
        return Ok(false);
    };
    dict.set_item(
        intern!(py, "level"),
        level_value(py, types, level_name, record)?,
    )?;
    dict.set_item(intern!(py, "file"), file_value(py, types, record)?)?;
    dict.set_item(
        intern!(py, "module"),
        module_name(record.caller.file_name()),
    )?;
    dict.set_item(intern!(py, "thread"), thread_value(py, types, record)?)?;
    dict.set_item(intern!(py, "process"), process_value(py, types, record)?)?;
    dict.set_item(intern!(py, "time"), time_value(py, &record.timestamp)?)?;
    dict.set_item(
        intern!(py, "elapsed"),
        elapsed_value(py, types, &record.timestamp)?,
    )?;
    Ok(true)
}

#[cfg(test)]
mod tests {
    use super::module_name;

    #[test]
    fn module_name_strips_extension() {
        assert_eq!(module_name("app.py"), "app");
        assert_eq!(module_name("archive.tar.gz"), "archive.tar");
        assert_eq!(module_name("noext"), "noext");
        assert_eq!(module_name(""), "");
    }
}
