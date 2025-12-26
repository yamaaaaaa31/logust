use std::collections::HashMap;
use std::sync::LazyLock;

use chrono::{DateTime, Local};
use colored::Color;
use serde::Serialize;

use crate::handler::LogRecord;
use crate::level::LogLevel;

/// Logger initialization time for elapsed calculation
pub static LOGGER_START_TIME: LazyLock<DateTime<Local>> = LazyLock::new(Local::now);

/// Format elapsed time as HH:MM:SS.mmm
/// Handles negative durations (e.g., clock adjustment) by clamping to 0
pub fn format_elapsed(start: &DateTime<Local>, now: &DateTime<Local>) -> String {
    let duration = *now - *start;
    let total_millis = duration.num_milliseconds().max(0) as u64;
    let millis = (total_millis % 1000) as u32;
    let total_secs = total_millis / 1000;
    let hours = total_secs / 3600;
    let minutes = (total_secs % 3600) / 60;
    let seconds = total_secs % 60;
    format!("{:02}:{:02}:{:02}.{:03}", hours, minutes, seconds, millis)
}

/// Apply ANSI color code to text (thread-safe, no global state)
#[inline]
fn colorize_text(text: &str, color: Color, bold: bool) -> String {
    let color_code = match color {
        Color::Black => "30",
        Color::Red => "31",
        Color::Green => "32",
        Color::Yellow => "33",
        Color::Blue => "34",
        Color::Magenta => "35",
        Color::Cyan => "36",
        Color::White => "37",
        Color::BrightBlack => "90",
        Color::BrightRed => "91",
        Color::BrightGreen => "92",
        Color::BrightYellow => "93",
        Color::BrightBlue => "94",
        Color::BrightMagenta => "95",
        Color::BrightCyan => "96",
        Color::BrightWhite => "97",
        _ => "0", // Default/reset
    };

    if bold {
        format!("\x1b[1;{}m{}\x1b[0m", color_code, text)
    } else {
        format!("\x1b[{}m{}\x1b[0m", color_code, text)
    }
}

/// Apply dim style to text (thread-safe)
#[inline]
fn dim_text(text: &str) -> String {
    format!("\x1b[2m{}\x1b[0m", text)
}

/// Apply cyan color to text (thread-safe)
#[inline]
fn cyan_text(text: &str) -> String {
    format!("\x1b[36m{}\x1b[0m", text)
}

/// Default log format template (loguru-compatible with caller info)
const DEFAULT_FORMAT_TEMPLATE: &str = "{time} | {level:<8} | {name}:{function}:{line} - {message}";

/// Default time format with milliseconds
const DEFAULT_TIME_FORMAT: &str = "%Y-%m-%d %H:%M:%S%.3f";

/// Initial capacity hint for formatted result strings
const FORMAT_RESULT_CAPACITY: usize = 64;

/// Flags indicating which runtime information is needed for formatting
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct TokenRequirements {
    /// Needs caller info (name, module, function, line, file)
    pub needs_caller: bool,
    /// Needs thread info (thread name and id)
    pub needs_thread: bool,
    /// Needs process info (process name and id)
    pub needs_process: bool,
    /// Needs time formatting (for lazy computation optimization)
    pub needs_time: bool,
    /// Needs level formatting (for lazy computation optimization)
    pub needs_level: bool,
    /// Needs message formatting (for lazy computation optimization)
    pub needs_message: bool,
    /// Needs elapsed time (for lazy computation optimization)
    pub needs_elapsed: bool,
}

impl TokenRequirements {
    /// Merge requirements (OR operation)
    pub fn merge(&self, other: &TokenRequirements) -> TokenRequirements {
        TokenRequirements {
            needs_caller: self.needs_caller || other.needs_caller,
            needs_thread: self.needs_thread || other.needs_thread,
            needs_process: self.needs_process || other.needs_process,
            needs_time: self.needs_time || other.needs_time,
            needs_level: self.needs_level || other.needs_level,
            needs_message: self.needs_message || other.needs_message,
            needs_elapsed: self.needs_elapsed || other.needs_elapsed,
        }
    }

    /// All requirements enabled (for callbacks/filters that need full record)
    pub fn all() -> TokenRequirements {
        TokenRequirements {
            needs_caller: true,
            needs_thread: true,
            needs_process: true,
            needs_time: true,
            needs_level: true,
            needs_message: true,
            needs_elapsed: true,
        }
    }
}

