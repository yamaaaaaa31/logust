//! Caller, thread and process collection for `PyLogger::log_fast`.
//!
//! These mirror the Python helpers in `logust/_logger.py` (`_get_caller_info`,
//! `_get_thread_info`, `_get_process_info`) so a record built here is identical
//! to one built by the Python dispatch path. Whenever a value has a shape the
//! Python helpers would hand to PyO3 and get a `TypeError` back for, the
//! collectors return `None` and the caller falls back to the Python path, which
//! then raises exactly as before.

use std::sync::Mutex;

use pyo3::ffi;
use pyo3::intern;
use pyo3::prelude::*;
use pyo3::sync::PyOnceLock;
use pyo3::types::{PyDict, PyString};

use crate::handler::{CallerInfo, ProcessInfo, ThreadInfo};

/// `threading.current_thread`, resolved once.
static CURRENT_THREAD: PyOnceLock<Py<PyAny>> = PyOnceLock::new();

/// `(pid, name)` of the last process queried; re-read after `fork()` (pid change),
/// like `_CACHED_PROCESS_INFO` / `_CACHED_PROCESS_PID` on the Python side.
/// Only ever `try_lock`ed: a fork() taken while another thread holds the lock
/// (possible on free-threaded builds) would otherwise leave it locked forever in
/// the child.
static PROCESS_INFO: Mutex<Option<(u32, String)>> = Mutex::new(None);

/// Caller info of the frame `depth` levels above the Python frame that is
/// calling into Rust, as `_get_caller_info` would report it.
///
/// `Ok(Some(..))` has the module name (`f_globals["__name__"]`, or `co_filename`
/// when the key is missing), `co_name`, the current line and `co_filename`.
/// Running past the top of the stack gives empty values, matching the
/// `sys._getframe` `ValueError` fallback. `Ok(None)` means the caller should
/// use the Python path (an unexpected object shape).
pub fn caller_info(py: Python<'_>, depth: usize) -> PyResult<Option<CallerInfo>> {
    // SAFETY: `PyEval_GetFrame` returns a *borrowed* pointer to the current
    // thread's executing frame, or NULL when no Python code is running on it.
    // `from_borrowed_ptr_or_opt` takes its own reference, so the `Bound` owns
    // one reference that is released when it is dropped. The thread is attached
    // to the interpreter for the lifetime of `py`.
    let Some(mut frame) =
        (unsafe { Bound::from_borrowed_ptr_or_opt(py, ffi::PyEval_GetFrame().cast()) })
    else {
        return Ok(Some(CallerInfo::default()));
    };

    for _ in 0..depth {
        // SAFETY: `frame` is a live frame object (owned by the `Bound`).
        // `PyFrame_GetBack` returns a *new* reference (or NULL at the outermost
        // frame), which `from_owned_ptr_or_opt` adopts without another INCREF.
        let back = unsafe {
            Bound::from_owned_ptr_or_opt(py, ffi::PyFrame_GetBack(frame.as_ptr().cast()).cast())
        };
        match back {
            Some(back) => frame = back,
            None => return Ok(Some(CallerInfo::default())),
        }
    }

    // SAFETY: `frame` is a live frame object; `PyFrame_GetCode` returns a new
    // reference to its code object and never NULL.
    let code = unsafe {
        Bound::from_owned_ptr_or_err(py, ffi::PyFrame_GetCode(frame.as_ptr().cast()).cast())
    }?;
    // SAFETY: `frame` is a live frame object. The line is -1 when it is unknown
    // (where Python's `f_lineno` is `None`, which the Python path turns into 0).
    let line = unsafe { ffi::PyFrame_GetLineNumber(frame.as_ptr().cast()) };
    let line = u32::try_from(line).unwrap_or(0);

    let Some(function) = owned_str(&code.getattr(intern!(py, "co_name"))?)? else {
        return Ok(None);
    };
    let Some(file) = owned_str(&code.getattr(intern!(py, "co_filename"))?)? else {
        return Ok(None);
    };

    let globals = frame.getattr(intern!(py, "f_globals"))?;
    let Ok(globals) = globals.cast::<PyDict>() else {
        return Ok(None);
    };
    let name = match globals.get_item(intern!(py, "__name__"))? {
        None => file.clone(),
        Some(value) if value.is_none() => String::new(),
        Some(value) => match owned_str(&value)? {
            Some(name) => name,
            None => return Ok(None),
        },
    };

    Ok(Some(CallerInfo::with_file(name, function, line, file)))
}

/// Current thread as `_get_thread_info` reports it: `threading.current_thread()`'s
/// `name` and `ident or 0`. `Ok(None)` means the caller should use the Python path.
pub fn thread_info(py: Python<'_>) -> PyResult<Option<ThreadInfo>> {
    let current_thread = CURRENT_THREAD.get_or_try_init(py, || {
        py.import(intern!(py, "threading"))?
            .getattr(intern!(py, "current_thread"))
            .map(Bound::unbind)
    })?;
    let thread = current_thread.bind(py).call0()?;
    let Some(name) = owned_str(&thread.getattr(intern!(py, "name"))?)? else {
        return Ok(None);
    };
    // `thread.ident or 0`: the property is read like the Python helper does
    // (`PyThread_get_thread_ident` would be equal, but pyo3-ffi does not bind
    // it and a self-declared extern does not link with Windows raw-dylib builds).
    let ident = thread.getattr(intern!(py, "ident"))?;
    let id = if ident.is_none() {
        0
    } else {
        match ident.extract::<u64>() {
            Ok(id) => id,
            Err(_) => return Ok(None),
        }
    };
    Ok(Some(ThreadInfo { name, id }))
}

/// Current process as `_get_process_info` reports it: the pid and
/// `multiprocessing.current_process().name` (`"MainProcess"` if that raises),
/// cached until the pid changes.
pub fn process_info(py: Python<'_>) -> PyResult<ProcessInfo> {
    let id = std::process::id();
    if let Some(cached) = try_lock(&PROCESS_INFO)
        && let Some((pid, name)) = cached.as_ref()
        && *pid == id
    {
        return Ok(ProcessInfo {
            name: name.clone(),
            id,
        });
    }
    let name = match current_process_name(py) {
        Ok(name) => name,
        Err(err) if err.is_instance_of::<pyo3::exceptions::PyException>(py) => {
            "MainProcess".to_string()
        }
        Err(err) => return Err(err),
    };
    if let Some(mut cached) = try_lock(&PROCESS_INFO) {
        *cached = Some((id, name.clone()));
    }
    Ok(ProcessInfo { name, id })
}

/// The lock if it is free (recovering a poisoned one); never blocks.
fn try_lock<T>(mutex: &Mutex<T>) -> Option<std::sync::MutexGuard<'_, T>> {
    match mutex.try_lock() {
        Ok(guard) => Some(guard),
        Err(std::sync::TryLockError::Poisoned(err)) => Some(err.into_inner()),
        Err(std::sync::TryLockError::WouldBlock) => None,
    }
}

fn current_process_name(py: Python<'_>) -> PyResult<String> {
    py.import(intern!(py, "multiprocessing"))?
        .getattr(intern!(py, "current_process"))?
        .call0()?
        .getattr(intern!(py, "name"))?
        .extract::<String>()
}

/// `str` (or subclass) contents as an owned `String`; `None` for other types.
fn owned_str(value: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    match value.cast::<PyString>() {
        Ok(s) => Ok(Some(s.to_str()?.to_owned())),
        Err(_) => Ok(None),
    }
}
