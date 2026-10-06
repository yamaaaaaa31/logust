use std::collections::{HashMap, HashSet};
use std::fmt::{self, Write as _};
use std::io::{self, Write as _};
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};

use chrono::{DateTime, Local};
use pyo3::IntoPyObjectExt;
use pyo3::prelude::*;
use pyo3::sync::PyOnceLock;
use pyo3::types::{
    PyBool, PyByteArray, PyBytes, PyDate, PyDateTime, PyDict, PyFloat, PyFrozenSet, PyInt, PyList,
    PySet, PyString, PyTime, PyTuple, PyType,
};
use serde::{Serialize, Serializer};
use serde_json::{Map, Number, Value};

use crate::clock::local_now;
use crate::format::{FormatConfig, TokenRequirements};
use crate::level::{LevelInfo, LogLevel};
use crate::sink::FileSink;

/// Global handler ID counter
static HANDLER_ID_COUNTER: AtomicU64 = AtomicU64::new(0);

/// Generate a new unique handler ID
#[inline]
pub fn next_handler_id() -> u64 {
    HANDLER_ID_COUNTER.fetch_add(1, Ordering::Relaxed)
}

/// Empty context singleton to avoid allocations
static EMPTY_CONTEXT: std::sync::LazyLock<Arc<ExtraMap>> =
    std::sync::LazyLock::new(|| Arc::new(HashMap::new()));

pub type ExtraMap = HashMap<String, ExtraValue>;

/// Maximum recursion depth when converting Python containers to JSON values.
/// Anything deeper is replaced with a sentinel string to avoid stack overflow
/// on cyclic data structures (e.g. ORM back-references, dict containing itself).
const MAX_JSON_DEPTH: usize = 32;

static ENUM_TYPE: PyOnceLock<Py<PyType>> = PyOnceLock::new();

/// Extra context value with text rendering compatibility and typed JSON output.
///
/// Two views are stored side-by-side:
/// * `text` keeps loguru-compatible `str(value)` output for format-string
///   `{extra[key]}` rendering and Python callbacks (`record["extra"][key]`).
/// * `json` carries the original Python type (int, float, bool, bytes,
///   datetime, list, dict, set, enum values, None) so JSON sinks emit native
///   types instead of strings.
#[derive(Clone, Debug)]
pub struct ExtraValue {
    text: String,
    json: Value,
    /// The Python value was a `str` (`{extra}` quotes it like `repr()`)
    is_str: bool,
}

/// Classification of a Python value for fast-path `ExtraValue` construction.
///
/// Each variant carries the already-extracted Rust value so
/// `ExtraValue::from_py` can build the JSON view without re-dispatching on the
/// Python type.
enum FastKind {
    None,
    Bool(bool),
    Str(String),
    I64(i64),
    U64(u64),
    /// No fast path applies — caller must use `value.str()` + full JSON dispatch.
    Slow,
}

impl FastKind {
    /// Try to classify `value` into a primitive variant; otherwise return `Slow`.
    ///
    /// Order matters: `PyBool` must be tested before `PyInt` because Python
    /// `bool` subclasses `int`, and `True` would otherwise serialize as `1`.
    #[inline(always)]
    fn classify(value: &Bound<'_, PyAny>) -> PyResult<Self> {
        if value.is_none() {
            return Ok(Self::None);
        }
        if value.cast::<PyBool>().is_ok() {
            return Ok(Self::Bool(value.extract()?));
        }
        if let Ok(s) = value.cast::<PyString>() {
            return Ok(Self::Str(s.to_str()?.to_owned()));
        }
        if value.cast::<PyInt>().is_ok() {
            if let Ok(n) = value.extract::<i64>() {
                return Ok(Self::I64(n));
            }
            if let Ok(n) = value.extract::<u64>() {
                return Ok(Self::U64(n));
            }
            // Big int: fall through to slow path so text/json agree on the
            // string fallback.
        }
        Ok(Self::Slow)
    }
}

fn safe_text_view(value: &Bound<'_, PyAny>) -> String {
    if let Ok(s) = value.str() {
        return s.to_string();
    }
    if let Ok(s) = value.repr() {
        return s.to_string();
    }
    let type_name = value
        .get_type()
        .name()
        .map(|n| n.to_string())
        .unwrap_or_else(|_| "object".to_string());
    format!("<unprintable {type_name}>")
}