/// Pre-parsed format token for efficient template rendering
#[derive(Clone, Debug)]
pub enum FormatToken {
    /// Static text segment
    Static(String),
    /// {time} placeholder
    Time,
    /// {level} placeholder (no width)
    Level,
    /// {level:<N} placeholder with width
    LevelWidth(usize),
    /// {message} placeholder
    Message,
    /// {extra[key]} placeholder
    Extra(String),
    /// {name} placeholder - module/logger name
    Name,
    /// {function} placeholder - function name
    Function,
    /// {line} placeholder - line number
    Line,
    /// {elapsed} placeholder - time since logger start
    Elapsed,
    /// {thread} placeholder - thread name:id
    Thread,
    /// {process} placeholder - process name:id
    Process,
    /// {file} placeholder - source file basename
    File,
    /// {module} placeholder - module name (alias for Name)
    Module,
}

/// Compute token requirements from parsed tokens
fn compute_requirements(tokens: &[FormatToken]) -> TokenRequirements {
    let mut reqs = TokenRequirements::default();
    for token in tokens {
        match token {
            FormatToken::Name
            | FormatToken::Module
            | FormatToken::Function
            | FormatToken::Line
            | FormatToken::File => {
                reqs.needs_caller = true;
            }
            FormatToken::Thread => {
                reqs.needs_thread = true;
            }
            FormatToken::Process => {
                reqs.needs_process = true;
            }
            FormatToken::Time => {
                reqs.needs_time = true;
            }
            FormatToken::Level | FormatToken::LevelWidth(_) => {
                reqs.needs_level = true;
            }
            FormatToken::Message => {
                reqs.needs_message = true;
            }
            FormatToken::Elapsed => {
                reqs.needs_elapsed = true;
            }
            _ => {}
        }
    }
    reqs
}

/// Parse a template string into tokens
fn parse_template(template: &str) -> Vec<FormatToken> {
    let mut tokens = Vec::new();
    let mut chars = template.chars().peekable();
    let mut static_buf = String::new();

    while let Some(c) = chars.next() {
        if c == '{' {
            let mut placeholder = String::new();
            while let Some(&ch) = chars.peek() {
                if ch == '}' {
                    chars.next();
                    break;
                }
                placeholder.push(chars.next().unwrap());
            }

            if !static_buf.is_empty() {
                tokens.push(FormatToken::Static(std::mem::take(&mut static_buf)));
            }

            if placeholder == "time" {
                tokens.push(FormatToken::Time);
            } else if placeholder == "message" {
                tokens.push(FormatToken::Message);
            } else if placeholder == "level" {
                tokens.push(FormatToken::Level);
            } else if placeholder == "name" {
                tokens.push(FormatToken::Name);
            } else if placeholder == "function" {
                tokens.push(FormatToken::Function);
            } else if placeholder == "line" {
                tokens.push(FormatToken::Line);
            } else if placeholder == "elapsed" {
                tokens.push(FormatToken::Elapsed);
            } else if placeholder == "thread" {
                tokens.push(FormatToken::Thread);
            } else if placeholder == "process" {
                tokens.push(FormatToken::Process);
            } else if placeholder == "file" {
                tokens.push(FormatToken::File);
            } else if placeholder == "module" {
                tokens.push(FormatToken::Module);
            } else if let Some(width_str) = placeholder.strip_prefix("level:<") {
                if let Ok(width) = width_str.parse::<usize>() {
                    tokens.push(FormatToken::LevelWidth(width));
                } else {
                    static_buf.push('{');
                    static_buf.push_str(&placeholder);
                    static_buf.push('}');
                }
            } else if placeholder.starts_with("extra[") && placeholder.ends_with(']') {
                let key = &placeholder[6..placeholder.len() - 1];
                tokens.push(FormatToken::Extra(key.to_string()));
            } else {
                static_buf.push('{');
                static_buf.push_str(&placeholder);
                static_buf.push('}');
            }
        } else {
            static_buf.push(c);
        }
    }

    if !static_buf.is_empty() {
        tokens.push(FormatToken::Static(static_buf));
    }

    tokens
}

