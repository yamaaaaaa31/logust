mod format;
mod handler;
mod level;
mod sink;

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use std::sync::atomic::{AtomicU32, Ordering};

use parking_lot::RwLock;
use pyo3::intern;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyTuple};

pub use format::{FormatConfig, LOGGER_START_TIME, TokenRequirements, format_elapsed};
pub use handler::{
    CallerInfo, ConsoleHandler, FileHandler, HandlerEntry, HandlerType, LogRecord, ProcessInfo,
    ThreadInfo, empty_context,
};
pub use level::{LevelInfo, LogLevel, get_level_by_no, get_level_info, register_level};
pub use sink::{FileSink, FileSinkConfig, Rotation};

/// Built-in levels used to precompute per-emit-level token requirements (Python passes `level_value`).
const EMIT_LEVELS: [LogLevel; 8] = [
    LogLevel::Trace,
    LogLevel::Debug,
    LogLevel::Info,
    LogLevel::Success,
    LogLevel::Warning,
    LogLevel::Error,
    LogLevel::Fail,
    LogLevel::Critical,
];

/// Requirements for a formatted callable sink (`ParsedCallableTemplate` on Python).
/// Bool order matches [`ParsedCallableTemplate::lightweight_requirements_for_rust`].
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct FormattedSinkRequirements {
    pub needs_timestamp: bool,
    pub needs_level: bool,
    pub needs_name: bool,
    pub needs_function: bool,
    pub needs_line: bool,
    pub needs_file: bool,
    pub needs_elapsed: bool,
    pub needs_thread: bool,
    pub needs_process: bool,
    pub needs_message: bool,
    pub needs_nested_extra: bool,
    /// Keys referenced as `extra[key]` in the template (empty if none).
    pub extra_keys: Vec<String>,
}

impl FormattedSinkRequirements {
    fn from_python_tuples(
        req: &Bound<'_, PyTuple>,
        extra_keys: &Bound<'_, PyTuple>,
    ) -> PyResult<Self> {
        if req.len() != 11 {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "requirements tuple must have 11 bool fields",
            ));
        }
        let mut keys = Vec::with_capacity(extra_keys.len());
        for i in 0..extra_keys.len() {
            keys.push(extra_keys.get_item(i)?.extract::<String>()?);
        }
        Ok(Self {
            needs_timestamp: req.get_item(0)?.extract()?,
            needs_level: req.get_item(1)?.extract()?,
            needs_name: req.get_item(2)?.extract()?,
            needs_function: req.get_item(3)?.extract()?,
            needs_line: req.get_item(4)?.extract()?,
            needs_file: req.get_item(5)?.extract()?,
            needs_elapsed: req.get_item(6)?.extract()?,
            needs_thread: req.get_item(7)?.extract()?,
            needs_process: req.get_item(8)?.extract()?,
            needs_message: req.get_item(9)?.extract()?,
            needs_nested_extra: req.get_item(10)?.extract()?,
            extra_keys: keys,
        })
    }

    fn as_token_requirements(&self) -> TokenRequirements {
        TokenRequirements {
            needs_caller: self.needs_name
                || self.needs_function
                || self.needs_line
                || self.needs_file,
            needs_thread: self.needs_thread,
            needs_process: self.needs_process,
            needs_time: self.needs_timestamp,
            needs_level: self.needs_level,
            needs_message: self.needs_message,
            needs_elapsed: self.needs_elapsed,
        }
    }
}

/// Raw callbacks receive a full record dict; formatted sinks receive a minimal dict for templates.
pub enum CallbackKind {
    Raw,
    FormattedLight(FormattedSinkRequirements),
}

/// Callback entry for log record callbacks
pub struct CallbackEntry {
    pub id: u64,
    pub callback: Py<PyAny>,
    pub level: LogLevel,
    pub kind: CallbackKind,
}

/// Merge handler + callback token requirements eligible when emitting at severity `emit_no`
/// (numeric level value: built-in `LogLevel` as u32 or custom `LevelInfo.no`).
fn merge_token_requirements_for_emit_no(
    handlers: &[HandlerEntry],
    callbacks: &[CallbackEntry],
    emit_no: u32,
) -> TokenRequirements {
    let mut combined = TokenRequirements::default();
    for entry in handlers.iter() {
        if emit_no >= entry.handler.level() as u32 {
            combined = combined.merge(&entry.handler.requirements());
        }
    }

    let mut any_raw = false;
    for entry in callbacks.iter() {
        if emit_no < entry.level as u32 {
            continue;
        }
        match &entry.kind {
            CallbackKind::Raw => {
                any_raw = true;
            }
            CallbackKind::FormattedLight(req) => {
                combined = combined.merge(&req.as_token_requirements());
            }
        }
    }

    if any_raw {
        combined = TokenRequirements::all();
    }

    let has_filter = handlers
        .iter()
        .any(|e| e.filter.is_some() && emit_no >= e.handler.level() as u32);
    if has_filter {
        combined = TokenRequirements::all();
    }

    combined
}

/// Handler formats only (no callbacks), merged for handlers eligible at `emit_no`.
fn merge_handler_only_requirements_for_emit_no(
    handlers: &[HandlerEntry],
    emit_no: u32,
) -> TokenRequirements {
    let mut combined = TokenRequirements::default();
    for entry in handlers.iter() {
        if emit_no >= entry.handler.level() as u32 {
            combined = combined.merge(&entry.handler.requirements());
        }
    }
    combined
}