impl ExtraValue {
    pub fn from_py(value: &Bound<'_, PyAny>) -> PyResult<Self> {
        let kind = FastKind::classify(value)?;
        let text = safe_text_view(value);

        match kind {
            FastKind::None => Ok(Self {
                text,
                json: Value::Null,
                is_str: false,
            }),
            FastKind::Bool(b) => Ok(Self {
                text,
                json: Value::Bool(b),
                is_str: false,
            }),
            FastKind::Str(s) => Ok(Self {
                text,
                json: Value::String(s),
                is_str: true,
            }),
            FastKind::I64(n) => Ok(Self {
                text,
                json: Value::Number(Number::from(n)),
                is_str: false,
            }),
            FastKind::U64(n) => Ok(Self {
                text,
                json: Value::Number(Number::from(n)),
                is_str: false,
            }),
            FastKind::Slow => {
                let mut seen = HashSet::new();
                let json = py_to_json_value(value, 0, &mut seen)
                    .unwrap_or_else(|_| Value::String(text.clone()));
                Ok(Self {
                    text,
                    json,
                    is_str: false,
                })
            }
        }
    }

    #[inline]
    pub fn as_str(&self) -> &str {
        &self.text
    }

    #[inline]
    pub fn as_json(&self) -> &Value {
        &self.json
    }

    /// A non-`str` value whose `str()` is `text` (e.g. an int), for tests
    #[cfg(test)]
    pub fn non_str(text: &str) -> Self {
        Self {
            text: text.to_string(),
            json: Value::String(text.to_string()),
            is_str: false,
        }
    }

    /// Append the value as it appears in `str(dict)` (loguru's `{extra}`).
    ///
    /// Strings are quoted like Python's `repr()`; other values use their `str()`
    /// text, which equals `repr()` for `int`, `float`, `bool`, `None`, and
    /// `list` / `tuple` / `dict` values.
    pub fn write_repr(&self, out: &mut String) {
        if self.is_str {
            write_py_str_repr(&self.text, out);
        } else {
            out.push_str(&self.text);
        }
    }
}

/// Whether Python's `str.isprintable()` is false for `c` (approximation of the
/// Unicode categories Cc, Cf, Co, Zl, Zp and Zs other than the ASCII space).
fn is_py_unprintable(c: char) -> bool {
    matches!(
        c as u32,
        0x00..=0x1f
            | 0x7f..=0xa0
            | 0xad
            | 0x600..=0x605
            | 0x61c
            | 0x6dd
            | 0x70f
            | 0x1680
            | 0x180e
            | 0x2000..=0x200f
            | 0x2028..=0x202f
            | 0x205f..=0x2064
            | 0x2066..=0x206f
            | 0x3000
            | 0xd800..=0xf8ff
            | 0xfeff
            | 0xfff9..=0xfffb
            | 0xf0000..=0x10ffff
    )
}

/// Append `s` quoted and escaped like Python's `repr(str)`.
pub fn write_py_str_repr(s: &str, out: &mut String) {
    let quote = if s.contains('\'') && !s.contains('"') {
        '"'
    } else {
        '\''
    };
    out.reserve(s.len() + 2);
    out.push(quote);
    for c in s.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c == quote => {
                out.push('\\');
                out.push(c);
            }
            c if is_py_unprintable(c) => {
                let n = c as u32;
                let _ = if n < 0x100 {
                    write!(out, "\\x{n:02x}")
                } else if n < 0x10000 {
                    write!(out, "\\u{n:04x}")
                } else {
                    write!(out, "\\U{n:08x}")
                };
            }
            c => out.push(c),
        }
    }
    out.push(quote);
}

/// Append the whole extra dict as loguru's `{extra}` renders it (`str(dict)`).
///
/// Keys are sorted: the map does not keep insertion order (loguru's does).
pub fn write_extra_repr(extra: &ExtraMap, out: &mut String) {
    out.push('{');
    let mut keys: Vec<&String> = extra.keys().collect();
    keys.sort_unstable();
    for (i, key) in keys.into_iter().enumerate() {
        if i > 0 {
            out.push_str(", ");
        }
        write_py_str_repr(key, out);
        out.push_str(": ");
        extra[key].write_repr(out);
    }
    out.push('}');
}

impl From<String> for ExtraValue {
    fn from(value: String) -> Self {
        Self {
            text: value.clone(),
            json: Value::String(value),
            is_str: true,
        }
    }
}