/// Convert tag name to ANSI escape code (returns static string to avoid allocation)
fn tag_to_ansi(tag: &str) -> Option<&'static str> {
    match tag.to_ascii_lowercase().as_str() {
        "red" => Some("\x1b[31m"),
        "green" => Some("\x1b[32m"),
        "yellow" => Some("\x1b[33m"),
        "blue" => Some("\x1b[34m"),
        "magenta" => Some("\x1b[35m"),
        "cyan" => Some("\x1b[36m"),
        "white" => Some("\x1b[37m"),
        "black" => Some("\x1b[30m"),

        "bright_red" | "light-red" => Some("\x1b[91m"),
        "bright_green" | "light-green" => Some("\x1b[92m"),
        "bright_yellow" | "light-yellow" => Some("\x1b[93m"),
        "bright_blue" | "light-blue" => Some("\x1b[94m"),
        "bright_magenta" | "light-magenta" => Some("\x1b[95m"),
        "bright_cyan" | "light-cyan" => Some("\x1b[96m"),
        "bright_white" | "light-white" => Some("\x1b[97m"),

        "bold" | "b" => Some("\x1b[1m"),
        "dim" => Some("\x1b[2m"),
        "italic" | "i" => Some("\x1b[3m"),
        "underline" | "u" => Some("\x1b[4m"),
        "strike" | "s" => Some("\x1b[9m"),

        _ => None,
    }
}

/// Parse and apply color markup tags to text
/// Supports: <red>, <bold>, <italic>, etc.
pub fn apply_color_markup(text: &str) -> String {
    if !text.contains('<') {
        return text.to_string();
    }

    let mut result = String::with_capacity(text.len());
    let mut chars = text.chars().peekable();
    let mut style_stack: Vec<&'static str> = Vec::new();

    while let Some(c) = chars.next() {
        if c == '<' {
            let mut tag = String::new();
            let is_closing = chars.peek() == Some(&'/');
            if is_closing {
                chars.next();
            }

            let mut found_close = false;
            while let Some(&ch) = chars.peek() {
                if ch == '>' {
                    chars.next();
                    found_close = true;
                    break;
                }
                tag.push(chars.next().unwrap());
            }

            if !found_close {
                result.push('<');
                if is_closing {
                    result.push('/');
                }
                result.push_str(&tag);
                continue;
            }

            if is_closing {
                if tag_to_ansi(&tag).is_some() && !style_stack.is_empty() {
                    style_stack.pop();
                    result.push_str("\x1b[0m");
                    for s in &style_stack {
                        result.push_str(s);
                    }
                } else {
                    result.push_str("</");
                    result.push_str(&tag);
                    result.push('>');
                }
            } else if let Some(ansi) = tag_to_ansi(&tag) {
                style_stack.push(ansi);
                result.push_str(ansi);
            } else {
                result.push('<');
                result.push_str(&tag);
                result.push('>');
            }
        } else {
            result.push(c);
        }
    }

    if !style_stack.is_empty() {
        result.push_str("\x1b[0m");
    }

    result
}

/// Format configuration for log output
#[derive(Clone, Debug)]
pub struct FormatConfig {
    /// Format template string
    pub template: String,
    /// Pre-parsed template tokens for efficient rendering
    tokens: Vec<FormatToken>,
    /// Whether to serialize as JSON
    pub serialize: bool,
    /// Time format string
    pub time_format: String,
    /// Computed requirements based on tokens
    requirements: TokenRequirements,
}

impl Default for FormatConfig {
    fn default() -> Self {
        let template = DEFAULT_FORMAT_TEMPLATE.to_string();
        let tokens = parse_template(&template);
        let requirements = compute_requirements(&tokens);
        FormatConfig {
            template,
            tokens,
            serialize: false,
            time_format: DEFAULT_TIME_FORMAT.to_string(),
            requirements,
        }
    }
}

impl FormatConfig {
    /// Create a new format config
    pub fn new(template: Option<String>, serialize: bool) -> Self {
        let template = template.unwrap_or_else(|| DEFAULT_FORMAT_TEMPLATE.to_string());
        let tokens = parse_template(&template);
        let requirements = compute_requirements(&tokens);
        FormatConfig {
            template,
            tokens,
            serialize,
            time_format: DEFAULT_TIME_FORMAT.to_string(),
            requirements,
        }
    }

    /// Get token requirements for this format
    pub fn requirements(&self) -> TokenRequirements {
        self.requirements
    }

    /// Format a log record
    pub fn format(
        &self,
        timestamp: &DateTime<Local>,
        level: LogLevel,
        message: &str,
        extra: &HashMap<String, String>,
        exception: &Option<String>,
        colorize: bool,
    ) -> String {
        if self.serialize {
            self.format_json(timestamp, level, message, extra, exception)
        } else {
            self.format_template(timestamp, level, message, extra, exception, colorize)
        }
    }

