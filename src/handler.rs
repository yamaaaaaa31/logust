use std::collections::HashMap;
use std::io;
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};

use chrono::{DateTime, Local};
use pyo3::prelude::*;

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
static EMPTY_CONTEXT: std::sync::LazyLock<Arc<HashMap<String, String>>> =
    std::sync::LazyLock::new(|| Arc::new(HashMap::new()));

/// Get empty context (zero-cost)
#[inline]
pub fn empty_context() -> Arc<HashMap<String, String>> {
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
    pub extra: Arc<HashMap<String, String>>,
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
    pub fn with_extra(
        level: LogLevel,
        message: String,
        extra: Arc<HashMap<String, String>>,
    ) -> Self {
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
        extra: Arc<HashMap<String, String>>,
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
        extra: Arc<HashMap<String, String>>,
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
        extra: Arc<HashMap<String, String>>,
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
        extra: Arc<HashMap<String, String>>,
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
        extra: Arc<HashMap<String, String>>,
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
        extra: Arc<HashMap<String, String>>,
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