#[pyclass]
pub struct PyLogger {
    /// All handlers (console + files)
    handlers: Arc<RwLock<Vec<HandlerEntry>>>,
    /// Bound context (extra fields) - immutable after creation for zero-copy sharing
    context: Arc<HashMap<String, String>>,
    /// Registered callbacks
    callbacks: Arc<RwLock<Vec<CallbackEntry>>>,
    /// Cached minimum log level across all handlers and callbacks (shared via Arc)
    cached_min_level: Arc<AtomicU32>,
    /// Precomputed token requirements for built-in emit levels; arbitrary `emit_no` values are memoized on miss.
    cached_requirements_by_level: Arc<RwLock<HashMap<u32, TokenRequirements>>>,
    /// Cached token requirements for handlers only (excludes callbacks)
    cached_handler_requirements: Arc<RwLock<TokenRequirements>>,
}

#[pymethods]
impl PyLogger {
    #[new]
    #[pyo3(signature = (level=None))]
    fn new(level: Option<LogLevel>) -> Self {
        let logger = PyLogger {
            handlers: Arc::new(RwLock::new(Vec::new())),
            context: empty_context(),
            callbacks: Arc::new(RwLock::new(Vec::new())),
            cached_min_level: Arc::new(AtomicU32::new(u32::MAX)),
            cached_requirements_by_level: Arc::new(RwLock::new(HashMap::new())),
            cached_handler_requirements: Arc::new(RwLock::new(TokenRequirements::default())),
        };

        let console_level = level.unwrap_or_default();
        let console_handler = ConsoleHandler::new(console_level);
        let entry = HandlerEntry {
            id: handler::next_handler_id(),
            handler: HandlerType::Console(console_handler),
            filter: None,
        };
        logger.handlers.write().push(entry);
        logger.update_min_level_cache();
        logger.update_requirements_cache();

        logger
    }