impl From<&str> for ExtraValue {
    fn from(value: &str) -> Self {
        Self::from(value.to_string())
    }
}

impl fmt::Display for ExtraValue {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.text)
    }
}

impl Serialize for ExtraValue {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        self.json.serialize(serializer)
    }
}

pub fn serde_json_to_py(py: Python<'_>, value: &Value) -> PyResult<Py<PyAny>> {
    match value {
        Value::Null => Ok(py.None()),
        Value::Bool(b) => (*b).into_py_any(py),
        Value::Number(number) => {
            if let Some(n) = number.as_i64() {
                return n.into_py_any(py);
            }
            if let Some(n) = number.as_u64() {
                return n.into_py_any(py);
            }
            if let Some(n) = number.as_f64() {
                return n.into_py_any(py);
            }
            Err(pyo3::exceptions::PyValueError::new_err(
                "unsupported JSON number",
            ))
        }
        Value::String(s) => s.as_str().into_py_any(py),
        Value::Array(values) => {
            let list = PyList::empty(py);
            for item in values {
                list.append(serde_json_to_py(py, item)?)?;
            }
            Ok(list.into_any().unbind())
        }
        Value::Object(values) => {
            let dict = PyDict::new(py);
            for (key, item) in values {
                dict.set_item(key, serde_json_to_py(py, item)?)?;
            }
            Ok(dict.into_any().unbind())
        }
    }
}

fn recursion_limit_value() -> Value {
    Value::String("<recursion limit reached>".to_string())
}

fn py_to_json_value(
    value: &Bound<'_, PyAny>,
    depth: usize,
    seen: &mut HashSet<usize>,
) -> PyResult<Value> {
    if depth >= MAX_JSON_DEPTH {
        return Ok(recursion_limit_value());
    }

    if value.is_none() {
        return Ok(Value::Null);
    }
    // PyBool must be checked before PyInt because `bool` is a subclass of `int`
    // in Python — otherwise `True` would serialize as `1`.
    if value.cast::<PyBool>().is_ok() {
        return Ok(Value::Bool(value.extract::<bool>()?));
    }
    if value.cast::<PyString>().is_ok() {
        return Ok(Value::String(value.extract::<String>()?));
    }
    if value.cast::<PyInt>().is_ok() {
        return py_int_to_json(value);
    }
    if value.cast::<PyFloat>().is_ok() {
        return py_float_to_json(value);
    }
    if let Ok(bytes) = value.cast::<PyBytes>() {
        return Ok(bytes_to_utf8_json(bytes.as_bytes()));
    }
    if let Ok(bytearray) = value.cast::<PyByteArray>() {
        return Ok(bytes_to_utf8_json(&bytearray.to_vec()));
    }
    if value.cast::<PyDateTime>().is_ok() {
        return py_isoformat_to_json(value);
    }
    if value.cast::<PyDate>().is_ok() {
        return py_isoformat_to_json(value);
    }
    if value.cast::<PyTime>().is_ok() {
        return py_isoformat_to_json(value);
    }
    if let Ok(list) = value.cast::<PyList>() {
        return py_container_to_json(value, seen, |seen| {
            py_seq_to_json(list.iter(), list.len(), depth + 1, seen)
        });
    }
    if let Ok(tuple) = value.cast::<PyTuple>() {
        return py_container_to_json(value, seen, |seen| {
            py_seq_to_json(tuple.iter(), tuple.len(), depth + 1, seen)
        });
    }
    if let Ok(dict) = value.cast::<PyDict>() {
        return py_container_to_json(value, seen, |seen| py_dict_to_json(dict, depth + 1, seen));
    }
    if let Ok(set) = value.cast::<PySet>() {
        return py_container_to_json(value, seen, |seen| {
            py_seq_to_json(set.iter(), set.len(), depth + 1, seen)
        });
    }
    if let Ok(frozenset) = value.cast::<PyFrozenSet>() {
        return py_container_to_json(value, seen, |seen| {
            py_seq_to_json(frozenset.iter(), frozenset.len(), depth + 1, seen)
        });
    }
    if let Some(enum_value) = py_enum_to_json(value, depth + 1, seen)? {
        return Ok(enum_value);
    }

    Ok(Value::String(value.str()?.to_string()))
}

