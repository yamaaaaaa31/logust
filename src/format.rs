use std::borrow::Cow;
use std::collections::HashMap;
use std::fmt::Write as _;
use std::sync::LazyLock;

use chrono::{DateTime, Datelike, Local, Timelike};
use colored::Color;
use serde::Serialize;

use crate::handler::{ExtraMap, LogRecord, write_extra_repr};
use crate::level::get_level_color;
use crate::time_format::{TimeSpec, push_num};

/// Logger initialization time for elapsed calculation
pub static LOGGER_START_TIME: LazyLock<DateTime<Local>> = LazyLock::new(Local::now);

/// Write elapsed time as HH:MM:SS.mmm into `out`.
/// Handles negative durations (e.g., clock adjustment) by clamping to 0.
fn write_elapsed(start: &DateTime<Local>, now: &DateTime<Local>, out: &mut String) {
    let duration = *now - *start;
    let total_millis = duration.num_milliseconds().max(0) as u64;
    let millis = (total_millis % 1000) as u32;
    let total_secs = total_millis / 1000;
    let hours = total_secs / 3600;
    let minutes = (total_secs % 3600) / 60;
    let seconds = total_secs % 60;
    push_num(out, hours, 2);
    out.push(':');
    push_num(out, minutes, 2);
    out.push(':');
    push_num(out, seconds, 2);
    out.push('.');
    push_num(out, u64::from(millis), 3);
}

/// Append `text` left-aligned in a field of `width` characters (like `{:<width$}`)
#[inline]
fn push_padded(out: &mut String, text: &str, width: usize) {
    out.push_str(text);
    for _ in text.chars().count()..width {
        out.push(' ');
    }
}

/// Format elapsed time as HH:MM:SS.mmm
/// Handles negative durations (e.g., clock adjustment) by clamping to 0
pub fn format_elapsed(start: &DateTime<Local>, now: &DateTime<Local>) -> String {
    let mut s = String::with_capacity(16);
    write_elapsed(start, now, &mut s);
    s
}

/// ANSI SGR prefix for bold text in `color` (`ESC[1;<code>m`)
#[inline]
fn bold_color_prefix(color: Color) -> &'static str {
    match color {
        Color::Black => "\x1b[1;30m",
        Color::Red => "\x1b[1;31m",
        Color::Green => "\x1b[1;32m",
        Color::Yellow => "\x1b[1;33m",
        Color::Blue => "\x1b[1;34m",
        Color::Magenta => "\x1b[1;35m",
        Color::Cyan => "\x1b[1;36m",
        Color::White => "\x1b[1;37m",
        Color::BrightBlack => "\x1b[1;90m",
        Color::BrightRed => "\x1b[1;91m",
        Color::BrightGreen => "\x1b[1;92m",
        Color::BrightYellow => "\x1b[1;93m",
        Color::BrightBlue => "\x1b[1;94m",
        Color::BrightMagenta => "\x1b[1;95m",
        Color::BrightCyan => "\x1b[1;96m",
        Color::BrightWhite => "\x1b[1;97m",
        _ => "\x1b[1;0m", // Default/reset
    }
}

/// ANSI reset
const RESET: &str = "\x1b[0m";
/// ANSI dim style (default style of `{time}` and `{elapsed}`)
const DIM: &str = "\x1b[2m";
/// ANSI cyan (default style of caller, thread and process fields)
const CYAN: &str = "\x1b[36m";

/// Append what `write` produces, wrapped in `prefix` and a reset when `styled`.
///
/// Renders straight into `out`: no intermediate string per token.
#[inline]
fn write_styled(out: &mut String, styled: bool, prefix: &str, write: impl FnOnce(&mut String)) {
    if styled {
        out.push_str(prefix);
    }
    write(out);
    if styled {
        out.push_str(RESET);
    }
}

/// Style `text` as the console styles the level `level_name` (bold, level color).
pub fn colorize_level(text: &str, level_name: &str) -> String {
    let color = get_level_color(level_name).unwrap_or(Color::White);
    let mut out = String::with_capacity(text.len() + 12);
    write_styled(&mut out, true, bold_color_prefix(color), |o| {
        o.push_str(text)
    });
    out
}

/// ANSI prefix that styles text like the level `level_name` (bold, level color).
pub fn level_style(level_name: &str) -> String {
    let color = get_level_color(level_name).unwrap_or(Color::White);
    bold_color_prefix(color).to_string()
}

/// Default log format template (loguru-compatible with caller info)
const DEFAULT_FORMAT_TEMPLATE: &str = "{time} | {level:<8} | {name}:{function}:{line} - {message}";

/// Default time format with milliseconds (`{time}` without a spec)
const DEFAULT_TIME_FORMAT: &str = "%Y-%m-%d %H:%M:%S%.3f";

/// Two ASCII decimal digits of `n` (`n` must be < 100)
#[inline]
fn two_digits(n: u32) -> [u8; 2] {
    [b'0' + (n / 10) as u8, b'0' + (n % 10) as u8]
}

