use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{LazyLock, RwLockReadGuard, RwLockWriteGuard};

use colored::Color;
use pyo3::prelude::*;

struct RwLock<T>(std::sync::RwLock<T>);

impl<T> RwLock<T> {
    fn new(value: T) -> Self {
        Self(std::sync::RwLock::new(value))
    }

    fn read(&self) -> RwLockReadGuard<'_, T> {
        self.0.read().unwrap_or_else(|e| e.into_inner())
    }

    fn write(&self) -> RwLockWriteGuard<'_, T> {
        self.0.write().unwrap_or_else(|e| e.into_inner())
    }
}

/// Log level enum with numeric ordering for filtering
#[pyclass(eq, eq_int, from_py_object)]
#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Debug, Hash, Default)]
pub enum LogLevel {
    Trace = 5,
    #[default]
    Debug = 10,
    Info = 20,
    Success = 25,
    Warning = 30,
    Error = 40,
    Fail = 45,
    Critical = 50,
}

#[pymethods]
impl LogLevel {
    /// Get numeric value for comparison
    #[getter]
    fn value(&self) -> u8 {
        *self as u8
    }

    /// Get display name
    #[getter]
    fn name(&self) -> &'static str {
        self.as_str()
    }
}

impl LogLevel {
    /// Get string representation
    pub fn as_str(&self) -> &'static str {
        match self {
            LogLevel::Trace => "TRACE",
            LogLevel::Debug => "DEBUG",
            LogLevel::Info => "INFO",
            LogLevel::Success => "SUCCESS",
            LogLevel::Warning => "WARNING",
            LogLevel::Error => "ERROR",
            LogLevel::Fail => "FAIL",
            LogLevel::Critical => "CRITICAL",
        }
    }

    /// Slot of this level in [`BUILTIN_COLOR_OVERRIDES`] (one byte per level).
    #[inline]
    fn slot(&self) -> u32 {
        match self {
            LogLevel::Trace => 0,
            LogLevel::Debug => 1,
            LogLevel::Info => 2,
            LogLevel::Success => 3,
            LogLevel::Warning => 4,
            LogLevel::Error => 5,
            LogLevel::Fail => 6,
            LogLevel::Critical => 7,
        }
    }

    /// Look up a built-in level by (case-insensitive) name.
    pub fn from_name(name: &str) -> Option<LogLevel> {
        match name.to_ascii_uppercase().as_str() {
            "TRACE" => Some(LogLevel::Trace),
            "DEBUG" => Some(LogLevel::Debug),
            "INFO" => Some(LogLevel::Info),
            "SUCCESS" => Some(LogLevel::Success),
            "WARNING" => Some(LogLevel::Warning),
            "ERROR" => Some(LogLevel::Error),
            "FAIL" => Some(LogLevel::Fail),
            "CRITICAL" => Some(LogLevel::Critical),
            _ => None,
        }
    }

    /// Default icon (loguru's defaults; FAIL is logust-only)
    pub fn icon(&self) -> &'static str {
        match self {
            LogLevel::Trace => "\u{270F}\u{FE0F}",
            LogLevel::Debug => "\u{1F41E}",
            LogLevel::Info => "\u{2139}\u{FE0F}",
            LogLevel::Success => "\u{2705}",
            LogLevel::Warning => "\u{26A0}\u{FE0F}",
            LogLevel::Error => "\u{274C}",
            LogLevel::Fail => "\u{2716}\u{FE0F}",
            LogLevel::Critical => "\u{2620}\u{FE0F}",
        }
    }

    /// Get associated color for terminal output
    #[inline]
    pub fn color(&self) -> Color {
        let code = (BUILTIN_COLOR_OVERRIDES.load(Ordering::Relaxed) >> (self.slot() * 8)) as u8;
        if code != 0 {
            return color_from_code(code);
        }
        self.default_color()
    }

    /// Default color of the built-in level, ignoring `logger.level()` updates
    fn default_color(&self) -> Color {
        match self {
            LogLevel::Trace => Color::Cyan,
            LogLevel::Debug => Color::Blue,
            LogLevel::Info => Color::Green,
            LogLevel::Success => Color::BrightGreen,
            LogLevel::Warning => Color::Yellow,
            LogLevel::Error => Color::Red,
            LogLevel::Fail => Color::Magenta,
            LogLevel::Critical => Color::BrightRed,
        }
    }
}

/// Information about a log level (built-in or custom)
#[derive(Clone, Debug)]
pub struct LevelInfo {
    pub name: String,
    pub no: u32,
    pub color: String,
    pub icon: Option<String>,
}

impl LevelInfo {
    /// Create a new level info
    pub fn new(name: String, no: u32, color: Option<String>, icon: Option<String>) -> Self {
        LevelInfo {
            name,
            no,
            color: color.unwrap_or_default(),
            icon,
        }
    }

    /// Get color as colored::Color
    pub fn get_color(&self) -> Color {
        get_color_from_name(&self.color)
    }
}