fn py_container_to_json(
    value: &Bound<'_, PyAny>,
    seen: &mut HashSet<usize>,
    convert: impl FnOnce(&mut HashSet<usize>) -> PyResult<Value>,
) -> PyResult<Value> {
    let identity = value.as_ptr() as usize;
    if !seen.insert(identity) {
        return Ok(recursion_limit_value());
    }

    let result = convert(seen);
    seen.remove(&identity);
    result
}

fn bytes_to_utf8_json(bytes: &[u8]) -> Value {
    Value::String(String::from_utf8_lossy(bytes).into_owned())
}

fn py_int_to_json(value: &Bound<'_, PyAny>) -> PyResult<Value> {
    if let Ok(n) = value.extract::<i64>() {
        return Ok(Value::Number(Number::from(n)));
    }
    if let Ok(n) = value.extract::<u64>() {
        return Ok(Value::Number(Number::from(n)));
    }
    Ok(Value::String(value.str()?.to_string()))
}

fn py_float_to_json(value: &Bound<'_, PyAny>) -> PyResult<Value> {
    let n = value.extract::<f64>()?;
    Ok(Number::from_f64(n)
        .map(Value::Number)
        .unwrap_or_else(|| Value::String(value.str().map(|s| s.to_string()).unwrap_or_default())))
}

fn py_isoformat_to_json(value: &Bound<'_, PyAny>) -> PyResult<Value> {
    Ok(Value::String(
        value.call_method0("isoformat")?.extract::<String>()?,
    ))
}

fn py_enum_to_json(
    value: &Bound<'_, PyAny>,
    depth: usize,
    seen: &mut HashSet<usize>,
) -> PyResult<Option<Value>> {
    let enum_type = ENUM_TYPE.import(value.py(), "enum", "Enum")?;
    if value.is_instance(enum_type)? {
        let enum_value = value.getattr("value")?;
        return Ok(Some(py_to_json_value(&enum_value, depth, seen)?));
    }
    Ok(None)
}

fn py_seq_to_json<'py>(
    iter: impl Iterator<Item = Bound<'py, PyAny>>,
    capacity: usize,
    depth: usize,
    seen: &mut HashSet<usize>,
) -> PyResult<Value> {
    let mut values = Vec::with_capacity(capacity);
    for item in iter {
        values.push(py_to_json_value(&item, depth, seen)?);
    }
    Ok(Value::Array(values))
}

fn py_dict_to_json(
    dict: &Bound<'_, PyDict>,
    depth: usize,
    seen: &mut HashSet<usize>,
) -> PyResult<Value> {
    let mut map = Map::with_capacity(dict.len());
    for (key, value) in dict.iter() {
        map.insert(
            key.str()?.to_string(),
            py_to_json_value(&value, depth, seen)?,
        );
    }
    Ok(Value::Object(map))
}

/// Get empty context (zero-cost)
#[inline]
pub fn empty_context() -> Arc<ExtraMap> {
    Arc::clone(&EMPTY_CONTEXT)
}

/// Caller information for log records
#[derive(Clone, Debug, Default)]
pub struct CallerInfo {
    pub name: String,
    pub function: String,
    pub line: u32,
    /// Source file path as given by the caller (Python passes `co_filename`)
    pub file: String,
}

/// Final component of a file path (like `os.path.basename`)
#[inline]
pub fn file_basename(path: &str) -> &str {
    #[cfg(windows)]
    let sep = path.rfind(['/', '\\']);
    #[cfg(not(windows))]
    let sep = path.rfind('/');
    sep.map_or(path, |i| &path[i + 1..])
}

impl CallerInfo {
    pub fn new(name: String, function: String, line: u32) -> Self {
        CallerInfo {
            name,
            function,
            line,
            file: String::new(),
        }
    }

    pub fn with_file(name: String, function: String, line: u32, file: String) -> Self {
        CallerInfo {
            name,
            function,
            line,
            file,
        }
    }

    /// Source file basename (`{file}` / `{file.name}`)
    #[inline]
    pub fn file_name(&self) -> &str {
        file_basename(&self.file)
    }
}

/// Thread information for log records
#[derive(Clone, Debug, Default)]
pub struct ThreadInfo {
    pub name: String,
    pub id: u64,
}

/// Process information for log records
#[derive(Clone, Debug, Default)]
pub struct ProcessInfo {
    pub name: String,
    pub id: u32,
}