/// Append `dt` as the default `{time}` (`%Y-%m-%d %H:%M:%S%.3f`).
///
/// Writes the digits directly instead of going through chrono's strftime
/// machinery, which re-parses the format string on every record. The output is
/// byte-identical to `dt.format(DEFAULT_TIME_FORMAT)`: years outside `0..=9999`
/// (which chrono prints with a sign) fall back to chrono.
pub fn write_default_time(dt: &DateTime<Local>, out: &mut String) {
    let local = dt.naive_local();
    let year = local.year();
    if !(0..=9999).contains(&year) {
        let _ = write!(out, "{}", dt.format(DEFAULT_TIME_FORMAT));
        return;
    }
    let nanos = local.nanosecond();
    // Like chrono's `%S`, a leap second (nanosecond >= 1e9) renders as "60"
    let second = local.second() + nanos / 1_000_000_000;
    let millis = nanos / 1_000_000 % 1000;

    let year = year as u32;
    let [c0, c1] = two_digits(year / 100);
    let [y0, y1] = two_digits(year % 100);
    let [mo0, mo1] = two_digits(local.month());
    let [d0, d1] = two_digits(local.day());
    let [h0, h1] = two_digits(local.hour());
    let [mi0, mi1] = two_digits(local.minute());
    let [s0, s1] = two_digits(second);
    let [ms1, ms2] = two_digits(millis % 100);
    let ms0 = b'0' + (millis / 100) as u8;
    let buf = [
        c0, c1, y0, y1, b'-', mo0, mo1, b'-', d0, d1, b' ', h0, h1, b':', mi0, mi1, b':', s0, s1,
        b'.', ms0, ms1, ms2,
    ];
    // SAFETY: `buf` holds only ASCII digits and punctuation, which is valid UTF-8
    // (`from_utf8` would validate the 23 bytes on every record)
    out.push_str(unsafe { std::str::from_utf8_unchecked(&buf) });
}

/// The default `{time}` rendering of `dt` as a new string
pub fn format_default_time(dt: &DateTime<Local>) -> String {
    let mut out = String::with_capacity(23);
    write_default_time(dt, &mut out);
    out
}

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
    /// {time:<spec>} placeholder with a precompiled loguru time spec
    TimeFormatted(Box<TimeSpec>),
    /// {level} placeholder (no width)
    Level,
    /// {level:<N} placeholder with width
    LevelWidth(usize),
    /// {level.no} placeholder - numeric severity
    LevelNo,
    /// {level.icon} placeholder
    LevelIcon,
    /// {message} placeholder
    Message,
    /// {extra[key]} placeholder
    Extra(String),
    /// {extra} placeholder - the whole extra dict, rendered like `str(dict)`
    ExtraAll,
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
    /// {thread.name} placeholder
    ThreadName,
    /// {thread.id} placeholder
    ThreadId,
    /// {process} placeholder - process name:id
    Process,
    /// {process.name} placeholder
    ProcessName,
    /// {process.id} placeholder
    ProcessId,
    /// {file} / {file.name} placeholder - source file basename
    File,
    /// {file.path} placeholder - source file path
    FilePath,
    /// {exception} placeholder - formatted traceback (empty without exception)
    Exception,
    /// {module} placeholder - module name (alias for Name)
    Module,
    /// Opening color markup tag in the template (`<red>`, `<level>`, ...)
    StyleOpen(MarkupStyle),
    /// Closing color markup tag in the template
    StyleClose,
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
            | FormatToken::File
            | FormatToken::FilePath => {
                reqs.needs_caller = true;
            }
            FormatToken::Thread | FormatToken::ThreadName | FormatToken::ThreadId => {
                reqs.needs_thread = true;
            }
            FormatToken::Process | FormatToken::ProcessName | FormatToken::ProcessId => {
                reqs.needs_process = true;
            }
            // `{time:<spec>}` renders from the record's timestamp itself
            FormatToken::Time => {
                reqs.needs_time = true;
            }
            FormatToken::Level
            | FormatToken::LevelWidth(_)
            | FormatToken::LevelNo
            | FormatToken::LevelIcon => {
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

/// Parse a template string into tokens.
///
/// Fails on an invalid `{time:<spec>}` (loguru raises on these too).
fn parse_template(template: &str) -> Result<Vec<FormatToken>, String> {
    let mut tokens = Vec::new();
    for piece in split_format_markup(template) {
        match piece {
            MarkupPiece::Text(text) => parse_placeholders(&text, &mut tokens)?,
            MarkupPiece::Open(style) => tokens.push(FormatToken::StyleOpen(style)),
            MarkupPiece::Close => tokens.push(FormatToken::StyleClose),
        }
    }
    Ok(tokens)
}

/// Token for a placeholder without format spec, if it is a known field
fn field_token(placeholder: &str) -> Option<FormatToken> {
    Some(match placeholder {
        "time" => FormatToken::Time,
        "message" => FormatToken::Message,
        "level" | "level.name" => FormatToken::Level,
        "level.no" => FormatToken::LevelNo,
        "level.icon" => FormatToken::LevelIcon,
        "name" => FormatToken::Name,
        "function" => FormatToken::Function,
        "line" => FormatToken::Line,
        "elapsed" => FormatToken::Elapsed,
        "thread" => FormatToken::Thread,
        "thread.name" => FormatToken::ThreadName,
        "thread.id" => FormatToken::ThreadId,
        "process" => FormatToken::Process,
        "process.name" => FormatToken::ProcessName,
        "process.id" => FormatToken::ProcessId,
        "file" | "file.name" => FormatToken::File,
        "file.path" => FormatToken::FilePath,
        "module" => FormatToken::Module,
        "exception" => FormatToken::Exception,
        "extra" => FormatToken::ExtraAll,
        _ => return None,
    })
}

/// Parse `{...}` placeholders in a markup-free piece of the template
fn parse_placeholders(template: &str, tokens: &mut Vec<FormatToken>) -> Result<(), String> {
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

            if let Some(token) = field_token(&placeholder) {
                tokens.push(token);
            } else if let Some(spec) = placeholder.strip_prefix("time:") {
                let spec = TimeSpec::parse(spec)?;
                tokens.push(FormatToken::TimeFormatted(Box::new(spec)));
            } else if let Some(width_str) = placeholder
                .strip_prefix("level:<")
                .or_else(|| placeholder.strip_prefix("level.name:<"))
            {
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
    Ok(())
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

/// Parse color markup tags (<red>, <bold>, <italic>, etc.) and render them as ANSI codes,
/// or strip them if `colorize` is false. Unknown tags are kept as literal text.
pub fn apply_color_markup(text: &str, colorize: bool) -> Cow<'_, str> {
    apply_color_markup_within(text, colorize, "")
}

/// Like [`apply_color_markup`], for text rendered inside `base` (ANSI prefix of the
/// surrounding styles): `base` is re-applied after each reset so it isn't lost.
pub fn apply_color_markup_within<'a>(text: &'a str, colorize: bool, base: &str) -> Cow<'a, str> {
    if !text.contains('<') {
        return Cow::Borrowed(text);
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
                    if colorize {
                        result.push_str("\x1b[0m");
                        result.push_str(base);
                        for s in &style_stack {
                            result.push_str(s);
                        }
                    }
                } else {
                    result.push_str("</");
                    result.push_str(&tag);
                    result.push('>');
                }
            } else if let Some(ansi) = tag_to_ansi(&tag) {
                style_stack.push(ansi);
                if colorize {
                    result.push_str(ansi);
                }
            } else {
                result.push('<');
                result.push_str(&tag);
                result.push('>');
            }
        } else {
            result.push(c);
        }
    }

    if colorize && !style_stack.is_empty() {
        result.push_str("\x1b[0m");
        result.push_str(base);
    }

    Cow::Owned(result)
}