/// Colors set on built-in levels via `logger.level()`: one byte per level slot,
/// `0` = default color, otherwise an index into [`NAMED_COLORS`] plus one.
/// Read with one relaxed load in [`LogLevel::color`], written only at setup time.
static BUILTIN_COLOR_OVERRIDES: AtomicU64 = AtomicU64::new(0);

/// Colors that [`get_color_from_name`] can produce, indexed by override code - 1.
const NAMED_COLORS: [Color; 16] = [
    Color::Black,
    Color::Red,
    Color::Green,
    Color::Yellow,
    Color::Blue,
    Color::Magenta,
    Color::Cyan,
    Color::White,
    Color::BrightBlack,
    Color::BrightRed,
    Color::BrightGreen,
    Color::BrightYellow,
    Color::BrightBlue,
    Color::BrightMagenta,
    Color::BrightCyan,
    Color::BrightWhite,
];

fn color_to_code(color: Color) -> u8 {
    NAMED_COLORS
        .iter()
        .position(|c| *c == color)
        .map_or(8, |i| i as u8 + 1)
}

fn color_from_code(code: u8) -> Color {
    NAMED_COLORS
        .get(usize::from(code) - 1)
        .copied()
        .unwrap_or(Color::White)
}

/// Make console output of the built-in `level` use `color`
fn set_builtin_color(level: LogLevel, color: Color) {
    let shift = level.slot() * 8;
    let code = u64::from(color_to_code(color)) << shift;
    let mask = !(0xFFu64 << shift);
    // CAS loop rather than `fetch_update`, which newer toolchains deprecate
    let mut current = BUILTIN_COLOR_OVERRIDES.load(Ordering::Relaxed);
    while let Err(actual) = BUILTIN_COLOR_OVERRIDES.compare_exchange_weak(
        current,
        (current & mask) | code,
        Ordering::Relaxed,
        Ordering::Relaxed,
    ) {
        current = actual;
    }
}

/// Global registry for custom log levels (by name)
static LEVEL_REGISTRY: LazyLock<RwLock<HashMap<String, LevelInfo>>> =
    LazyLock::new(|| RwLock::new(HashMap::new()));

/// Secondary registry for O(1) numeric lookup (level_no -> level_name)
static LEVEL_NO_REGISTRY: LazyLock<RwLock<HashMap<u32, String>>> =
    LazyLock::new(|| RwLock::new(HashMap::new()));

/// Bumped whenever a level is (re)registered, so caches of level details can
/// tell they are stale
pub static LEVEL_GENERATION: AtomicU64 = AtomicU64::new(0);

/// Register a custom level
pub fn register_level(info: LevelInfo) {
    let name = info.name.to_ascii_uppercase();
    if let Some(builtin) = LogLevel::from_name(&name) {
        set_builtin_color(builtin, info.get_color());
    }
    let no = info.no;
    LEVEL_REGISTRY.write().insert(name.clone(), info);
    LEVEL_NO_REGISTRY.write().insert(no, name);
    LEVEL_GENERATION.fetch_add(1, Ordering::Release);
}

/// Look up level by name (checks custom first, then built-in)
pub fn get_level_info(name: &str) -> Option<LevelInfo> {
    let upper = name.to_ascii_uppercase();

    if let Some(info) = LEVEL_REGISTRY.read().get(&upper) {
        return Some(info.clone());
    }

    builtin_level(&upper).map(builtin_level_info)
}

/// Built-in level for an upper-case level name
fn builtin_level(upper: &str) -> Option<LogLevel> {
    Some(match upper {
        "TRACE" => LogLevel::Trace,
        "DEBUG" => LogLevel::Debug,
        "INFO" => LogLevel::Info,
        "SUCCESS" => LogLevel::Success,
        "WARNING" => LogLevel::Warning,
        "ERROR" => LogLevel::Error,
        "FAIL" => LogLevel::Fail,
        "CRITICAL" => LogLevel::Critical,
        _ => return None,
    })
}

/// Level info of a built-in level
fn builtin_level_info(level: LogLevel) -> LevelInfo {
    let color = match level {
        LogLevel::Trace => "cyan",
        LogLevel::Debug => "blue",
        LogLevel::Info => "green",
        LogLevel::Success => "bright_green",
        LogLevel::Warning => "yellow",
        LogLevel::Error => "red",
        LogLevel::Fail => "magenta",
        LogLevel::Critical => "bright_red",
    };
    LevelInfo::new(
        level.as_str().into(),
        level as u32,
        Some(color.into()),
        Some(level.icon().into()),
    )
}

/// Color of the level `name` (custom first, then built-in), without cloning its info
pub fn get_level_color(name: &str) -> Option<Color> {
    let upper = name.to_ascii_uppercase();
    if let Some(info) = LEVEL_REGISTRY.read().get(&upper) {
        return Some(info.get_color());
    }
    builtin_level(&upper).map(|level| level.color())
}