    /// Format a LogRecord (supports both built-in and custom levels)
    pub fn format_record(&self, record: &LogRecord, colorize: bool) -> String {
        if self.serialize {
            self.format_record_json(record)
        } else {
            self.format_record_template(record, colorize)
        }
    }

    /// Format a LogRecord using pre-parsed tokens (O(n) single pass, thread-safe)
    fn format_record_template(&self, record: &LogRecord, colorize: bool) -> String {
        let reqs = &self.requirements;

        // Lazy computation: only compute if token is needed
        let level_name = record.level_name();
        let level_color = record
            .level_info
            .as_ref()
            .map(|info| info.get_color())
            .unwrap_or_else(|| record.level.color());

        // Lazy time formatting - only compute if {time} token is in format
        let time_fmt = if reqs.needs_time {
            let time_raw = record.timestamp.format(&self.time_format).to_string();
            if colorize {
                Some(dim_text(&time_raw))
            } else {
                Some(time_raw)
            }
        } else {
            None
        };

        // Lazy level formatting - only compute if {level} token is in format
        let level_fmt = if reqs.needs_level {
            if colorize {
                Some(colorize_text(level_name, level_color, true))
            } else {
                Some(level_name.to_string())
            }
        } else {
            None
        };

        // Lazy message formatting - only compute if {message} token is in format
        let message_fmt = if reqs.needs_message {
            if colorize {
                Some(apply_color_markup(&record.message))
            } else {
                Some(record.message.clone())
            }
        } else {
            None
        };

        let mut result = String::with_capacity(self.template.len() + FORMAT_RESULT_CAPACITY);

        for token in &self.tokens {
            match token {
                FormatToken::Static(s) => result.push_str(s),
                FormatToken::Time => {
                    if let Some(ref fmt) = time_fmt {
                        result.push_str(fmt);
                    }
                }
                FormatToken::Message => {
                    if let Some(ref fmt) = message_fmt {
                        result.push_str(fmt);
                    }
                }
                FormatToken::Level => {
                    if let Some(ref fmt) = level_fmt {
                        result.push_str(fmt);
                    }
                }
                FormatToken::LevelWidth(width) => {
                    let padded = format!("{:<width$}", level_name, width = width);
                    if colorize {
                        result.push_str(&colorize_text(&padded, level_color, true));
                    } else {
                        result.push_str(&padded);
                    }
                }
                FormatToken::Extra(key) => {
                    if let Some(value) = record.extra.get(key) {
                        result.push_str(value);
                    }
                }
                FormatToken::Name => {
                    if colorize {
                        result.push_str(&cyan_text(&record.caller.name));
                    } else {
                        result.push_str(&record.caller.name);
                    }
                }
                FormatToken::Function => {
                    if colorize {
                        result.push_str(&cyan_text(&record.caller.function));
                    } else {
                        result.push_str(&record.caller.function);
                    }
                }
                FormatToken::Line => {
                    let line_str = record.caller.line.to_string();
                    if colorize {
                        result.push_str(&cyan_text(&line_str));
                    } else {
                        result.push_str(&line_str);
                    }
                }
                FormatToken::Elapsed => {
                    let elapsed = format_elapsed(&LOGGER_START_TIME, &record.timestamp);
                    if colorize {
                        result.push_str(&dim_text(&elapsed));
                    } else {
                        result.push_str(&elapsed);
                    }
                }
                FormatToken::Thread => {
                    let thread_str = format!("{}:{}", record.thread.name, record.thread.id);
                    if colorize {
                        result.push_str(&cyan_text(&thread_str));
                    } else {
                        result.push_str(&thread_str);
                    }
                }
                FormatToken::Process => {
                    let process_str = format!("{}:{}", record.process.name, record.process.id);
                    if colorize {
                        result.push_str(&cyan_text(&process_str));
                    } else {
                        result.push_str(&process_str);
                    }
                }
                FormatToken::File => {
                    if colorize {
                        result.push_str(&cyan_text(&record.caller.file));
                    } else {
                        result.push_str(&record.caller.file);
                    }
                }
                FormatToken::Module => {
                    // Alias for Name
                    if colorize {
                        result.push_str(&cyan_text(&record.caller.name));
                    } else {
                        result.push_str(&record.caller.name);
                    }
                }
            }
        }

        if let Some(ref exc) = record.exception {
            result.push('\n');
            result.push_str(exc);
        }

        result
    }