/// A color style opened by a markup tag in a format template
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum MarkupStyle {
    /// Fixed ANSI style (`<red>`, `<bold>`, ...)
    Ansi(&'static str),
    /// `<level>`: the color of the record's level
    Level,
}

/// A piece of a format template after color markup is resolved
#[derive(Debug, PartialEq, Eq)]
pub enum MarkupPiece {
    /// Text without markup (may still contain `{...}` placeholders)
    Text(String),
    /// Opening tag
    Open(MarkupStyle),
    /// Closing tag matching an open one
    Close,
}

fn markup_style(tag: &str) -> Option<MarkupStyle> {
    if tag.eq_ignore_ascii_case("level") {
        Some(MarkupStyle::Level)
    } else {
        tag_to_ansi(tag).map(MarkupStyle::Ansi)
    }
}

/// Split color markup out of a format template.
///
/// `{...}` placeholders are skipped so `{level:<8}` is not read as a tag. Unknown tags and
/// closing tags without an open one are kept as literal text.
pub fn split_format_markup(template: &str) -> Vec<MarkupPiece> {
    let mut pieces = Vec::new();
    let mut text = String::new();
    let mut depth = 0usize;
    let mut rest = template;

    while let Some(pos) = rest.find(['<', '{']) {
        text.push_str(&rest[..pos]);
        rest = &rest[pos..];

        if rest.starts_with('{') {
            let end = rest.find('}').map_or(rest.len(), |i| i + 1);
            text.push_str(&rest[..end]);
            rest = &rest[end..];
            continue;
        }

        // A tag ends at the first '>' and contains no '<' or '{'
        let tag_end = rest[1..].find(['>', '<', '{']).map(|i| i + 1);
        let Some(end) = tag_end.filter(|&i| rest.as_bytes()[i] == b'>') else {
            text.push('<');
            rest = &rest[1..];
            continue;
        };

        let tag = &rest[1..end];
        let (is_closing, name) = match tag.strip_prefix('/') {
            Some(name) => (true, name),
            None => (false, tag),
        };

        match markup_style(name) {
            Some(_) if is_closing && depth > 0 => {
                depth -= 1;
                if !text.is_empty() {
                    pieces.push(MarkupPiece::Text(std::mem::take(&mut text)));
                }
                pieces.push(MarkupPiece::Close);
            }
            Some(style) if !is_closing => {
                depth += 1;
                if !text.is_empty() {
                    pieces.push(MarkupPiece::Text(std::mem::take(&mut text)));
                }
                pieces.push(MarkupPiece::Open(style));
            }
            _ => text.push_str(&rest[..=end]),
        }
        rest = &rest[end + 1..];
    }

    text.push_str(rest);
    if !text.is_empty() {
        pieces.push(MarkupPiece::Text(text));
    }
    pieces
}

/// ANSI prefix for a markup style
fn push_style(result: &mut String, style: MarkupStyle, level_color: Color) {
    match style {
        MarkupStyle::Ansi(ansi) => result.push_str(ansi),
        MarkupStyle::Level => result.push_str(bold_color_prefix(level_color)),
    }
}

/// Reset, then re-apply the styles still open
fn restore_styles(result: &mut String, styles: &[MarkupStyle], level_color: Color) {
    result.push_str(RESET);
    for &style in styles {
        push_style(result, style, level_color);
    }
}

/// ANSI prefix of the open template styles
fn styles_prefix(styles: &[MarkupStyle], level_color: Color) -> String {
    let mut prefix = String::new();
    for &style in styles {
        push_style(&mut prefix, style, level_color);
    }
    prefix
}

/// Render a template markup token. Returns false for non-markup tokens.
#[inline]
fn render_markup_token(
    token: &FormatToken,
    result: &mut String,
    styles: &mut Vec<MarkupStyle>,
    level_color: Color,
    colorize: bool,
) -> bool {
    match token {
        FormatToken::StyleOpen(style) => {
            styles.push(*style);
            if colorize {
                push_style(result, *style, level_color);
            }
            true
        }
        FormatToken::StyleClose => {
            styles.pop();
            if colorize {
                restore_styles(result, styles, level_color);
            }
            true
        }
        _ => false,
    }
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
    /// Computed requirements based on tokens
    requirements: TokenRequirements,
    /// Template places the exception itself (`{exception}`): don't append it
    has_exception_token: bool,
}

impl Default for FormatConfig {
    fn default() -> Self {
        Self::new(None, false)
    }
}

impl FormatConfig {
    /// Create a new format config.
    ///
    /// Panics on an invalid `{time:<spec>}`; use [`FormatConfig::try_new`] for user input.
    pub fn new(template: Option<String>, serialize: bool) -> Self {
        Self::try_new(template, serialize).unwrap_or_else(|err| panic!("{err}"))
    }

    /// Create a new format config, failing on an invalid `{time:<spec>}`
    pub fn try_new(template: Option<String>, serialize: bool) -> Result<Self, String> {
        let template = template.unwrap_or_else(|| DEFAULT_FORMAT_TEMPLATE.to_string());
        let tokens = if serialize {
            // The template is unused for JSON output
            parse_template(&template).unwrap_or_default()
        } else {
            parse_template(&template)?
        };
        let requirements = compute_requirements(&tokens);
        let has_exception_token = tokens.iter().any(|t| matches!(t, FormatToken::Exception));
        Ok(FormatConfig {
            template,
            tokens,
            serialize,
            requirements,
            has_exception_token,
        })
    }

    /// Get token requirements for this format
    pub fn requirements(&self) -> TokenRequirements {
        self.requirements
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
        let level_name = record.level_name();
        let level_color = record
            .level_info
            .as_ref()
            .map(|info| info.get_color())
            .unwrap_or_else(|| record.level.color());

        let mut result = String::with_capacity(self.template.len() + FORMAT_RESULT_CAPACITY);
        // Styles opened by template markup; tokens inside them keep the markup's color
        let mut styles: Vec<MarkupStyle> = Vec::new();

        for token in &self.tokens {
            if render_markup_token(token, &mut result, &mut styles, level_color, colorize) {
                continue;
            }
            // Default token styles apply only outside template markup
            let auto = colorize && styles.is_empty();
            let out = &mut result;
            match token {
                FormatToken::Static(s) => out.push_str(s),
                FormatToken::Time => write_styled(out, auto, DIM, |o| {
                    write_default_time(&record.timestamp, o);
                }),
                FormatToken::TimeFormatted(spec) => write_styled(out, auto, DIM, |o| {
                    spec.write(&record.timestamp, o);
                }),
                FormatToken::Message => {
                    if !record.message_markup {
                        // `opt(colors=False)`: markup in the message is plain text
                        out.push_str(&record.message);
                    } else if !colorize || styles.is_empty() {
                        out.push_str(&apply_color_markup(&record.message, colorize));
                    } else {
                        // Keep template styles alive across resets in the message markup
                        let base = styles_prefix(&styles, level_color);
                        out.push_str(&apply_color_markup_within(&record.message, true, &base));
                    }
                }
                FormatToken::Level => {
                    write_styled(out, auto, bold_color_prefix(level_color), |o| {
                        o.push_str(level_name);
                    })
                }
                FormatToken::LevelWidth(width) => {
                    write_styled(out, auto, bold_color_prefix(level_color), |o| {
                        push_padded(o, level_name, *width);
                    })
                }
                FormatToken::LevelNo => {
                    push_num(out, u64::from(record.level_no()), 0);
                }
                FormatToken::LevelIcon => out.push_str(record.level_icon()),
                FormatToken::Exception => {
                    if let Some(ref exc) = record.exception {
                        out.push_str(exc);
                    }
                }
                FormatToken::Extra(key) => {
                    if let Some(value) = record.extra.get(key) {
                        out.push_str(value.as_str());
                    }
                }
                FormatToken::ExtraAll => write_extra_repr(&record.extra, out),
                FormatToken::Name | FormatToken::Module => {
                    write_styled(out, auto, CYAN, |o| o.push_str(&record.caller.name))
                }
                FormatToken::Function => {
                    write_styled(out, auto, CYAN, |o| o.push_str(&record.caller.function))
                }
                FormatToken::Line => write_styled(out, auto, CYAN, |o| {
                    push_num(o, u64::from(record.caller.line), 0);
                }),
                FormatToken::Elapsed => write_styled(out, auto, DIM, |o| {
                    write_elapsed(&LOGGER_START_TIME, &record.timestamp, o);
                }),
                FormatToken::Thread => write_styled(out, auto, CYAN, |o| {
                    o.push_str(&record.thread.name);
                    o.push(':');
                    push_num(o, record.thread.id, 0);
                }),
                FormatToken::ThreadName => {
                    write_styled(out, auto, CYAN, |o| o.push_str(&record.thread.name))
                }
                FormatToken::ThreadId => write_styled(out, auto, CYAN, |o| {
                    push_num(o, record.thread.id, 0);
                }),
                FormatToken::ProcessName => {
                    write_styled(out, auto, CYAN, |o| o.push_str(&record.process.name))
                }
                FormatToken::ProcessId => write_styled(out, auto, CYAN, |o| {
                    push_num(o, u64::from(record.process.id), 0);
                }),
                FormatToken::Process => write_styled(out, auto, CYAN, |o| {
                    o.push_str(&record.process.name);
                    o.push(':');
                    push_num(o, u64::from(record.process.id), 0);
                }),
                FormatToken::File => {
                    write_styled(out, auto, CYAN, |o| o.push_str(record.caller.file_name()))
                }
                FormatToken::FilePath => {
                    write_styled(out, auto, CYAN, |o| o.push_str(&record.caller.file))
                }
                FormatToken::StyleOpen(_) | FormatToken::StyleClose => {}
            }
        }

        // Close styles left open by the template
        if colorize && !styles.is_empty() {
            result.push_str(RESET);
        }

        // `{exception}` in the template already placed it
        if let Some(ref exc) = record.exception
            && !self.has_exception_token
        {
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
            extra: &'a ExtraMap,
            #[serde(skip_serializing_if = "Option::is_none")]
            exception: &'a Option<String>,
        }

        fn is_zero(n: &u32) -> bool {
            *n == 0
        }

        let json_record = JsonRecord {
            time: format_default_time(&record.timestamp),
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
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;

    use crate::handler::empty_context;
    use crate::handler::{CallerInfo, ExtraValue, LogRecord, ProcessInfo, ThreadInfo};
    use crate::level::{LevelInfo, LogLevel};

    #[test]
    fn test_default_format() {
        let config = FormatConfig::default();
        let record = LogRecord::new(LogLevel::Info, "test message".into());

        let result = config.format_record(&record, false);
        assert!(result.contains("INFO"));
        assert!(result.contains("test message"));
    }

    #[test]
    fn test_json_format() {
        let config = FormatConfig::new(None, true);
        let record = LogRecord::new(LogLevel::Error, "error occurred".into());

        let result = config.format_record(&record, false);
        assert!(result.contains("\"level\":\"ERROR\""));
        assert!(result.contains("\"message\":\"error occurred\""));
    }

    #[test]
    fn test_custom_template() {
        let config = FormatConfig::new(Some("[{level}] {message}".to_string()), false);
        let record = LogRecord::new(LogLevel::Warning, "warning!".into());

        let result = config.format_record(&record, false);
        assert_eq!(result, "[WARNING] warning!");
    }

    #[test]
    fn test_extra_fields() {
        let config =
            FormatConfig::new(Some("{message} - user={extra[user_id]}".to_string()), false);
        let mut extra = HashMap::new();
        extra.insert("user_id".to_string(), ExtraValue::from("123"));
        let record = LogRecord::with_extra(LogLevel::Info, "login".into(), Arc::new(extra));

        let result = config.format_record(&record, false);
        assert_eq!(result, "login - user=123");
    }

    #[test]
    fn test_exception_in_template() {
        let config = FormatConfig::new(Some("[{level}] {message}".to_string()), false);
        let exception = Some("Traceback:\n  File test.py".to_string());
        let record =
            LogRecord::with_exception(LogLevel::Error, "Failed".into(), empty_context(), exception);

        let result = config.format_record(&record, false);
        assert!(result.contains("[ERROR] Failed"));
        assert!(result.contains("Traceback:"));
    }

    #[test]
    fn test_exception_in_json() {
        let config = FormatConfig::new(None, true);
        let exception = Some("Traceback".to_string());
        let record =
            LogRecord::with_exception(LogLevel::Error, "Failed".into(), empty_context(), exception);

        let result = config.format_record(&record, false);
        assert!(result.contains("\"exception\":\"Traceback\""));
    }

    #[test]
    fn test_color_markup_basic() {
        let result = apply_color_markup("<red>error</red>", true);
        assert!(result.contains("\x1b[31m"));
        assert!(result.contains("\x1b[0m"));
        assert!(result.contains("error"));
    }

    #[test]
    fn test_color_markup_nested() {
        let result = apply_color_markup("<bold><green>success</green></bold>", true);
        assert!(result.contains("\x1b[1m"));
        assert!(result.contains("\x1b[32m"));
        assert!(result.contains("success"));
    }

    #[test]
    fn test_color_markup_invalid_tag() {
        let result = apply_color_markup("<invalid>text</invalid>", true);
        assert_eq!(result, "<invalid>text</invalid>");
    }

    #[test]
    fn test_color_markup_no_tags() {
        let result = apply_color_markup("plain text", true);
        assert_eq!(result, "plain text");
    }

    #[test]
    fn test_color_markup_strip() {
        let result =
            apply_color_markup("<bold><green>ok</green></bold> <nope>x</nope></red>", false);
        assert_eq!(result, "ok <nope>x</nope></red>");
    }

    #[test]
    fn test_color_markup_styles() {
        let bold = apply_color_markup("<bold>text</bold>", true);
        assert!(bold.contains("\x1b[1m"));

        let italic = apply_color_markup("<italic>text</italic>", true);
        assert!(italic.contains("\x1b[3m"));

        let underline = apply_color_markup("<underline>text</underline>", true);
        assert!(underline.contains("\x1b[4m"));
    }

    #[test]
    fn test_parse_template() {
        let tokens = parse_template(DEFAULT_FORMAT_TEMPLATE).unwrap();
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
        let tokens = parse_template("{message} user={extra[user_id]}").unwrap();
        assert_eq!(tokens.len(), 3);
        assert!(matches!(tokens[0], FormatToken::Message));
        assert!(matches!(&tokens[1], FormatToken::Static(s) if s == " user="));
        assert!(matches!(&tokens[2], FormatToken::Extra(k) if k == "user_id"));
    }

    #[test]
    fn test_format_record_message_only_omits_time() {
        let config = FormatConfig::new(Some("{message}".to_string()), false);
        let record = LogRecord::new(LogLevel::Info, "only".into());
        let result = config.format_record(&record, false);
        assert_eq!(result, "only");
        assert!(!result.contains(&format!("{}", record.timestamp.format("%Y"))));
    }

    #[test]
    fn test_record_level_width_left_pad_noncolor() {
        let config = FormatConfig::new(Some("{level:<8}".to_string()), false);
        let record = LogRecord::new(LogLevel::Info, "x".into());
        assert_eq!(config.format_record(&record, false), "INFO    ");
    }

    #[test]
    fn test_record_level_width_long_level_not_truncated() {
        let info = LevelInfo::new(
            "VERYLONGCUSTOMLEVEL".to_string(),
            99,
            Some("red".to_string()),
            None,
        );
        let record = LogRecord::with_custom_level(info, "m".into(), empty_context(), None);
        let config = FormatConfig::new(Some("{level:<8}".to_string()), false);
        let out = config.format_record(&record, false);
        let expected = format!("{:<8}", "VERYLONGCUSTOMLEVEL");
        assert_eq!(out, expected);
        assert!(out.len() > 8);
    }

    #[test]
    fn test_record_thread_process_noncolor() {
        let record = LogRecord::with_all(
            LogLevel::Info,
            "m".into(),
            empty_context(),
            None,
            CallerInfo::default(),
            ThreadInfo {
                name: "worker".into(),
                id: 42,
            },
            ProcessInfo {
                name: "app".into(),
                id: 7,
            },
        );
        let config = FormatConfig::new(Some("{thread} | {process}".to_string()), false);
        assert_eq!(config.format_record(&record, false), "worker:42 | app:7");
    }

    #[test]
    fn test_record_line_noncolor() {
        let caller = CallerInfo::with_file("mod".into(), "f".into(), 12345, "a.py".into());
        let record =
            LogRecord::with_caller(LogLevel::Info, "m".into(), empty_context(), None, caller);
        let config = FormatConfig::new(Some("L={line}".to_string()), false);
        assert_eq!(config.format_record(&record, false), "L=12345");
    }

    #[test]
    fn test_split_format_markup() {
        use MarkupPiece::{Close, Open, Text};
        assert_eq!(
            split_format_markup("<green>{time}</green> <level>{level:<8}</level> <nope>x</nope>"),
            vec![
                Open(MarkupStyle::Ansi("\x1b[32m")),
                Text("{time}".into()),
                Close,
                Text(" ".into()),
                Open(MarkupStyle::Level),
                Text("{level:<8}".into()),
                Close,
                Text(" <nope>x</nope>".into()),
            ]
        );
        // Unmatched closing tag and stray '<' stay literal
        assert_eq!(
            split_format_markup("</red>a < b <red>c"),
            vec![
                Text("</red>a < b ".into()),
                Open(MarkupStyle::Ansi("\x1b[31m")),
                Text("c".into()),
            ]
        );
    }

    #[test]
    fn test_record_template_markup_stripped_without_color() {
        let config = FormatConfig::new(
            Some("<green>{level}</green> <level>{message}</level> <nope>x</nope>".to_string()),
            false,
        );
        let record = LogRecord::new(LogLevel::Info, "<red>m</red>".into());
        assert_eq!(
            config.format_record(&record, false),
            "INFO m <nope>x</nope>"
        );
    }

    #[test]
    fn test_record_template_markup_colorized() {
        let config = FormatConfig::new(
            Some("<green>{level}</green>|<level>{message}</level>|{level}".to_string()),
            false,
        );
        let record = LogRecord::new(LogLevel::Warning, "<red>r</red> t".into());
        assert_eq!(
            config.format_record(&record, true),
            // Markup color replaces the default level style; message resets keep <level>
            "\x1b[32mWARNING\x1b[0m|\x1b[1;33m\x1b[31mr\x1b[0m\x1b[1;33m t\x1b[0m|\x1b[1;33mWARNING\x1b[0m"
        );
    }

    #[test]
    fn test_time_spec_token() {
        let config = FormatConfig::new(Some("[{time:YYYY-MM-DD}] {message}".into()), false);
        let record = LogRecord::new(LogLevel::Info, "m".into());
        let expected = format!("[{}] m", record.timestamp.format("%Y-%m-%d"));
        assert_eq!(config.format_record(&record, false), expected);
        // The default `{time}` string is not computed for spec-only formats
        assert!(!config.requirements().needs_time);
        assert!(matches!(
            parse_template("{time:HH}").unwrap()[0],
            FormatToken::TimeFormatted(_)
        ));
        // Colorized like {time}
        let colored = config.format_record(&record, true);
        assert!(colored.starts_with("[\x1b[2m"));
    }

    #[test]
    fn test_invalid_time_spec_rejected() {
        assert!(FormatConfig::try_new(Some("{time:SSSSSSS}".into()), false).is_err());
        assert!(FormatConfig::try_new(Some("{time:%Q}".into()), false).is_err());
        // Unused template of a JSON sink is not validated
        assert!(FormatConfig::try_new(Some("{time:SSSSSSS}".into()), true).is_ok());
    }

    #[test]
    fn test_plain_time_unchanged() {
        let config = FormatConfig::new(Some("{time}".into()), false);
        let record = LogRecord::new(LogLevel::Info, "m".into());
        assert_eq!(
            config.format_record(&record, false),
            record.timestamp.format(DEFAULT_TIME_FORMAT).to_string()
        );
    }

    #[test]
    fn test_default_time_matches_chrono() {
        use chrono::{NaiveDate, TimeZone};

        let check = |dt: DateTime<Local>| {
            assert_eq!(
                format_default_time(&dt),
                dt.format(DEFAULT_TIME_FORMAT).to_string(),
                "{dt:?}"
            );
        };

        // Sweep instants with varying sub-second parts across several years
        let base = Local::now();
        for i in 0..20_000i64 {
            let dt = base
                + chrono::Duration::seconds(i * 7_919)
                + chrono::Duration::nanoseconds(i * 1_234_567);
            check(dt);
        }
        // Milliseconds with leading zeros and exact boundaries
        for nanos in [0, 999, 1_000_000, 9_999_999, 10_000_000, 999_999_999] {
            let dt = Local.with_ymd_and_hms(2024, 2, 29, 0, 0, 0).unwrap()
                + chrono::Duration::nanoseconds(nanos);
            check(dt);
        }
        // Leap second representation renders as second 60
        let leap = NaiveDate::from_ymd_opt(2016, 12, 31)
            .unwrap()
            .and_hms_nano_opt(23, 59, 59, 1_500_000_000)
            .unwrap()
            .and_local_timezone(Local)
            .unwrap();
        check(leap);
        assert!(format_default_time(&leap).ends_with(":60.500"));
        // Years that chrono pads or signs
        for year in [1, 999, 1000, 9999, -1, 10_000] {
            check(Local.with_ymd_and_hms(year, 6, 15, 12, 30, 45).unwrap());
        }
    }

    #[test]
    fn test_level_fields() {
        let config = FormatConfig::new(
            Some("{level.name}|{level.no}|{level.icon}|{message}".into()),
            false,
        );
        let record = LogRecord::new(LogLevel::Warning, "m".into());
        assert_eq!(
            config.format_record(&record, false),
            "WARNING|30|\u{26A0}\u{FE0F}|m"
        );
        assert!(config.requirements().needs_level);

        let info = LevelInfo::new("NOTICE".into(), 35, None, Some("!".into()));
        let record = LogRecord::with_custom_level(info, "m".into(), empty_context(), None);
        assert_eq!(config.format_record(&record, false), "NOTICE|35|!|m");

        let info = LevelInfo::new("PLAIN".into(), 36, None, None);
        let record = LogRecord::with_custom_level(info, "m".into(), empty_context(), None);
        assert_eq!(config.format_record(&record, false), "PLAIN|36||m");

        let config = FormatConfig::new(Some("{level.name:<8}|".into()), false);
        let record = LogRecord::new(LogLevel::Info, "m".into());
        assert_eq!(config.format_record(&record, false), "INFO    |");
    }

    #[test]
    fn test_thread_process_fields() {
        let record = LogRecord::with_all(
            LogLevel::Info,
            "m".into(),
            empty_context(),
            None,
            CallerInfo::default(),
            ThreadInfo {
                name: "worker".into(),
                id: 42,
            },
            ProcessInfo {
                name: "app".into(),
                id: 7,
            },
        );
        let config = FormatConfig::new(
            Some("{thread.name}/{thread.id} {process.name}/{process.id}".into()),
            false,
        );
        assert_eq!(config.format_record(&record, false), "worker/42 app/7");
        let reqs = config.requirements();
        assert!(reqs.needs_thread && reqs.needs_process && !reqs.needs_caller);
    }

    #[test]
    fn test_file_fields() {
        let caller = CallerInfo::with_file("mod".into(), "f".into(), 1, "/src/pkg/app.py".into());
        let record =
            LogRecord::with_caller(LogLevel::Info, "m".into(), empty_context(), None, caller);
        let config = FormatConfig::new(Some("{file}|{file.name}|{file.path}".into()), false);
        assert_eq!(
            config.format_record(&record, false),
            "app.py|app.py|/src/pkg/app.py"
        );
        assert!(config.requirements().needs_caller);
    }

    #[test]
    fn test_exception_token_replaces_auto_append() {
        let exception = Some("Traceback: boom\n".to_string());
        let record =
            LogRecord::with_exception(LogLevel::Error, "Failed".into(), empty_context(), exception);
        let config = FormatConfig::new(Some("{message}\n{exception}--".into()), false);
        assert_eq!(
            config.format_record(&record, false),
            "Failed\nTraceback: boom\n--"
        );

        // Without exception, {exception} renders empty
        let record = LogRecord::new(LogLevel::Error, "ok".into());
        assert_eq!(config.format_record(&record, false), "ok\n--");
    }

    #[test]
    fn test_dotted_fields_with_unknown_attribute_stay_literal() {
        let config = FormatConfig::new(Some("{level.color} {thread.x}".into()), false);
        let record = LogRecord::new(LogLevel::Info, "m".into());
        assert_eq!(
            config.format_record(&record, false),
            "{level.color} {thread.x}"
        );
    }

    fn extra_record(pairs: &[(&str, ExtraValue)]) -> LogRecord {
        let extra: ExtraMap = pairs
            .iter()
            .map(|(k, v)| (k.to_string(), v.clone()))
            .collect();
        LogRecord::with_extra(LogLevel::Info, "m".into(), Arc::new(extra))
    }

    #[test]
    fn test_extra_all_token_parsed() {
        let tokens = parse_template("{message} {extra}").unwrap();
        assert!(matches!(tokens[2], FormatToken::ExtraAll));
        // With a spec it is not a field (literal, like other unknown placeholders)
        let tokens = parse_template("{extra:>5}").unwrap();
        assert!(matches!(&tokens[0], FormatToken::Static(s) if s == "{extra:>5}"));
    }

    #[test]
    fn test_extra_all_empty() {
        let config = FormatConfig::new(Some("{message} {extra}".into()), false);
        let record = LogRecord::new(LogLevel::Info, "m".into());
        assert_eq!(config.format_record(&record, false), "m {}");
    }

    #[test]
    fn test_extra_all_sorted_and_typed() {
        let config = FormatConfig::new(Some("{extra}".into()), false);
        let record = extra_record(&[
            ("user", ExtraValue::from("alice")),
            ("count", ExtraValue::non_str("3")),
            ("flag", ExtraValue::non_str("True")),
            ("none", ExtraValue::non_str("None")),
        ]);
        assert_eq!(
            config.format_record(&record, false),
            "{'count': 3, 'flag': True, 'none': None, 'user': 'alice'}"
        );
    }

    #[test]
    fn test_extra_all_string_escapes() {
        let config = FormatConfig::new(Some("{extra}".into()), false);
        let record = extra_record(&[
            ("a", ExtraValue::from("it's")),
            ("b", ExtraValue::from("'\"")),
            ("c", ExtraValue::from("x\ny\t\\")),
            ("d", ExtraValue::from("\u{0}\u{7f}\u{a0}\u{2028}é")),
        ]);
        assert_eq!(
            config.format_record(&record, false),
            r#"{'a': "it's", 'b': '\'"', 'c': 'x\ny\t\\', 'd': '\x00\x7f\xa0\u2028é'}"#
        );
    }

    #[test]
    fn test_extra_all_not_colorized() {
        let config = FormatConfig::new(Some("{extra}".into()), false);
        let record = extra_record(&[("k", ExtraValue::from("v"))]);
        assert_eq!(config.format_record(&record, true), "{'k': 'v'}");
    }

    #[test]
    fn test_message_markup_disabled() {
        let config = FormatConfig::new(Some("{message}".into()), false);
        let mut record = LogRecord::new(LogLevel::Info, "<red>x</red>".into());
        assert_eq!(config.format_record(&record, false), "x");
        record.message_markup = false;
        assert_eq!(config.format_record(&record, false), "<red>x</red>");
        assert_eq!(config.format_record(&record, true), "<red>x</red>");
    }
}