    /// Add a file handler
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (path, level=None, format=None, rotation=None, retention=None, compression=None, serialize=None, filter=None, enqueue=None))]
    fn add(
        &self,
        path: String,
        level: Option<LogLevel>,
        format: Option<String>,
        rotation: Option<String>,
        retention: Option<String>,
        compression: Option<bool>,
        serialize: Option<bool>,
        filter: Option<Py<PyAny>>,
        enqueue: Option<bool>,
    ) -> PyResult<u64> {
        let level = level.unwrap_or(LogLevel::Debug);
        let serialize = serialize.unwrap_or(false);
        let format_config = FormatConfig::new(format, serialize);

        let (time_rotation, max_size) = rotation
            .as_ref()
            .map(|r| sink::parse_rotation(r))
            .unwrap_or((Rotation::Never, None));

        let (retention_days, retention_count) = retention
            .as_ref()
            .map(|r| sink::parse_retention(r))
            .unwrap_or((None, None));

        let config = FileSinkConfig {
            path: PathBuf::from(path),
            rotation: time_rotation,
            max_size,
            retention_days,
            retention_count,
            compression: compression.unwrap_or(false),
            enqueue: enqueue.unwrap_or(false),
        };

        let sink = FileSink::new(config)
            .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))?;

        let id = handler::next_handler_id();
        let file_handler = FileHandler::with_format(sink, level, format_config);
        let entry = HandlerEntry {
            id,
            handler: HandlerType::File(file_handler),
            filter,
        };

        self.handlers.write().push(entry);
        self.update_min_level_cache();
        self.update_requirements_cache();
        Ok(id)
    }

    /// Add a console handler (stdout or stderr)
    #[pyo3(signature = (stream, level=None, format=None, serialize=None, filter=None, colorize=None))]
    fn add_console(
        &self,
        stream: String,
        level: Option<LogLevel>,
        format: Option<String>,
        serialize: Option<bool>,
        filter: Option<Py<PyAny>>,
        colorize: Option<bool>,
    ) -> PyResult<u64> {
        let level = level.unwrap_or(LogLevel::Debug);
        let serialize = serialize.unwrap_or(false);
        let colorize = colorize.unwrap_or(!serialize);
        let format_config = FormatConfig::new(format, serialize);
        if stream != "stdout" && stream != "stderr" {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "stream must be 'stdout' or 'stderr'",
            ));
        }
        let use_stderr = stream == "stderr";

        let id = handler::next_handler_id();
        let console_handler =
            ConsoleHandler::with_options(level, format_config, colorize, use_stderr);
        let entry = HandlerEntry {
            id,
            handler: HandlerType::Console(console_handler),
            filter,
        };

        self.handlers.write().push(entry);
        self.update_min_level_cache();
        self.update_requirements_cache();
        Ok(id)
    }

    /// Remove a handler by ID, or remove all handlers if None
    #[pyo3(signature = (handler_id=None))]
    fn remove(&self, handler_id: Option<u64>) -> bool {
        let mut handlers = self.handlers.write();

        let result = if let Some(id) = handler_id {
            if let Some(pos) = handlers.iter().position(|h| h.id == id) {
                handlers.remove(pos);
                true
            } else {
                false
            }
        } else {
            handlers.clear();
            true
        };
        drop(handlers); // Release lock before updating cache
        self.update_min_level_cache();
        self.update_requirements_cache();
        result
    }

    /// Bind context values and return a new logger (zero-copy when no new keys)
    fn bind(&self, py: Python, kwargs: Option<&Bound<'_, PyDict>>) -> PyResult<Py<PyLogger>> {
        let new_context = match kwargs {
            None => Arc::clone(&self.context),
            Some(dict) if dict.is_empty() => Arc::clone(&self.context),
            Some(dict) => {
                let mut ctx = (*self.context).clone();
                for (key, value) in dict.iter() {
                    let key_str: String = key.extract()?;
                    let value_str: String = value.str()?.to_string();
                    ctx.insert(key_str, value_str);
                }
                Arc::new(ctx)
            }
        };

        let new_logger = PyLogger {
            handlers: Arc::clone(&self.handlers),
            context: new_context,
            callbacks: Arc::clone(&self.callbacks),
            cached_min_level: Arc::clone(&self.cached_min_level),
            cached_requirements_by_level: Arc::clone(&self.cached_requirements_by_level),
            cached_handler_requirements: Arc::clone(&self.cached_handler_requirements),
        };
        Py::new(py, new_logger)
    }

    /// Set minimum log level for all console handlers
    fn set_level(&self, level: LogLevel) {
        {
            let mut handlers = self.handlers.write();
            for entry in handlers.iter_mut() {
                if let HandlerType::Console(ref mut h) = entry.handler {
                    h.level = level;
                }
            }
        }
        self.update_min_level_cache();
        self.update_requirements_cache();
    }

    /// Get current minimum log level (from first console handler)
    fn get_level(&self) -> LogLevel {
        let handlers = self.handlers.read();
        for entry in handlers.iter() {
            if let HandlerType::Console(ref h) = entry.handler {
                return h.level;
            }
        }
        LogLevel::Debug
    }

    /// Check if any handler would accept messages at the given level (O(1) via `cached_min_level`).
    fn is_level_enabled(&self, level: LogLevel) -> bool {
        let m = self.cached_min_level.load(Ordering::Relaxed);
        (level as u32) >= m
    }

    /// Get the cached minimum log level across all handlers and callbacks
    #[getter]
    fn min_level(&self) -> u32 {
        self.cached_min_level.load(Ordering::Relaxed)
    }

    /// True if a maximal-severity emit would need caller info (merge of all handlers/callbacks).
    #[getter]
    fn needs_caller_info(&self) -> bool {
        self.token_requirements_for_emit_no(u32::MAX).needs_caller
    }

    #[getter]
    fn needs_thread_info(&self) -> bool {
        self.token_requirements_for_emit_no(u32::MAX).needs_thread
    }

    #[getter]
    fn needs_process_info(&self) -> bool {
        self.token_requirements_for_emit_no(u32::MAX).needs_process
    }

    /// Resolve ``level`` / numeric ``no`` the same way as [`Self::log`], for Python emit-scoped collection.
    fn try_resolve_emit_level_no(&self, level_arg: &Bound<'_, PyAny>) -> Option<u32> {
        if let Ok(lvl_name) = level_arg.extract::<String>() {
            get_level_info(&lvl_name).map(|i| i.no)
        } else if let Ok(no) = level_arg.extract::<u32>() {
            get_level_by_no(no).map(|i| i.no)
        } else {
            None
        }
    }

    fn needs_caller_info_for_emit_no(&self, emit_no: u32) -> bool {
        self.token_requirements_for_emit_no(emit_no).needs_caller
    }

    fn needs_thread_info_for_emit_no(&self, emit_no: u32) -> bool {
        self.token_requirements_for_emit_no(emit_no).needs_thread
    }

    fn needs_process_info_for_emit_no(&self, emit_no: u32) -> bool {
        self.token_requirements_for_emit_no(emit_no).needs_process
    }

    /// Single merge for Python: ``(needs_caller, needs_thread, needs_process)`` at ``emit_no``.
    fn collect_needs_for_emit_no(&self, emit_no: u32) -> (bool, bool, bool) {
        let t = self.token_requirements_for_emit_no(emit_no);
        (t.needs_caller, t.needs_thread, t.needs_process)
    }

    /// Handler formats only at ``emit_no`` (untracked default console vs tracked handlers).
    fn handler_only_needs_for_emit_no(&self, emit_no: u32) -> (bool, bool, bool) {
        let handlers = self.handlers.read();
        let t = merge_handler_only_requirements_for_emit_no(&handlers, emit_no);
        (t.needs_caller, t.needs_thread, t.needs_process)
    }

    /// Back-compat: `level_value` is a built-in `LogLevel` discriminant (5–50).
    fn needs_caller_info_for_level(&self, level_value: u8) -> bool {
        self.needs_caller_info_for_emit_no(level_value as u32)
    }

    fn needs_thread_info_for_level(&self, level_value: u8) -> bool {
        self.needs_thread_info_for_emit_no(level_value as u32)
    }

    fn needs_process_info_for_level(&self, level_value: u8) -> bool {
        self.needs_process_info_for_emit_no(level_value as u32)
    }

    /// Check if any handler format needs caller info (excludes callbacks)
    /// Used for auto-detect when there might be untracked handlers
    #[getter]
    fn needs_caller_info_for_handlers(&self) -> bool {
        self.cached_handler_requirements.read().needs_caller
    }

    /// Check if any handler format needs thread info (excludes callbacks)
    #[getter]
    fn needs_thread_info_for_handlers(&self) -> bool {
        self.cached_handler_requirements.read().needs_thread
    }

    /// Check if any handler format needs process info (excludes callbacks)
    #[getter]
    fn needs_process_info_for_handlers(&self) -> bool {
        self.cached_handler_requirements.read().needs_process
    }

    /// Get the current number of handlers (excludes callbacks)
    #[getter]
    fn handler_count(&self) -> usize {
        self.handlers.read().len()
    }

    /// Disable console output
    fn disable(&self) {
        {
            let mut handlers = self.handlers.write();
            handlers.retain(|entry| !matches!(entry.handler, HandlerType::Console(_)));
        }
        self.update_min_level_cache();
        self.update_requirements_cache();
    }

    /// Enable console output with given level
    #[pyo3(signature = (level=None))]
    fn enable(&self, level: Option<LogLevel>) {
        {
            let mut handlers = self.handlers.write();

            let has_console = handlers
                .iter()
                .any(|e| matches!(e.handler, HandlerType::Console(_)));

            if !has_console {
                let console_level = level.unwrap_or(LogLevel::Debug);
                let console_handler = ConsoleHandler::new(console_level);
                let entry = HandlerEntry {
                    id: handler::next_handler_id(),
                    handler: HandlerType::Console(console_handler),
                    filter: None,
                };
                handlers.push(entry);
            }
        }
        self.update_min_level_cache();
        self.update_requirements_cache();
    }

    /// Check if console output is enabled
    fn is_enabled(&self) -> bool {
        let handlers = self.handlers.read();
        handlers
            .iter()
            .any(|e| matches!(e.handler, HandlerType::Console(_)))
    }

    /// Flush all file handlers to ensure pending logs are written
    fn complete(&self) -> PyResult<()> {
        let handlers = self.handlers.read();
        for entry in handlers.iter() {
            if let HandlerType::File(ref h) = entry.handler {
                h.sink
                    .flush()
                    .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))?;
            }
        }
        Ok(())
    }

    /// Add a callback to receive full log record dicts (raw callback).
    #[pyo3(signature = (callback, level=None))]
    fn add_callback(&self, callback: Py<PyAny>, level: Option<LogLevel>) -> u64 {
        let id = handler::next_handler_id();
        let entry = CallbackEntry {
            id,
            callback,
            level: level.unwrap_or(LogLevel::Debug),
            kind: CallbackKind::Raw,
        };
        self.callbacks.write().push(entry);
        self.update_min_level_cache();
        self.update_requirements_cache();
        id
    }

    /// Add a formatted callable sink callback (minimal dict + Python `ParsedCallableTemplate`).
    #[pyo3(signature = (callback, requirements, extra_keys, level=None))]
    fn add_formatted_sink_callback(
        &self,
        callback: Py<PyAny>,
        requirements: Bound<'_, PyTuple>,
        extra_keys: Bound<'_, PyTuple>,
        level: Option<LogLevel>,
    ) -> PyResult<u64> {
        let req = FormattedSinkRequirements::from_python_tuples(&requirements, &extra_keys)?;
        let id = handler::next_handler_id();
        let entry = CallbackEntry {
            id,
            callback,
            level: level.unwrap_or(LogLevel::Debug),
            kind: CallbackKind::FormattedLight(req),
        };
        self.callbacks.write().push(entry);
        self.update_min_level_cache();
        self.update_requirements_cache();
        Ok(id)
    }

    /// Remove a callback by ID
    fn remove_callback(&self, callback_id: u64) -> bool {
        let result = {
            let mut callbacks = self.callbacks.write();
            if let Some(pos) = callbacks.iter().position(|c| c.id == callback_id) {
                callbacks.remove(pos);
                true
            } else {
                false
            }
        };
        self.update_min_level_cache();
        self.update_requirements_cache();
        result
    }

    /// Remove multiple callbacks by IDs (batch operation)
    /// More efficient than calling remove_callback multiple times
    /// as it only updates caches once at the end.
    /// Uses O(n+m) HashSet + retain instead of O(n*m) position + remove.
    fn remove_callbacks(&self, callback_ids: Vec<u64>) -> usize {
        let id_set: std::collections::HashSet<u64> = callback_ids.into_iter().collect();
        let removed = {
            let mut callbacks = self.callbacks.write();
            let before = callbacks.len();
            callbacks.retain(|c| !id_set.contains(&c.id));
            before - callbacks.len()
        };
        if removed > 0 {
            self.update_min_level_cache();
            self.update_requirements_cache();
        }
        removed
    }

    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (message, exception=None, name=None, function=None, line=None, file=None, thread_name=None, thread_id=None, process_name=None, process_id=None))]
    fn trace(
        &self,
        message: String,
        exception: Option<String>,
        name: Option<String>,
        function: Option<String>,
        line: Option<u32>,
        file: Option<String>,
        thread_name: Option<String>,
        thread_id: Option<u64>,
        process_name: Option<String>,
        process_id: Option<u32>,
    ) {
        self._log(
            LogLevel::Trace,
            message,
            exception,
            name,
            function,
            line,
            file,
            thread_name,
            thread_id,
            process_name,
            process_id,
        );
    }

    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (message, exception=None, name=None, function=None, line=None, file=None, thread_name=None, thread_id=None, process_name=None, process_id=None))]
    fn debug(
        &self,
        message: String,
        exception: Option<String>,
        name: Option<String>,
        function: Option<String>,
        line: Option<u32>,
        file: Option<String>,
        thread_name: Option<String>,
        thread_id: Option<u64>,
        process_name: Option<String>,
        process_id: Option<u32>,
    ) {
        self._log(
            LogLevel::Debug,
            message,
            exception,
            name,
            function,
            line,
            file,
            thread_name,
            thread_id,
            process_name,
            process_id,
        );
    }

    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (message, exception=None, name=None, function=None, line=None, file=None, thread_name=None, thread_id=None, process_name=None, process_id=None))]
    fn info(
        &self,
        message: String,
        exception: Option<String>,
        name: Option<String>,
        function: Option<String>,
        line: Option<u32>,
        file: Option<String>,
        thread_name: Option<String>,
        thread_id: Option<u64>,
        process_name: Option<String>,
        process_id: Option<u32>,
    ) {
        self._log(
            LogLevel::Info,
            message,
            exception,
            name,
            function,
            line,
            file,
            thread_name,
            thread_id,
            process_name,
            process_id,
        );
    }

    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (message, exception=None, name=None, function=None, line=None, file=None, thread_name=None, thread_id=None, process_name=None, process_id=None))]
    fn success(
        &self,
        message: String,
        exception: Option<String>,
        name: Option<String>,
        function: Option<String>,
        line: Option<u32>,
        file: Option<String>,
        thread_name: Option<String>,
        thread_id: Option<u64>,
        process_name: Option<String>,
        process_id: Option<u32>,
    ) {
        self._log(
            LogLevel::Success,
            message,
            exception,
            name,
            function,
            line,
            file,
            thread_name,
            thread_id,
            process_name,
            process_id,
        );
    }

    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (message, exception=None, name=None, function=None, line=None, file=None, thread_name=None, thread_id=None, process_name=None, process_id=None))]
    fn warning(
        &self,
        message: String,
        exception: Option<String>,
        name: Option<String>,
        function: Option<String>,
        line: Option<u32>,
        file: Option<String>,
        thread_name: Option<String>,
        thread_id: Option<u64>,
        process_name: Option<String>,
        process_id: Option<u32>,
    ) {
        self._log(
            LogLevel::Warning,
            message,
            exception,
            name,
            function,
            line,
            file,
            thread_name,
            thread_id,
            process_name,
            process_id,
        );
    }

    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (message, exception=None, name=None, function=None, line=None, file=None, thread_name=None, thread_id=None, process_name=None, process_id=None))]
    fn error(
        &self,
        message: String,
        exception: Option<String>,
        name: Option<String>,
        function: Option<String>,
        line: Option<u32>,
        file: Option<String>,
        thread_name: Option<String>,
        thread_id: Option<u64>,
        process_name: Option<String>,
        process_id: Option<u32>,
    ) {
        self._log(
            LogLevel::Error,
            message,
            exception,
            name,
            function,
            line,
            file,
            thread_name,
            thread_id,
            process_name,
            process_id,
        );
    }

    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (message, exception=None, name=None, function=None, line=None, file=None, thread_name=None, thread_id=None, process_name=None, process_id=None))]
    fn fail(
        &self,
        message: String,
        exception: Option<String>,
        name: Option<String>,
        function: Option<String>,
        line: Option<u32>,
        file: Option<String>,
        thread_name: Option<String>,
        thread_id: Option<u64>,
        process_name: Option<String>,
        process_id: Option<u32>,
    ) {
        self._log(
            LogLevel::Fail,
            message,
            exception,
            name,
            function,
            line,
            file,
            thread_name,
            thread_id,
            process_name,
            process_id,
        );
    }

    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (message, exception=None, name=None, function=None, line=None, file=None, thread_name=None, thread_id=None, process_name=None, process_id=None))]
    fn critical(
        &self,
        message: String,
        exception: Option<String>,
        name: Option<String>,
        function: Option<String>,
        line: Option<u32>,
        file: Option<String>,
        thread_name: Option<String>,
        thread_id: Option<u64>,
        process_name: Option<String>,
        process_id: Option<u32>,
    ) {
        self._log(
            LogLevel::Critical,
            message,
            exception,
            name,
            function,
            line,
            file,
            thread_name,
            thread_id,
            process_name,
            process_id,
        );
    }

    /// Register a custom log level
    #[pyo3(signature = (name, no, color=None, icon=None))]
    fn level(
        &self,
        name: String,
        no: u32,
        color: Option<String>,
        icon: Option<String>,
    ) -> PyResult<()> {
        let info = LevelInfo::new(name, no, color, icon);
        register_level(info);
        Ok(())
    }

    /// Log at any level (built-in or custom)
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (level_arg, message, exception=None, name=None, function=None, line=None, file=None, thread_name=None, thread_id=None, process_name=None, process_id=None))]
    fn log(
        &self,
        level_arg: &Bound<'_, PyAny>,
        message: String,
        exception: Option<String>,
        name: Option<String>,
        function: Option<String>,
        line: Option<u32>,
        file: Option<String>,
        thread_name: Option<String>,
        thread_id: Option<u64>,
        process_name: Option<String>,
        process_id: Option<u32>,
    ) -> PyResult<()> {
        let level_info = if let Ok(lvl_name) = level_arg.extract::<String>() {
            get_level_info(&lvl_name)
        } else if let Ok(no) = level_arg.extract::<u32>() {
            get_level_by_no(no)
        } else {
            None
        };

        let info = level_info
            .ok_or_else(|| pyo3::exceptions::PyValueError::new_err("Invalid log level"))?;

        self._log_custom(
            info,
            message,
            exception,
            name,
            function,
            line,
            file,
            thread_name,
            thread_id,
            process_name,
            process_id,
        );
        Ok(())
    }
}