/// Log record containing all information about a log message
#[derive(Clone, Debug)]
pub struct LogRecord {
    pub timestamp: DateTime<Local>,
    pub level: LogLevel,
    pub level_info: Option<Arc<LevelInfo>>,
    pub message: String,
    pub extra: Arc<ExtraMap>,
    pub exception: Option<String>,
    pub caller: CallerInfo,
    pub thread: ThreadInfo,
    pub process: ProcessInfo,
    /// Render color markup in the message (`opt(colors=False)` turns it off)
    pub message_markup: bool,
}

impl LogRecord {
    /// Create a new log record
    pub fn new(level: LogLevel, message: String) -> Self {
        LogRecord {
            timestamp: local_now(),
            level,
            level_info: None,
            message,
            extra: empty_context(),
            exception: None,
            caller: CallerInfo::default(),
            thread: ThreadInfo::default(),
            process: ProcessInfo::default(),
            message_markup: true,
        }
    }

    /// Create a new log record with extra context (Arc reference - zero-copy)
    pub fn with_extra(level: LogLevel, message: String, extra: Arc<ExtraMap>) -> Self {
        LogRecord {
            timestamp: local_now(),
            level,
            level_info: None,
            message,
            extra,
            exception: None,
            caller: CallerInfo::default(),
            thread: ThreadInfo::default(),
            process: ProcessInfo::default(),
            message_markup: true,
        }
    }

    /// Create a new log record with caller info and exception
    pub fn with_caller(
        level: LogLevel,
        message: String,
        extra: Arc<ExtraMap>,
        exception: Option<String>,
        caller: CallerInfo,
    ) -> Self {
        LogRecord {
            timestamp: local_now(),
            level,
            level_info: None,
            message,
            extra,
            exception,
            caller,
            thread: ThreadInfo::default(),
            process: ProcessInfo::default(),
            message_markup: true,
        }
    }

    /// Create a new log record with all fields
    pub fn with_all(
        level: LogLevel,
        message: String,
        extra: Arc<ExtraMap>,
        exception: Option<String>,
        caller: CallerInfo,
        thread: ThreadInfo,
        process: ProcessInfo,
    ) -> Self {
        LogRecord {
            timestamp: local_now(),
            level,
            level_info: None,
            message,
            extra,
            exception,
            caller,
            thread,
            process,
            message_markup: true,
        }
    }

    /// Create a new log record with extra context and exception (Arc reference - zero-copy)
    pub fn with_exception(
        level: LogLevel,
        message: String,
        extra: Arc<ExtraMap>,
        exception: Option<String>,
    ) -> Self {
        LogRecord {
            timestamp: local_now(),
            level,
            level_info: None,
            message,
            extra,
            exception,
            caller: CallerInfo::default(),
            thread: ThreadInfo::default(),
            process: ProcessInfo::default(),
            message_markup: true,
        }
    }

    /// Create a log record with custom level info (Arc reference - zero-copy)
    pub fn with_custom_level(
        level_info: Arc<LevelInfo>,
        message: String,
        extra: Arc<ExtraMap>,
        exception: Option<String>,
    ) -> Self {
        LogRecord {
            timestamp: local_now(),
            level: LogLevel::Debug, // Placeholder, not used for custom levels
            level_info: Some(level_info),
            message,
            extra,
            exception,
            caller: CallerInfo::default(),
            thread: ThreadInfo::default(),
            process: ProcessInfo::default(),
            message_markup: true,
        }
    }

    /// Create a log record with custom level info and caller
    pub fn with_custom_level_and_caller(
        level_info: Arc<LevelInfo>,
        message: String,
        extra: Arc<ExtraMap>,
        exception: Option<String>,
        caller: CallerInfo,
    ) -> Self {
        LogRecord {
            timestamp: local_now(),
            level: LogLevel::Debug,
            level_info: Some(level_info),
            message,
            extra,
            exception,
            caller,
            thread: ThreadInfo::default(),
            process: ProcessInfo::default(),
            message_markup: true,
        }
    }

    /// Create a log record with custom level info, caller, thread and process
    pub fn with_custom_level_full(
        level_info: Arc<LevelInfo>,
        message: String,
        extra: Arc<ExtraMap>,
        exception: Option<String>,
        caller: CallerInfo,
        thread: ThreadInfo,
        process: ProcessInfo,
    ) -> Self {
        LogRecord {
            timestamp: local_now(),
            level: LogLevel::Debug,
            level_info: Some(level_info),
            message,
            extra,
            exception,
            caller,
            thread,
            process,
            message_markup: true,
        }
    }

