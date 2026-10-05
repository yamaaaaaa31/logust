//! loguru-shaped values for the record dict passed to filters and raw callbacks.
//!
//! Only the paths that already build a full record dict call into this module;
//! the default (no filter, no callback) logging path never does.
//!
//! The level, file, thread and process values are cached per distinct value, so
//! a record usually costs one lock, a few hash lookups, and one `datetime` plus
//! one `timedelta` construction.

use std::collections::HashMap;
use std::sync::atomic::Ordering;
use std::sync::{LazyLock, Mutex};

use chrono::{DateTime, Datelike, Local, Offset, Timelike};
use pyo3::intern;
use pyo3::prelude::*;
use pyo3::sync::PyOnceLock;
use pyo3::types::{PyDateTime, PyDelta, PyDict, PyString, PyType, PyTzInfo};

use crate::format::{LOGGER_START_TIME, format_elapsed};
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
    /// `elapsed` is a `timedelta` subclass (checked once, enables the C API fast path)
    elapsed_is_delta: bool,
}

/// `None` if `logust._record` cannot be imported (plain values are used instead)
static RECORD_TYPES: PyOnceLock<Option<RecordTypes>> = PyOnceLock::new();

fn record_types(py: Python<'_>) -> Option<&RecordTypes> {
    RECORD_TYPES
        .get_or_init(py, || {
            let module = py.import("logust._record").ok()?;
            let get = |name: &str| module.getattr(name).ok();
            let elapsed = get("RecordElapsed")?;
            let elapsed_is_delta = elapsed
                .cast::<PyType>()
                .is_ok_and(|t| t.is_subclass_of::<PyDelta>().unwrap_or(false));
            Some(RecordTypes {
                level: get("RecordLevelStr")?.unbind(),
                file: get("RecordFile")?.unbind(),
                thread: get("RecordThread")?.unbind(),
                process: get("RecordProcess")?.unbind(),
                elapsed: elapsed.unbind(),
                elapsed_is_delta,
            })
        })
        .as_ref()
}

#[derive(Default)]
struct Caches {
    /// Level registry generation the level cache was built for
    level_generation: u64,
    levels: HashMap<String, Py<PyAny>>,
    /// File path -> (`RecordFile`, module name)
    files: HashMap<String, (Py<PyAny>, Py<PyAny>)>,
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

/// Cached values for one record; `None` marks a cache miss
struct Cached {
    level: Option<Py<PyAny>>,
    file: Option<(Py<PyAny>, Py<PyAny>)>,
    thread: Option<Py<PyAny>>,
    process: Option<Py<PyAny>>,
    tz: Option<Py<PyTzInfo>>,
}

/// Look up every cached value under a single lock acquisition.
fn lookup(
    py: Python<'_>,
    level_name: &str,
    record: &LogRecord,
    generation: u64,
    offset: i32,
) -> Cached {
    let mut c = caches();
    if c.level_generation != generation {
        c.levels.clear();
        c.level_generation = generation;
    }
    Cached {
        level: c.levels.get(level_name).map(|o| o.clone_ref(py)),
        file: c
            .files
            .get(record.caller.file.as_str())
            .map(|(f, m)| (f.clone_ref(py), m.clone_ref(py))),
        thread: c
            .threads
            .get(&record.thread.id)
            .filter(|(name, _)| *name == record.thread.name)
            .map(|(_, o)| o.clone_ref(py)),
        process: c
            .processes
            .get(&record.process.id)
            .filter(|(name, _)| *name == record.process.name)
            .map(|(_, o)| o.clone_ref(py)),
        tz: c
            .tz
            .as_ref()
            .filter(|(o, _)| *o == offset)
            .map(|(_, tz)| tz.clone_ref(py)),
    }
}

/// Level `(no, icon)` for a `RecordLevelStr` built on a cache miss
fn level_details(name: &str, record: &LogRecord) -> (u32, String) {
    match record.level_info.as_ref() {
        Some(info) => (info.no, info.icon.clone().unwrap_or_default()),
        None => get_level_info(name).map_or((record.level as u32, String::new()), |info| {
            (info.no, info.icon.unwrap_or_default())
        }),
    }
}

/// Aware `datetime` for the record timestamp (loguru's `record["time"]`)
fn time_value<'py>(
    py: Python<'py>,
    ts: &DateTime<Local>,
    tz: &Bound<'py, PyTzInfo>,
) -> PyResult<Bound<'py, PyDateTime>> {
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
        Some(tz),
    )
}