impl PyLogger {
    /// Update the cached minimum level across all handlers and callbacks
    fn update_min_level_cache(&self) {
        let handlers = self.handlers.read();
        let callbacks = self.callbacks.read();

        let min_handler = handlers
            .iter()
            .map(|e| e.handler.level() as u32)
            .min()
            .unwrap_or(u32::MAX);

        let min_callback = callbacks
            .iter()
            .map(|e| e.level as u32)
            .min()
            .unwrap_or(u32::MAX);

        self.cached_min_level
            .store(min_handler.min(min_callback), Ordering::Relaxed);
    }

    /// Update the cached token requirements per built-in emit level (handlers + eligible callbacks).
    fn update_requirements_cache(&self) {
        let handlers = self.handlers.read();
        let callbacks = self.callbacks.read();

        let mut handler_only = TokenRequirements::default();

        // Merge requirements from all handlers (this is the handler-only requirements)
        for entry in handlers.iter() {
            let req = entry.handler.requirements();
            handler_only = handler_only.merge(&req);
        }

        // Cache handler-only requirements (excludes callbacks)
        *self.cached_handler_requirements.write() = handler_only;

        let mut map = HashMap::new();

        for &emit_level in &EMIT_LEVELS {
            let emit_no = emit_level as u32;
            let combined = merge_token_requirements_for_emit_no(&handlers, &callbacks, emit_no);
            map.insert(emit_no, combined);
        }

        *self.cached_requirements_by_level.write() = map;
    }