    /// Format a LogRecord as JSON
    fn format_record_json(&self, record: &LogRecord) -> String {
        #[derive(Serialize)]
        struct JsonRecord<'a> {
            time: String,
            level: &'a str,
            message: &'a str,
            #[serde(skip_serializing_if = "str::is_empty")]
            name: &'a str,
            #[serde(skip_serializing_if = "str::is_empty")]
            function: &'a str,
            #[serde(skip_serializing_if = "is_zero")]
            line: u32,
            #[serde(skip_serializing_if = "HashMap::is_empty")]
            extra: &'a HashMap<String, String>,
            #[serde(skip_serializing_if = "Option::is_none")]
            exception: &'a Option<String>,
        }

        fn is_zero(n: &u32) -> bool {
            *n == 0
        }

        let json_record = JsonRecord {
            time: record.timestamp.format(&self.time_format).to_string(),
            level: record.level_name(),
            message: &record.message,
            name: &record.caller.name,
            function: &record.caller.function,
            line: record.caller.line,
            extra: &record.extra,
            exception: &record.exception,
        };

        serde_json::to_string(&json_record).unwrap_or_else(|_| record.message.clone())
    }

    /// Format using pre-parsed tokens (O(n) single pass, thread-safe)
    fn format_template(
        &self,
        timestamp: &DateTime<Local>,
        level: LogLevel,
        message: &str,
        extra: &HashMap<String, String>,
        exception: &Option<String>,
        colorize: bool,
    ) -> String {
        let level_name = level.as_str();
        let level_color = level.color();

        let time_raw = timestamp.format(&self.time_format).to_string();
        let time_fmt = if colorize {
            dim_text(&time_raw)
        } else {
            time_raw
        };

        let level_fmt = if colorize {
            colorize_text(level_name, level_color, true)
        } else {
            level_name.to_string()
        };

        let message_fmt = if colorize {
            apply_color_markup(message)
        } else {
            message.to_string()
        };

        let mut result = String::with_capacity(self.template.len() + FORMAT_RESULT_CAPACITY);

        for token in &self.tokens {
            match token {
                FormatToken::Static(s) => result.push_str(s),
                FormatToken::Time => result.push_str(&time_fmt),
                FormatToken::Message => result.push_str(&message_fmt),
                FormatToken::Level => result.push_str(&level_fmt),
                FormatToken::LevelWidth(width) => {
                    let padded = format!("{:<width$}", level_name, width = width);
                    if colorize {
                        result.push_str(&colorize_text(&padded, level_color, true));
                    } else {
                        result.push_str(&padded);
                    }
                }
                FormatToken::Extra(key) => {
                    if let Some(value) = extra.get(key) {
                        result.push_str(value);
                    }
                }
                // These tokens are not available in this context (no caller/thread/process info)
                FormatToken::Name
                | FormatToken::Function
                | FormatToken::Line
                | FormatToken::Elapsed
                | FormatToken::Thread
                | FormatToken::Process
                | FormatToken::File
                | FormatToken::Module => {}
            }
        }

        if let Some(exc) = exception {
            result.push('\n');
            result.push_str(exc);
        }

        result
    }

    /// Format as JSON
    fn format_json(
        &self,
        timestamp: &DateTime<Local>,
        level: LogLevel,
        message: &str,
        extra: &HashMap<String, String>,
        exception: &Option<String>,
    ) -> String {
        #[derive(Serialize)]
        struct JsonRecord<'a> {
            time: String,
            level: &'a str,
            message: &'a str,
            #[serde(skip_serializing_if = "HashMap::is_empty")]
            extra: &'a HashMap<String, String>,
            #[serde(skip_serializing_if = "Option::is_none")]
            exception: &'a Option<String>,
        }

        let record = JsonRecord {
            time: timestamp.format(&self.time_format).to_string(),
            level: level.as_str(),
            message,
            extra,
            exception,
        };

        serde_json::to_string(&record).unwrap_or_else(|_| message.to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_format() {
        let config = FormatConfig::default();
        let now = Local::now();
        let extra = HashMap::new();

        let result = config.format(&now, LogLevel::Info, "test message", &extra, &None, false);
        assert!(result.contains("INFO"));
        assert!(result.contains("test message"));
    }

    #[test]
    fn test_json_format() {
        let config = FormatConfig::new(None, true);
        let now = Local::now();
        let extra = HashMap::new();

        let result = config.format(
            &now,
            LogLevel::Error,
            "error occurred",
            &extra,
            &None,
            false,
        );
        assert!(result.contains("\"level\":\"ERROR\""));
        assert!(result.contains("\"message\":\"error occurred\""));
    }

    #[test]
    fn test_custom_template() {
        let config = FormatConfig::new(Some("[{level}] {message}".to_string()), false);
        let now = Local::now();
        let extra = HashMap::new();

        let result = config.format(&now, LogLevel::Warning, "warning!", &extra, &None, false);
        assert_eq!(result, "[WARNING] warning!");
    }

    #[test]
    fn test_extra_fields() {
        let config =
            FormatConfig::new(Some("{message} - user={extra[user_id]}".to_string()), false);
        let now = Local::now();
        let mut extra = HashMap::new();
        extra.insert("user_id".to_string(), "123".to_string());

        let result = config.format(&now, LogLevel::Info, "login", &extra, &None, false);
        assert_eq!(result, "login - user=123");
    }

    #[test]
    fn test_exception_in_template() {
        let config = FormatConfig::new(Some("[{level}] {message}".to_string()), false);
        let now = Local::now();
        let extra = HashMap::new();
        let exception = Some("Traceback:\n  File test.py".to_string());

        let result = config.format(&now, LogLevel::Error, "Failed", &extra, &exception, false);
        assert!(result.contains("[ERROR] Failed"));
        assert!(result.contains("Traceback:"));
    }

    #[test]
    fn test_exception_in_json() {
        let config = FormatConfig::new(None, true);
        let now = Local::now();
        let extra = HashMap::new();
        let exception = Some("Traceback".to_string());

        let result = config.format(&now, LogLevel::Error, "Failed", &extra, &exception, false);
        assert!(result.contains("\"exception\":\"Traceback\""));
    }

    #[test]
    fn test_color_markup_basic() {
        let result = apply_color_markup("<red>error</red>");
        assert!(result.contains("\x1b[31m"));
        assert!(result.contains("\x1b[0m"));
        assert!(result.contains("error"));
    }

    #[test]
    fn test_color_markup_nested() {
        let result = apply_color_markup("<bold><green>success</green></bold>");
        assert!(result.contains("\x1b[1m"));
        assert!(result.contains("\x1b[32m"));
        assert!(result.contains("success"));
    }

    #[test]
    fn test_color_markup_invalid_tag() {
        let result = apply_color_markup("<invalid>text</invalid>");
        assert_eq!(result, "<invalid>text</invalid>");
    }

    #[test]
    fn test_color_markup_no_tags() {
        let result = apply_color_markup("plain text");
        assert_eq!(result, "plain text");
    }

    #[test]
    fn test_color_markup_styles() {
        let bold = apply_color_markup("<bold>text</bold>");
        assert!(bold.contains("\x1b[1m"));

        let italic = apply_color_markup("<italic>text</italic>");
        assert!(italic.contains("\x1b[3m"));

        let underline = apply_color_markup("<underline>text</underline>");
        assert!(underline.contains("\x1b[4m"));
    }

    #[test]
    fn test_parse_template() {
        let tokens = parse_template(DEFAULT_FORMAT_TEMPLATE);
        // Template: "{time} | {level:<8} | {name}:{function}:{line} - {message}"
        assert_eq!(tokens.len(), 11);
        assert!(matches!(tokens[0], FormatToken::Time));
        assert!(matches!(&tokens[1], FormatToken::Static(s) if s == " | "));
        assert!(matches!(tokens[2], FormatToken::LevelWidth(8)));
        assert!(matches!(&tokens[3], FormatToken::Static(s) if s == " | "));
        assert!(matches!(tokens[4], FormatToken::Name));
        assert!(matches!(&tokens[5], FormatToken::Static(s) if s == ":"));
        assert!(matches!(tokens[6], FormatToken::Function));
        assert!(matches!(&tokens[7], FormatToken::Static(s) if s == ":"));
        assert!(matches!(tokens[8], FormatToken::Line));
        assert!(matches!(&tokens[9], FormatToken::Static(s) if s == " - "));
        assert!(matches!(tokens[10], FormatToken::Message));
    }

    #[test]
    fn test_parse_template_extra() {
        let tokens = parse_template("{message} user={extra[user_id]}");
        assert_eq!(tokens.len(), 3);
        assert!(matches!(tokens[0], FormatToken::Message));
        assert!(matches!(&tokens[1], FormatToken::Static(s) if s == " user="));
        assert!(matches!(&tokens[2], FormatToken::Extra(k) if k == "user_id"));
    }
}