/// `RecordElapsed` (a `timedelta` subclass) since logger start, clamped at zero
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
    let days = (secs / 86_400).min(i64::from(i32::MAX)) as i32;
    let secs = (secs % 86_400) as i32;
    let micros = (micros % 1_000_000) as i32;
    if types.elapsed_is_delta {
        // SAFETY: the datetime C API pointer is checked (PyO3 imported it when
        // `time_value` ran), and `RecordElapsed` is a `timedelta` subclass, which
        // `Delta_FromDelta` allocates through the subclass's `tp_alloc`. This
        // skips the argument parsing of a regular class call.
        unsafe {
            let api = pyo3::ffi::PyDateTimeAPI();
            if !api.is_null() {
                let cls = types.elapsed.as_ptr().cast::<pyo3::ffi::PyTypeObject>();
                let ptr = ((*api).Delta_FromDelta)(days, secs, micros, 1, cls);
                return Bound::from_owned_ptr_or_err(py, ptr);
            }
        }
    }
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
///
/// Python objects for cache misses are created with the cache lock released, so
/// a constructor that releases the GIL cannot deadlock another logging thread.
pub fn set_compat_fields(
    py: Python<'_>,
    dict: &Bound<'_, PyDict>,
    level_name: &str,
    record: &LogRecord,
) -> PyResult<bool> {
    let Some(types) = record_types(py) else {
        return Ok(false);
    };
    let generation = LEVEL_GENERATION.load(Ordering::Acquire);
    let offset = record.timestamp.offset().fix().local_minus_utc();
    let cached = lookup(py, level_name, record, generation, offset);
    let any_miss = cached.level.is_none()
        || cached.file.is_none()
        || cached.thread.is_none()
        || cached.process.is_none()
        || cached.tz.is_none();

    let level = match cached.level {
        Some(obj) => obj.into_bound(py),
        None => {
            let (no, icon) = level_details(level_name, record);
            types.level.bind(py).call1((level_name, no, icon))?
        }
    };
    let (file, module) = match cached.file {
        Some((f, m)) => (f.into_bound(py), m.into_bound(py)),
        None => {
            let file_name = record.caller.file_name();
            let file = types
                .file
                .bind(py)
                .call1((file_name, record.caller.file.as_str()))?;
            let module = PyString::new(py, module_name(file_name)).into_any();
            (file, module)
        }
    };
    let thread = match cached.thread {
        Some(obj) => obj.into_bound(py),
        None => types
            .thread
            .bind(py)
            .call1((record.thread.id, record.thread.name.as_str()))?,
    };
    let process = match cached.process {
        Some(obj) => obj.into_bound(py),
        None => types
            .process
            .bind(py)
            .call1((record.process.id, record.process.name.as_str()))?,
    };
    let tz = match cached.tz {
        Some(tz) => tz.into_bound(py),
        None => PyTzInfo::fixed_offset(py, PyDelta::new(py, 0, offset, 0, true)?)?,
    };

    if any_miss {
        let mut c = caches();
        if c.level_generation == generation && !c.levels.contains_key(level_name) {
            insert_bounded(&mut c.levels, level_name.to_owned(), level.clone().unbind());
        }
        if !c.files.contains_key(record.caller.file.as_str()) {
            let value = (file.clone().unbind(), module.clone().unbind());
            insert_bounded(&mut c.files, record.caller.file.clone(), value);
        }
        let value = (record.thread.name.clone(), thread.clone().unbind());
        insert_bounded(&mut c.threads, record.thread.id, value);
        let value = (record.process.name.clone(), process.clone().unbind());
        insert_bounded(&mut c.processes, record.process.id, value);
        c.tz = Some((offset, tz.clone().unbind()));
    }

    dict.set_item(intern!(py, "level"), level)?;
    dict.set_item(intern!(py, "file"), file)?;
    dict.set_item(intern!(py, "module"), module)?;
    dict.set_item(intern!(py, "thread"), thread)?;
    dict.set_item(intern!(py, "process"), process)?;
    dict.set_item(intern!(py, "time"), time_value(py, &record.timestamp, &tz)?)?;
    dict.set_item(
        intern!(py, "elapsed"),
        elapsed_value(py, types, &record.timestamp)?,
    )?;
    Ok(true)
}

/// `(time, timestamp, elapsed)` for the current instant, as in a filter record.
///
/// Used by the patcher record, which is built in Python before the Rust record exists.
#[pyfunction]
pub fn record_time_fields(
    py: Python<'_>,
) -> PyResult<(Bound<'_, PyAny>, String, Bound<'_, PyAny>)> {
    let now = Local::now();
    let offset = now.offset().fix().local_minus_utc();
    let cached = caches()
        .tz
        .as_ref()
        .filter(|(o, _)| *o == offset)
        .map(|(_, tz)| tz.clone_ref(py));
    let tz = match cached {
        Some(tz) => tz.into_bound(py),
        None => {
            let tz = PyTzInfo::fixed_offset(py, PyDelta::new(py, 0, offset, 0, true)?)?;
            caches().tz = Some((offset, tz.clone().unbind()));
            tz
        }
    };
    let time = time_value(py, &now, &tz)?.into_any();
    let elapsed = match record_types(py) {
        Some(types) => elapsed_value(py, types, &now)?,
        None => PyString::new(py, &format_elapsed(&LOGGER_START_TIME, &now)).into_any(),
    };
    Ok((time, now.to_rfc3339(), elapsed))
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