    /// Get level name (works for both built-in and custom)
    pub fn level_name(&self) -> &str {
        if let Some(ref info) = self.level_info {
            &info.name
        } else {
            self.level.as_str()
        }
    }

    /// Get level numeric value
    pub fn level_no(&self) -> u32 {
        if let Some(ref info) = self.level_info {
            info.no
        } else {
            self.level as u32
        }
    }

    /// Get level icon (empty if the level has none)
    pub fn level_icon(&self) -> &str {
        match self.level_info {
            Some(ref info) => info.icon.as_deref().unwrap_or(""),
            None => self.level.icon(),
        }
    }

    /// Check if this is a custom level record
    pub fn is_custom(&self) -> bool {
        self.level_info.is_some()
    }
}

/// Handler type enum for different output destinations
pub enum HandlerType {
    Console(ConsoleHandler),
    File(FileHandler),
}

impl HandlerType {
    /// Handle a log record
    pub fn handle(&self, record: &LogRecord) -> io::Result<()> {
        match self {
            HandlerType::Console(h) => h.handle(record),
            HandlerType::File(h) => h.handle(record),
        }
    }

    /// Get the minimum log level for this handler
    pub fn level(&self) -> LogLevel {
        match self {
            HandlerType::Console(h) => h.level,
            HandlerType::File(h) => h.level,
        }
    }

    /// Get token requirements for this handler
    pub fn requirements(&self) -> TokenRequirements {
        match self {
            HandlerType::Console(h) => h.format.requirements(),
            HandlerType::File(h) => h.format.requirements(),
        }
    }
}

/// What to do when a handler fails to emit a record (loguru's `catch=`).
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum CatchMode {
    /// Drop the error silently (logust's historical default, `catch=None`).
    #[default]
    Silent,
    /// Print a report to stderr and continue (`catch=True`).
    Report,
    /// Raise the error from the logging call as `OSError` (`catch=False`).
    Raise,
}

impl CatchMode {
    pub fn from_option(catch: Option<bool>) -> Self {
        match catch {
            None => CatchMode::Silent,
            Some(true) => CatchMode::Report,
            Some(false) => CatchMode::Raise,
        }
    }
}

/// Handler entry with ID and optional filter
pub struct HandlerEntry {
    pub id: u64,
    pub handler: HandlerType,
    /// Optional filter callable (Python lambda/function)
    pub filter: Option<Py<PyAny>>,
    /// Error policy; only consulted when `handle` fails.
    pub catch: CatchMode,
    /// Traceback variant this handler gets (bit 0: backtrace, bit 1: diagnose)
    pub exc_variant: u8,
}

impl HandlerEntry {
    /// Apply the catch policy to a failed emit. Only reached on the error path.
    #[cold]
    pub fn on_error(&self, err: io::Error, record: &LogRecord, first_error: &mut Option<PyErr>) {
        match self.catch {
            CatchMode::Silent => {}
            CatchMode::Report => {
                let report = format!(
                    "--- Logging error in Logust Handler #{} ---\n\
                     Record was: {} | {}\n\
                     OSError: {}\n\
                     --- End of logging error ---\n",
                    self.id,
                    record.level_name(),
                    record.message,
                    err
                );
                // One report per failed record. A write error here (stderr
                // itself closed or broken) is dropped rather than reported
                // again, so a broken stderr can never loop or panic.
                let _ = io::stderr().lock().write_all(report.as_bytes());
            }
            CatchMode::Raise => {
                if first_error.is_none() {
                    *first_error = Some(PyErr::from(err));
                }
            }
        }
    }
}

/// Console handler for terminal output
pub struct ConsoleHandler {
    pub level: LogLevel,
    pub format: FormatConfig,
    pub colorize: bool,
    pub use_stderr: bool,
}

/// A non-empty environment variable (Python's truthy `os.getenv(name)`).
fn env_is_set(name: &str) -> bool {
    std::env::var_os(name).is_some_and(|v| !v.is_empty())
}

/// Whether running inside an IPython kernel whose `sys.stderr` is an
/// `ipykernel` stream, which renders ANSI colors (loguru colorizes there).
fn stderr_is_ipykernel_stream(py: Python<'_>) -> bool {
    let check = || -> PyResult<bool> {
        let builtins = py.import("builtins")?;
        if !builtins
            .getattr("__IPYTHON__")
            .and_then(|v| v.is_truthy())
            .unwrap_or(false)
        {
            return Ok(false);
        }
        let sys = py.import("sys")?;
        let Some(iostream) = sys.getattr("modules")?.get_item("ipykernel.iostream").ok() else {
            return Ok(false);
        };
        let out_stream = iostream.getattr("OutStream")?;
        sys.getattr("stderr")?.is_instance(&out_stream)
    };
    check().unwrap_or(false)
}

