use std::collections::HashMap;
use std::sync::LazyLock;

use colored::Color;
use parking_lot::RwLock;
use pyo3::prelude::*;

/// Log level enum with numeric ordering for filtering
#[pyclass(eq, eq_int)]
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

    /// Get associated color for terminal output
    pub fn color(&self) -> Color {
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

/// Global registry for custom log levels (by name)
static LEVEL_REGISTRY: LazyLock<RwLock<HashMap<String, LevelInfo>>> =
    LazyLock::new(|| RwLock::new(HashMap::new()));

/// Secondary registry for O(1) numeric lookup (level_no -> level_name)
static LEVEL_NO_REGISTRY: LazyLock<RwLock<HashMap<u32, String>>> =
    LazyLock::new(|| RwLock::new(HashMap::new()));

/// Register a custom level
pub fn register_level(info: LevelInfo) {
    let name = info.name.to_ascii_uppercase();
    let no = info.no;
    LEVEL_REGISTRY.write().insert(name.clone(), info);
    LEVEL_NO_REGISTRY.write().insert(no, name);
}

/// Look up level by name (checks custom first, then built-in)
pub fn get_level_info(name: &str) -> Option<LevelInfo> {
    let upper = name.to_ascii_uppercase();

    if let Some(info) = LEVEL_REGISTRY.read().get(&upper) {
        return Some(info.clone());
    }

    match upper.as_str() {
        "TRACE" => Some(LevelInfo::new("TRACE".into(), 5, Some("cyan".into()), None)),
        "DEBUG" => Some(LevelInfo::new(
            "DEBUG".into(),
            10,
            Some("blue".into()),
            None,
        )),
        "INFO" => Some(LevelInfo::new(
            "INFO".into(),
            20,
            Some("green".into()),
            None,
        )),
        "SUCCESS" => Some(LevelInfo::new(
            "SUCCESS".into(),
            25,
            Some("bright_green".into()),
            None,
        )),
        "WARNING" => Some(LevelInfo::new(
            "WARNING".into(),
            30,
            Some("yellow".into()),
            None,
        )),
        "ERROR" => Some(LevelInfo::new("ERROR".into(), 40, Some("red".into()), None)),
        "FAIL" => Some(LevelInfo::new(
            "FAIL".into(),
            45,
            Some("magenta".into()),
            None,
        )),
        "CRITICAL" => Some(LevelInfo::new(
            "CRITICAL".into(),
            50,
            Some("bright_red".into()),
            None,
        )),
        _ => None,
    }
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