/// Look up level by numeric value (O(1) using secondary registry)
pub fn get_level_by_no(no: u32) -> Option<LevelInfo> {
    if let Some(name) = LEVEL_NO_REGISTRY.read().get(&no) {
        return LEVEL_REGISTRY.read().get(name).cloned();
    }

    match no {
        5 => get_level_info("TRACE"),
        10 => get_level_info("DEBUG"),
        20 => get_level_info("INFO"),
        25 => get_level_info("SUCCESS"),
        30 => get_level_info("WARNING"),
        40 => get_level_info("ERROR"),
        45 => get_level_info("FAIL"),
        50 => get_level_info("CRITICAL"),
        _ => None,
    }
}

/// Convert color name to colored::Color
pub fn get_color_from_name(color_name: &str) -> Color {
    match color_name.to_ascii_lowercase().as_str() {
        "cyan" => Color::Cyan,
        "blue" => Color::Blue,
        "green" => Color::Green,
        "bright_green" => Color::BrightGreen,
        "yellow" => Color::Yellow,
        "red" => Color::Red,
        "magenta" => Color::Magenta,
        "bright_red" => Color::BrightRed,
        "white" => Color::White,
        "black" => Color::Black,
        "bright_blue" => Color::BrightBlue,
        "bright_cyan" => Color::BrightCyan,
        "bright_yellow" => Color::BrightYellow,
        "bright_magenta" => Color::BrightMagenta,
        "bright_white" => Color::BrightWhite,
        _ => Color::White,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_get_level_info_builtin() {
        let info = get_level_info("info").unwrap();
        assert_eq!(info.name, "INFO");
        assert_eq!(info.no, 20);

        let info = get_level_info("INFO").unwrap();
        assert_eq!(info.name, "INFO");

        let info = get_level_info("Info").unwrap();
        assert_eq!(info.name, "INFO");
        assert_eq!(info.icon.as_deref(), Some(LogLevel::Info.icon()));
        assert_eq!(info.get_color(), LogLevel::Info.color());
    }

    #[test]
    fn test_get_level_info_all_levels() {
        assert!(get_level_info("trace").is_some());
        assert!(get_level_info("debug").is_some());
        assert!(get_level_info("info").is_some());
        assert!(get_level_info("success").is_some());
        assert!(get_level_info("warning").is_some());
        assert!(get_level_info("error").is_some());
        assert!(get_level_info("fail").is_some());
        assert!(get_level_info("critical").is_some());
    }

    #[test]
    fn test_get_level_info_unknown() {
        assert!(get_level_info("unknown").is_none());
        assert!(get_level_info("").is_none());
    }

    #[test]
    fn test_get_color_from_name() {
        assert_eq!(get_color_from_name("red"), Color::Red);
        assert_eq!(get_color_from_name("RED"), Color::Red);
        assert_eq!(get_color_from_name("Red"), Color::Red);

        assert_eq!(get_color_from_name("bright_green"), Color::BrightGreen);
        assert_eq!(get_color_from_name("BRIGHT_GREEN"), Color::BrightGreen);
    }

    #[test]
    fn test_get_color_from_name_unknown() {
        assert_eq!(get_color_from_name("unknown"), Color::White);
        assert_eq!(get_color_from_name(""), Color::White);
    }

    #[test]
    fn test_get_level_by_no_builtin() {
        let info = get_level_by_no(20).unwrap();
        assert_eq!(info.name, "INFO");

        let info = get_level_by_no(40).unwrap();
        assert_eq!(info.name, "ERROR");
    }

    #[test]
    fn test_color_code_roundtrip() {
        for color in NAMED_COLORS {
            assert_eq!(color_from_code(color_to_code(color)), color);
        }
    }

    #[test]
    fn test_builtin_color_override() {
        // Use FAIL only: tests share the global registry.
        assert_eq!(LogLevel::Fail.color(), Color::Magenta);
        register_level(LevelInfo::new(
            "FAIL".into(),
            45,
            Some("bright_blue".into()),
            None,
        ));
        assert_eq!(LogLevel::Fail.color(), Color::BrightBlue);
        assert_eq!(LogLevel::Error.color(), Color::Red);
        assert_eq!(get_level_info("fail").unwrap().color, "bright_blue");
    }

    #[test]
    fn test_get_level_by_no_unknown() {
        assert!(get_level_by_no(999).is_none());
    }

    #[test]
    fn test_register_and_lookup_custom_level() {
        let custom = LevelInfo::new("NOTICE".into(), 35, Some("cyan".into()), Some("📢".into()));
        register_level(custom);

        let info = get_level_info("NOTICE").unwrap();
        assert_eq!(info.name, "NOTICE");
        assert_eq!(info.no, 35);

        let info = get_level_by_no(35).unwrap();
        assert_eq!(info.name, "NOTICE");
        assert_eq!(info.no, 35);
    }
}