/// Color decision for the default console handler (process stderr), made once
/// when the handler is created. Same rules as `logger.add(sys.stderr)`, which
/// ports loguru's `should_colorize`: `NO_COLOR`, `FORCE_COLOR`, Jupyter, known
/// CI services, PyCharm, `TERM=dumb`, `TERM` on Windows, then `isatty`.
pub fn stderr_should_colorize(py: Python<'_>) -> bool {
    use std::io::IsTerminal;

    if env_is_set("NO_COLOR") {
        return false;
    }
    if env_is_set("FORCE_COLOR") {
        return true;
    }
    if stderr_is_ipykernel_stream(py) {
        return true;
    }
    if std::env::var_os("CI").is_some()
        && [
            "TRAVIS",
            "CIRCLECI",
            "APPVEYOR",
            "GITLAB_CI",
            "GITHUB_ACTIONS",
        ]
        .iter()
        .any(|ci| std::env::var_os(ci).is_some())
    {
        return true;
    }
    if std::env::var_os("PYCHARM_HOSTED").is_some() {
        return true;
    }
    match std::env::var_os("TERM") {
        Some(term) if term == "dumb" => return false,
        Some(_) if cfg!(windows) => return true,
        _ => {}
    }
    io::stderr().is_terminal()
}

impl ConsoleHandler {
    /// The default console handler: default format on stderr, as in loguru,
    /// colored when [`stderr_should_colorize`] says so.
    pub fn new(py: Python<'_>, level: LogLevel) -> Self {
        ConsoleHandler {
            level,
            format: FormatConfig::default(),
            colorize: stderr_should_colorize(py),
            use_stderr: true,
        }
    }

    pub fn with_format(level: LogLevel, format: FormatConfig) -> Self {
        let colorize = !format.serialize;
        ConsoleHandler {
            level,
            format,
            colorize,
            use_stderr: false,
        }
    }

    pub fn with_options(
        level: LogLevel,
        format: FormatConfig,
        colorize: bool,
        use_stderr: bool,
    ) -> Self {
        ConsoleHandler {
            level,
            format,
            colorize,
            use_stderr,
        }
    }

    pub fn handle(&self, record: &LogRecord) -> io::Result<()> {
        if record.level_no() >= self.level as u32 {
            let mut output = self.format.format_record(record, self.colorize);
            output.push('\n');
            // `println!` / `eprintln!` panic on a write error (a closed pipe
            // once the reader of `app.py | head` has exited), and that panic
            // would escape the logging call as `PanicException`. Writing the
            // line ourselves returns the `io::Error` to the catch policy.
            //
            // Flushing is unchanged: Rust's stdout is always line-buffered,
            // and a single write ending in '\n' goes straight to the fd (one
            // syscall) whether it is a tty, a pipe or a file. Stderr is
            // unbuffered. A closed descriptor (EBADF) is still treated as a
            // successful write by the standard library.
            if self.use_stderr {
                io::stderr().lock().write_all(output.as_bytes())?;
            } else {
                io::stdout().lock().write_all(output.as_bytes())?;
            }
        }
        Ok(())
    }
}

/// File handler for file output
pub struct FileHandler {
    pub sink: FileSink,
    pub level: LogLevel,
    pub format: FormatConfig,
    pub colorize: bool,
}

impl FileHandler {
    pub fn new(sink: FileSink, level: LogLevel) -> Self {
        FileHandler {
            sink,
            level,
            format: FormatConfig::default(),
            colorize: false,
        }
    }

    pub fn with_format(
        sink: FileSink,
        level: LogLevel,
        format: FormatConfig,
        colorize: bool,
    ) -> Self {
        FileHandler {
            sink,
            level,
            format,
            colorize,
        }
    }

    #[inline]
    pub fn handle(&self, record: &LogRecord) -> io::Result<()> {
        if record.level_no() >= self.level as u32 {
            let output = self.format.format_record(record, self.colorize);
            self.sink.write_owned(output)
        } else {
            Ok(())
        }
    }
}
