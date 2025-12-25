use std::collections::HashMap;
use std::io;
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};

use chrono::{DateTime, Local};
use pyo3::prelude::*;

use crate::format::FormatConfig;
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

/// Log record containing all information about a log message
#[derive(Clone, Debug)]
pub struct LogRecord {
    pub timestamp: DateTime<Local>,
    pub level: LogLevel,
    pub level_info: Option<LevelInfo>,
    pub message: String,
    pub extra: Arc<HashMap<String, String>>,
    pub exception: Option<String>,
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
}

impl ConsoleHandler {
    pub fn new(level: LogLevel) -> Self {
        ConsoleHandler {
            level,
            format: FormatConfig::default(),
            colorize: true,
        }
    }

    pub fn with_format(level: LogLevel, format: FormatConfig) -> Self {
        let colorize = !format.serialize;
        ConsoleHandler {
            level,
            format,
            colorize,
        }
    }

    pub fn handle(&self, record: &LogRecord) -> io::Result<()> {
        if record.level_no() >= self.level as u32 {
            let output = self.format.format_record(record, self.colorize);
            println!("{}", output);
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
