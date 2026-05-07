use std::collections::{HashMap, HashSet};
use std::fmt;
use std::io;
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

impl ExtraValue {
    pub fn from_py(value: &Bound<'_, PyAny>) -> PyResult<Self> {
        let kind = FastKind::classify(value)?;
        let text = value.str()?.to_string();

        match kind {
            FastKind::None => Ok(Self {
                text,
                json: Value::Null,
            }),
            FastKind::Bool(b) => Ok(Self {
                text,
                json: Value::Bool(b),
            }),
            FastKind::Str(s) => Ok(Self {
                text,
                json: Value::String(s),
            }),
            FastKind::I64(n) => Ok(Self {
                text,
                json: Value::Number(Number::from(n)),
            }),
            FastKind::U64(n) => Ok(Self {
                text,
                json: Value::Number(Number::from(n)),
            }),
            FastKind::Slow => {
                let mut seen = HashSet::new();
                let json = py_to_json_value(value, 0, &mut seen)?;
                Ok(Self { text, json })
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
}

impl From<String> for ExtraValue {
    fn from(value: String) -> Self {
        Self {
            text: value.clone(),
            json: Value::String(value),
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
    pub file: String,
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
    pub level_info: Option<LevelInfo>,
    pub message: String,
    pub extra: Arc<ExtraMap>,
    pub exception: Option<String>,
    pub caller: CallerInfo,
    pub thread: ThreadInfo,
    pub process: ProcessInfo,
}

impl LogRecord {
    /// Create a new log record
    pub fn new(level: LogLevel, message: String) -> Self {
        LogRecord {
            timestamp: Local::now(),
            level,
            level_info: None,
            message,
            extra: empty_context(),
            exception: None,
            caller: CallerInfo::default(),
            thread: ThreadInfo::default(),
            process: ProcessInfo::default(),
        }
    }

    /// Create a new log record with extra context (Arc reference - zero-copy)
    pub fn with_extra(level: LogLevel, message: String, extra: Arc<ExtraMap>) -> Self {
        LogRecord {
            timestamp: Local::now(),
            level,
            level_info: None,
            message,
            extra,
            exception: None,
            caller: CallerInfo::default(),
            thread: ThreadInfo::default(),
            process: ProcessInfo::default(),
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
            timestamp: Local::now(),
            level,
            level_info: None,
            message,
            extra,
            exception,
            caller,
            thread: ThreadInfo::default(),
            process: ProcessInfo::default(),
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
            timestamp: Local::now(),
            level,
            level_info: None,
            message,
            extra,
            exception,
            caller,
            thread,
            process,
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
            timestamp: Local::now(),
            level,
            level_info: None,
            message,
            extra,
            exception,
            caller: CallerInfo::default(),
            thread: ThreadInfo::default(),
            process: ProcessInfo::default(),
        }
    }

    /// Create a log record with custom level info (Arc reference - zero-copy)
    pub fn with_custom_level(
        level_info: LevelInfo,
        message: String,
        extra: Arc<ExtraMap>,
        exception: Option<String>,
    ) -> Self {
        LogRecord {
            timestamp: Local::now(),
            level: LogLevel::Debug, // Placeholder, not used for custom levels
            level_info: Some(level_info),
            message,
            extra,
            exception,
            caller: CallerInfo::default(),
            thread: ThreadInfo::default(),
            process: ProcessInfo::default(),
        }
    }

    /// Create a log record with custom level info and caller
    pub fn with_custom_level_and_caller(
        level_info: LevelInfo,
        message: String,
        extra: Arc<ExtraMap>,
        exception: Option<String>,
        caller: CallerInfo,
    ) -> Self {
        LogRecord {
            timestamp: Local::now(),
            level: LogLevel::Debug,
            level_info: Some(level_info),
            message,
            extra,
            exception,
            caller,
            thread: ThreadInfo::default(),
            process: ProcessInfo::default(),
        }
    }

    /// Create a log record with custom level info, caller, thread and process
    pub fn with_custom_level_full(
        level_info: LevelInfo,
        message: String,
        extra: Arc<ExtraMap>,
        exception: Option<String>,
        caller: CallerInfo,
        thread: ThreadInfo,
        process: ProcessInfo,
    ) -> Self {
        LogRecord {
            timestamp: Local::now(),
            level: LogLevel::Debug,
            level_info: Some(level_info),
            message,
            extra,
            exception,
            caller,
            thread,
            process,
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

/// Handler entry with ID and optional filter
pub struct HandlerEntry {
    pub id: u64,
    pub handler: HandlerType,
    /// Optional filter callable (Python lambda/function)
    pub filter: Option<Py<PyAny>>,
}

/// Console handler for terminal output
pub struct ConsoleHandler {
    pub level: LogLevel,
    pub format: FormatConfig,
    pub colorize: bool,
    pub use_stderr: bool,
}

impl ConsoleHandler {
    pub fn new(level: LogLevel) -> Self {
        ConsoleHandler {
            level,
            format: FormatConfig::default(),
            colorize: true,
            use_stderr: false,
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
            let output = self.format.format_record(record, self.colorize);
            if self.use_stderr {
                eprintln!("{}", output);
            } else {
                println!("{}", output);
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
}

impl FileHandler {
    pub fn new(sink: FileSink, level: LogLevel) -> Self {
        FileHandler {
            sink,
            level,
            format: FormatConfig::default(),
        }
    }

    pub fn with_format(sink: FileSink, level: LogLevel, format: FormatConfig) -> Self {
        FileHandler {
            sink,
            level,
            format,
        }
    }

    #[inline]
    pub fn handle(&self, record: &LogRecord) -> io::Result<()> {
        if record.level_no() >= self.level as u32 {
            let output = self.format.format_record(record, false);
            self.sink.write_owned(output)
        } else {
            Ok(())
        }
    }
}