    /// Merge result for `emit_no`, using the precomputed map and memoizing misses.
    fn token_requirements_for_emit_no(&self, emit_no: u32) -> TokenRequirements {
        {
            let map = self.cached_requirements_by_level.read();
            if let Some(t) = map.get(&emit_no) {
                return *t;
            }
        }
        let merged = {
            let handlers = self.handlers.read();
            let callbacks = self.callbacks.read();
            merge_token_requirements_for_emit_no(&handlers, &callbacks, emit_no)
        };
        let mut map = self.cached_requirements_by_level.write();
        if let Some(t) = map.get(&emit_no) {
            return *t;
        }
        map.insert(emit_no, merged);
        merged
    }

    /// Internal log method - optimized for performance
    #[inline]
    #[allow(clippy::too_many_arguments)]
    fn _log(
        &self,
        level: LogLevel,
        message: String,
        exception: Option<String>,
        name: Option<String>,
        function: Option<String>,
        line: Option<u32>,
        file: Option<String>,
        thread_name: Option<String>,
        thread_id: Option<u64>,
        process_name: Option<String>,
        process_id: Option<u32>,
    ) {
        let handlers = self.handlers.read();
        let callbacks = self.callbacks.read();

        let mut has_eligible_handler = false;
        let mut has_eligible_filtered_handler = false;
        for e in handlers.iter() {
            if level >= e.handler.level() {
                has_eligible_handler = true;
                if e.filter.is_some() {
                    has_eligible_filtered_handler = true;
                }
            }
        }
        let has_eligible_callback = callbacks.iter().any(|e| level >= e.level);

        if !has_eligible_handler && !has_eligible_callback {
            return;
        }

        let has_callbacks = !callbacks.is_empty() && has_eligible_callback;
        let needs_gil = has_callbacks || has_eligible_filtered_handler;

        let extra = Arc::clone(&self.context);

        let caller = CallerInfo::with_file(
            name.unwrap_or_default(),
            function.unwrap_or_default(),
            line.unwrap_or(0),
            file.unwrap_or_default(),
        );

        let thread = ThreadInfo {
            name: thread_name.unwrap_or_default(),
            id: thread_id.unwrap_or(0),
        };

        let process = ProcessInfo {
            name: process_name.unwrap_or_default(),
            id: process_id.unwrap_or(0),
        };

        let record = LogRecord::with_all(level, message, extra, exception, caller, thread, process);

        if needs_gil {
            Python::attach(|py| {
                let need_full_dict = has_eligible_filtered_handler
                    || callbacks
                        .iter()
                        .any(|e| level >= e.level && matches!(e.kind, CallbackKind::Raw));

                let shared_full: Option<Bound<'_, PyDict>> = if need_full_dict {
                    Some(Self::build_record_dict(py, level, &record))
                } else {
                    None
                };

                for entry in callbacks.iter() {
                    if level < entry.level {
                        continue;
                    }
                    match &entry.kind {
                        CallbackKind::Raw => {
                            let full = shared_full
                                .as_ref()
                                .expect("raw callback implies full dict was built");
                            let _ = entry.callback.call1(py, (full.clone(),));
                        }
                        CallbackKind::FormattedLight(req) => {
                            let mini = Self::build_mini_record_dict(py, level, &record, req)
                                .expect("build_mini_record_dict");
                            let _ = entry.callback.call1(py, (mini,));
                        }
                    }
                }

                for entry in handlers.iter() {
                    if level < entry.handler.level() {
                        continue;
                    }
                    if let Some(ref filter) = entry.filter {
                        let full = shared_full
                            .as_ref()
                            .expect("handler filter implies full dict was built");
                        let passes = filter
                            .call1(py, (full.clone(),))
                            .and_then(|result| result.is_truthy(py))
                            .unwrap_or(true);
                        if !passes {
                            continue;
                        }
                    }
                    let _ = entry.handler.handle(&record);
                }
            });
        } else {
            for entry in handlers.iter() {
                let _ = entry.handler.handle(&record);
            }
        }
    }

    /// Build a Python dict from log record for callbacks/filters
    #[inline]
    fn build_record_dict<'py>(
        py: Python<'py>,
        level: LogLevel,
        record: &LogRecord,
    ) -> Bound<'py, PyDict> {
        let dict = PyDict::new(py);

        // Extra FIRST (flat expansion for backward compat)
        // This allows built-in fields to take precedence and prevents spoofing
        let extra_dict = PyDict::new(py);
        for (key, value) in record.extra.iter() {
            let _ = dict.set_item(key.as_str(), value.as_str());
            let _ = extra_dict.set_item(key.as_str(), value.as_str());
        }

        // Basic fields (override any extra with same name)
        // Using intern!() to cache key strings for better performance
        let _ = dict.set_item(intern!(py, "level"), level.as_str());
        let _ = dict.set_item(intern!(py, "message"), &record.message);
        let _ = dict.set_item(intern!(py, "timestamp"), record.timestamp.to_rfc3339());

        // Caller info
        let _ = dict.set_item(intern!(py, "name"), &record.caller.name);
        let _ = dict.set_item(intern!(py, "function"), &record.caller.function);
        let _ = dict.set_item(intern!(py, "line"), record.caller.line);
        let _ = dict.set_item(intern!(py, "file"), &record.caller.file);

        // Thread/process info
        let _ = dict.set_item(intern!(py, "thread_name"), &record.thread.name);
        let _ = dict.set_item(intern!(py, "thread_id"), record.thread.id);
        let _ = dict.set_item(intern!(py, "process_name"), &record.process.name);
        let _ = dict.set_item(intern!(py, "process_id"), record.process.id);

        // Elapsed time
        let _ = dict.set_item(
            intern!(py, "elapsed"),
            format_elapsed(&LOGGER_START_TIME, &record.timestamp),
        );

        // Extra as nested dict (for {extra[key]} access)
        let _ = dict.set_item(intern!(py, "extra"), extra_dict);

        // Exception
        if let Some(ref exc) = record.exception {
            let _ = dict.set_item(intern!(py, "exception"), exc.as_str());
        }

        dict
    }

    /// Minimal Python dict for formatted callable sinks (matches `ParsedCallableTemplate.format` keys).
    fn build_mini_record_dict<'py>(
        py: Python<'py>,
        level: LogLevel,
        record: &LogRecord,
        req: &FormattedSinkRequirements,
    ) -> PyResult<Bound<'py, PyDict>> {
        let dict = PyDict::new(py);

        if req.needs_timestamp {
            let _ = dict.set_item(intern!(py, "timestamp"), record.timestamp.to_rfc3339());
        }
        if req.needs_level {
            let _ = dict.set_item(intern!(py, "level"), level.as_str());
        }
        if req.needs_name {
            let _ = dict.set_item(intern!(py, "name"), &record.caller.name);
        }
        if req.needs_function {
            let _ = dict.set_item(intern!(py, "function"), &record.caller.function);
        }
        if req.needs_line {
            let _ = dict.set_item(intern!(py, "line"), record.caller.line);
        }
        if req.needs_file {
            let _ = dict.set_item(intern!(py, "file"), &record.caller.file);
        }
        if req.needs_elapsed {
            let _ = dict.set_item(
                intern!(py, "elapsed"),
                format_elapsed(&LOGGER_START_TIME, &record.timestamp),
            );
        }
        if req.needs_thread {
            let _ = dict.set_item(intern!(py, "thread_name"), &record.thread.name);
            let _ = dict.set_item(intern!(py, "thread_id"), record.thread.id);
        }
        if req.needs_process {
            let _ = dict.set_item(intern!(py, "process_name"), &record.process.name);
            let _ = dict.set_item(intern!(py, "process_id"), record.process.id);
        }
        if req.needs_message {
            let _ = dict.set_item(intern!(py, "message"), &record.message);
        }
        if req.needs_nested_extra {
            let extra_dict = PyDict::new(py);
            if req.extra_keys.is_empty() {
                for (key, value) in record.extra.iter() {
                    let _ = extra_dict.set_item(key.as_str(), value.as_str());
                }
            } else {
                for key in &req.extra_keys {
                    if let Some(value) = record.extra.get(key) {
                        let _ = extra_dict.set_item(key.as_str(), value.as_str());
                    }
                }
            }
            let _ = dict.set_item(intern!(py, "extra"), extra_dict);
        }

        Ok(dict)
    }

    /// Internal log method for custom levels - optimized
    #[inline]
    #[allow(clippy::too_many_arguments)]
    fn _log_custom(
        &self,
        level_info: LevelInfo,
        message: String,
        exception: Option<String>,
        name: Option<String>,
        function: Option<String>,
        line: Option<u32>,
        file: Option<String>,
        thread_name: Option<String>,
        thread_id: Option<u64>,
        process_name: Option<String>,
        process_id: Option<u32>,
    ) {
        let handlers = self.handlers.read();
        let callbacks = self.callbacks.read();

        let level_no = level_info.no;
        let mut has_eligible_handler = false;
        let mut has_eligible_filtered_handler = false;
        for e in handlers.iter() {
            if level_no >= e.handler.level() as u32 {
                has_eligible_handler = true;
                if e.filter.is_some() {
                    has_eligible_filtered_handler = true;
                }
            }
        }
        let has_eligible_callback = callbacks.iter().any(|e| level_no >= e.level as u32);

        if !has_eligible_handler && !has_eligible_callback {
            return;
        }

        let has_callbacks = !callbacks.is_empty() && has_eligible_callback;
        let needs_gil = has_callbacks || has_eligible_filtered_handler;

        let extra = Arc::clone(&self.context);

        let caller = CallerInfo::with_file(
            name.unwrap_or_default(),
            function.unwrap_or_default(),
            line.unwrap_or(0),
            file.unwrap_or_default(),
        );

        let thread = ThreadInfo {
            name: thread_name.unwrap_or_default(),
            id: thread_id.unwrap_or(0),
        };

        let process = ProcessInfo {
            name: process_name.unwrap_or_default(),
            id: process_id.unwrap_or(0),
        };

        let record = LogRecord::with_custom_level_full(
            level_info.clone(),
            message,
            extra,
            exception,
            caller,
            thread,
            process,
        );

        if needs_gil {
            Python::attach(|py| {
                let dict = Self::build_custom_record_dict(py, &record);

                for entry in callbacks.iter() {
                    if level_no >= entry.level as u32 {
                        let _ = entry.callback.call1(py, (dict.clone(),));
                    }
                }

                for entry in handlers.iter() {
                    if level_no < entry.handler.level() as u32 {
                        continue;
                    }
                    if let Some(ref filter) = entry.filter {
                        let passes = filter
                            .call1(py, (dict.clone(),))
                            .and_then(|result| result.is_truthy(py))
                            .unwrap_or(true);
                        if !passes {
                            continue;
                        }
                    }
                    let _ = entry.handler.handle(&record);
                }
            });
        } else {
            for entry in handlers.iter() {
                let _ = entry.handler.handle(&record);
            }
        }
    }

    /// Build a Python dict from custom level record for callbacks/filters
    #[inline]
    fn build_custom_record_dict<'py>(py: Python<'py>, record: &LogRecord) -> Bound<'py, PyDict> {
        let dict = PyDict::new(py);
        // Using intern!() to cache key strings for better performance
        if let Some(ref info) = record.level_info {
            let _ = dict.set_item(intern!(py, "level"), &info.name);
            let _ = dict.set_item(intern!(py, "level_no"), info.no);
        }
        let _ = dict.set_item(intern!(py, "message"), &record.message);
        let _ = dict.set_item(intern!(py, "timestamp"), record.timestamp.to_rfc3339());

        let extra_dict = PyDict::new(py);
        for (key, value) in record.extra.iter() {
            let _ = dict.set_item(key.as_str(), value.as_str());
            let _ = extra_dict.set_item(key.as_str(), value.as_str());
        }

        let _ = dict.set_item(intern!(py, "name"), &record.caller.name);
        let _ = dict.set_item(intern!(py, "function"), &record.caller.function);
        let _ = dict.set_item(intern!(py, "line"), record.caller.line);
        let _ = dict.set_item(intern!(py, "file"), &record.caller.file);
        let _ = dict.set_item(intern!(py, "thread_name"), &record.thread.name);
        let _ = dict.set_item(intern!(py, "thread_id"), record.thread.id);
        let _ = dict.set_item(intern!(py, "process_name"), &record.process.name);
        let _ = dict.set_item(intern!(py, "process_id"), record.process.id);
        let _ = dict.set_item(
            intern!(py, "elapsed"),
            format_elapsed(&LOGGER_START_TIME, &record.timestamp),
        );
        let _ = dict.set_item(intern!(py, "extra"), extra_dict);

        if let Some(ref exc) = record.exception {
            let _ = dict.set_item(intern!(py, "exception"), exc.as_str());
        }
        dict
    }
}

#[pymodule]
fn _logust(py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<LogLevel>()?;

    m.add_class::<Rotation>()?;

    m.add_class::<PyLogger>()?;

    let default_logger = Py::new(py, PyLogger::new(None))?;
    m.add("logger", default_logger)?;

    Ok(())
}
