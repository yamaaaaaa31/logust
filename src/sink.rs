use std::fs::{self, File, OpenOptions};
use std::io::{self, BufWriter, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicI64, AtomicU64, Ordering};
use std::thread::{self, JoinHandle};
use std::time::Duration;

use chrono::{DateTime, Local, Timelike};
use crossbeam_channel::{RecvTimeoutError, Sender, bounded};
use flate2::Compression;
use flate2::write::GzEncoder;
use parking_lot::Mutex;
use pyo3::prelude::*;

/// Capacity of the async message queue
const ASYNC_QUEUE_CAPACITY: usize = 10_000;

/// Flush interval for async writer in milliseconds
const ASYNC_FLUSH_INTERVAL_MS: u64 = 100;

/// Size unit multipliers for parsing size strings
const KB: u64 = 1024;
const MB: u64 = KB * 1024;
const GB: u64 = MB * 1024;
const TB: u64 = GB * 1024;

/// Rotation strategy
#[pyclass(eq, eq_int)]
#[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
pub enum Rotation {
    /// No rotation
    #[default]
    Never = 0,
    /// Rotate daily
    Daily = 1,
    /// Rotate hourly
    Hourly = 2,
}

/// Retention policy
#[pyclass(eq, eq_int)]
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum RetentionPolicy {
    /// No retention limit
    Forever = 0,
}

/// File sink configuration
#[derive(Clone)]
pub struct FileSinkConfig {
    pub path: PathBuf,
    pub rotation: Rotation,
    pub max_size: Option<u64>,
    pub retention_days: Option<u32>,
    pub retention_count: Option<u32>,
    pub compression: bool,
    /// If true, writes are queued and processed asynchronously (thread-safe)
    /// If false, writes are synchronous (faster for single-threaded use)
    pub enqueue: bool,
}

impl Default for FileSinkConfig {
    fn default() -> Self {
        FileSinkConfig {
            path: PathBuf::from("app.log"),
            rotation: Rotation::Never,
            max_size: None,
            retention_days: None,
            retention_count: None,
            compression: false,
            enqueue: false,
        }
    }
}

/// Async message for file writer thread
enum WriterMessage {
    Write(String),
    Flush,
    Shutdown,
}

/// Writer backend for FileSink
enum WriterBackend {
    /// Async writer with channel and background thread
    Async {
        sender: Sender<WriterMessage>,
        handle: Option<JoinHandle<()>>,
    },
    /// Sync writer with direct file access
    Sync { writer: Mutex<BufWriter<File>> },
}

/// File sink with optional async writing support
pub struct FileSink {
    config: FileSinkConfig,
    backend: WriterBackend,
    /// Current file size in bytes (lock-free for hot path)
    current_size: AtomicU64,
    current_file_time: Mutex<DateTime<Local>>,
    /// Cached next rotation boundary as epoch milliseconds for O(1) time-based rotation check.
    /// 0 means no rotation boundary (equivalent to None).
    next_rotation_boundary: AtomicI64,
}

impl FileSink {
    /// Create a new file sink
    pub fn new(config: FileSinkConfig) -> io::Result<Self> {
        let path = config.path.clone();

        if let Some(parent) = path.parent()
            && !parent.as_os_str().is_empty()
        {
            fs::create_dir_all(parent)?;
        }

        let current_size = if path.exists() {
            fs::metadata(&path)?.len()
        } else {
            0
        };

        let backend = if config.enqueue {
            // Open the file before spawning the worker so open errors surface here.
            let file = OpenOptions::new().create(true).append(true).open(&path)?;

            let (sender, receiver) = bounded::<WriterMessage>(ASYNC_QUEUE_CAPACITY);

            let writer_handle = thread::spawn(move || {
                let mut writer = BufWriter::new(file);
                let flush_interval = Duration::from_millis(ASYNC_FLUSH_INTERVAL_MS);

                loop {
                    match receiver.recv_timeout(flush_interval) {
                        Ok(WriterMessage::Write(msg)) => {
                            if let Err(e) = writeln!(writer, "{}", msg) {
                                eprintln!("Failed to write to log: {}", e);
                            }
                        }
                        Ok(WriterMessage::Flush) => {
                            let _ = writer.flush();
                        }
                        Ok(WriterMessage::Shutdown) => {
                            let _ = writer.flush();
                            break;
                        }
                        Err(RecvTimeoutError::Timeout) => {
                            let _ = writer.flush();
                        }
                        Err(RecvTimeoutError::Disconnected) => {
                            let _ = writer.flush();
                            break;
                        }
                    }
                }
            });

            WriterBackend::Async {
                sender,
                handle: Some(writer_handle),
            }
        } else {
            let file = OpenOptions::new().create(true).append(true).open(&path)?;

            WriterBackend::Sync {
                writer: Mutex::new(BufWriter::new(file)),
            }
        };

        let now = Local::now();
        let next_boundary = Self::calculate_next_rotation_boundary(&config.rotation, &now);

        Ok(FileSink {
            config,
            backend,
            current_size: AtomicU64::new(current_size),
            current_file_time: Mutex::new(now),
            next_rotation_boundary: AtomicI64::new(
                next_boundary.map(|b| b.timestamp_millis()).unwrap_or(0),
            ),
        })
    }

    /// Calculate the next rotation boundary based on rotation strategy
    fn calculate_next_rotation_boundary(
        rotation: &Rotation,
        from: &DateTime<Local>,
    ) -> Option<DateTime<Local>> {
        use chrono::{Duration, NaiveTime};

        match rotation {
            Rotation::Never => None,
            Rotation::Daily => {
                let tomorrow = from.date_naive() + Duration::days(1);
                let midnight = NaiveTime::from_hms_opt(0, 0, 0).unwrap();
                tomorrow
                    .and_time(midnight)
                    .and_local_timezone(Local)
                    .single()
            }
            Rotation::Hourly => {
                let next_hour = from.date_naive().and_hms_opt(from.hour() + 1, 0, 0);
                if let Some(nh) = next_hour {
                    nh.and_local_timezone(Local).single()
                } else {
                    let tomorrow = from.date_naive() + Duration::days(1);
                    let midnight = NaiveTime::from_hms_opt(0, 0, 0).unwrap();
                    tomorrow
                        .and_time(midnight)
                        .and_local_timezone(Local)
                        .single()
                }
            }
        }
    }

    /// Write a message to the file (borrows message)
    #[inline]
    pub fn write(&self, message: &str) -> io::Result<()> {
        self.maybe_rotate()?;

        let msg_len = message.len() as u64 + 1;

        match &self.backend {
            WriterBackend::Async { sender, .. } => {
                if let Err(e) = sender.send(WriterMessage::Write(message.to_string())) {
                    return Err(io::Error::other(e.to_string()));
                }
            }
            WriterBackend::Sync { writer } => {
                let mut w = writer.lock();
                writeln!(w, "{}", message)?;
            }
        }

        self.current_size.fetch_add(msg_len, Ordering::Relaxed);

        Ok(())
    }

    /// Write a message to the file (takes ownership, avoids clone in async mode)
    #[inline]
    pub fn write_owned(&self, message: String) -> io::Result<()> {
        self.maybe_rotate()?;

        let msg_len = message.len() as u64 + 1;

        match &self.backend {
            WriterBackend::Async { sender, .. } => {
                if let Err(e) = sender.send(WriterMessage::Write(message)) {
                    return Err(io::Error::other(e.to_string()));
                }
            }
            WriterBackend::Sync { writer } => {
                let mut w = writer.lock();
                writeln!(w, "{}", message)?;
            }
        }

        self.current_size.fetch_add(msg_len, Ordering::Relaxed);

        Ok(())
    }

    /// Flush pending writes
    pub fn flush(&self) -> io::Result<()> {
        match &self.backend {
            WriterBackend::Async { sender, .. } => sender
                .send(WriterMessage::Flush)
                .map_err(|e| io::Error::other(e.to_string())),
            WriterBackend::Sync { writer } => writer.lock().flush(),
        }
    }

    /// Check and perform rotation if needed
    #[inline]
    fn maybe_rotate(&self) -> io::Result<()> {
        if self.config.rotation == Rotation::Never && self.config.max_size.is_none() {
            return Ok(());
        }

        if self.check_rotation_needed() {
            self.rotate()?;
        }

        Ok(())
    }

    /// Check if rotation is needed (lock-free hot path)
    #[inline]
    fn check_rotation_needed(&self) -> bool {
        // Size-based rotation check (AtomicU64)
        if let Some(max_size) = self.config.max_size
            && self.current_size.load(Ordering::Relaxed) >= max_size
        {
            return true;
        }

        // Time-based rotation check (AtomicI64 as epoch millis, 0 = None)
        let boundary_millis = self.next_rotation_boundary.load(Ordering::Relaxed);
        if boundary_millis > 0 {
            Local::now().timestamp_millis() >= boundary_millis
        } else {
            false
        }
    }

    /// Perform rotation
    fn rotate(&self) -> io::Result<()> {
        let now = Local::now();

        let rotated_path = self.generate_rotated_path(&now);

        self.flush()?;

        if self.config.path.exists() {
            fs::rename(&self.config.path, &rotated_path)?;

            if self.config.compression {
                self.compress_file(&rotated_path)?;
            }
        }

        self.apply_retention()?;

        self.current_size.store(0, Ordering::Relaxed);
        *self.current_file_time.lock() = now;
        let next_boundary = Self::calculate_next_rotation_boundary(&self.config.rotation, &now);
        self.next_rotation_boundary.store(
            next_boundary.map(|b| b.timestamp_millis()).unwrap_or(0),
            Ordering::Relaxed,
        );

        Ok(())
    }

    /// Generate path for rotated file
    fn generate_rotated_path(&self, time: &DateTime<Local>) -> PathBuf {
        let stem = self
            .config
            .path
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("log");

        let ext = self
            .config
            .path
            .extension()
            .and_then(|s| s.to_str())
            .unwrap_or("log");

        let timestamp = time.format("%Y-%m-%d_%H-%M-%S");

        let filename = format!("{}.{}.{}", stem, timestamp, ext);

        self.config
            .path
            .parent()
            .map(|p| p.join(&filename))
            .unwrap_or_else(|| PathBuf::from(&filename))
    }

    /// Compress a file using gzip (streaming to avoid loading entire file into memory)
    fn compress_file(&self, path: &Path) -> io::Result<()> {
        let gz_path = path.with_extension(format!(
            "{}.gz",
            path.extension().and_then(|e| e.to_str()).unwrap_or("")
        ));

        let input_file = File::open(path)?;
        let mut reader = io::BufReader::new(input_file);

        let output_file = File::create(&gz_path)?;
        let mut encoder = GzEncoder::new(output_file, Compression::default());

        io::copy(&mut reader, &mut encoder)?;
        encoder.finish()?;

        fs::remove_file(path)?;

        Ok(())
    }

    /// Apply retention policy (O(n log n) instead of O(n²))
    fn apply_retention(&self) -> io::Result<()> {
        use std::time::SystemTime;

        let parent = self.config.path.parent().unwrap_or(Path::new("."));
        let stem = self
            .config
            .path
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("log");

        let current_filename = self
            .config
            .path
            .file_name()
            .and_then(|f| f.to_str())
            .unwrap_or("");

        let mut rotated_files: Vec<(PathBuf, SystemTime)> = fs::read_dir(parent)?
            .filter_map(|e| e.ok())
            .filter_map(|e| {
                let path = e.path();
                let filename = path.file_name()?.to_str()?;
                if filename.starts_with(stem) && filename != current_filename {
                    let modified = fs::metadata(&path).ok()?.modified().ok()?;
                    Some((path, modified))
                } else {
                    None
                }
            })
            .collect();

        rotated_files.sort_by_key(|(_, time)| *time);

        if let Some(max_count) = self.config.retention_count {
            let excess = rotated_files.len().saturating_sub(max_count as usize);
            for (path, _) in rotated_files.drain(..excess) {
                let _ = fs::remove_file(&path);
            }
        }

        if let Some(days) = self.config.retention_days {
            let cutoff = Local::now() - chrono::Duration::days(days as i64);
            let cutoff_time: SystemTime = cutoff.into();

            for (path, modified) in &rotated_files {
                if *modified < cutoff_time {
                    let _ = fs::remove_file(path);
                }
            }
        }

        Ok(())
    }
}

impl Drop for FileSink {
    fn drop(&mut self) {
        match &mut self.backend {
            WriterBackend::Async { sender, handle } => {
                let _ = sender.send(WriterMessage::Shutdown);
                if let Some(h) = handle.take() {
                    let _ = h.join();
                }
            }
            WriterBackend::Sync { writer } => {
                let _ = writer.lock().flush();
            }
        }
    }
}

/// Parse size string like "500 MB" to bytes
pub fn parse_size(size_str: &str) -> Option<u64> {
    let size_str = size_str.trim().to_uppercase();

    let (num_part, unit_part): (String, String) = size_str
        .chars()
        .partition(|c| c.is_ascii_digit() || *c == '.');

    let num: f64 = num_part.trim().parse().ok()?;
    let unit = unit_part.trim();

    let multiplier = match unit {
        "" | "B" => 1u64,
        "K" | "KB" => KB,
        "M" | "MB" => MB,
        "G" | "GB" => GB,
        "T" | "TB" => TB,
        _ => return None,
    };

    Some((num * multiplier as f64) as u64)
}

/// Parse rotation string like "daily", "hourly", or "500 MB"
pub fn parse_rotation(rotation_str: &str) -> (Rotation, Option<u64>) {
    let rotation_str = rotation_str.trim().to_lowercase();

    match rotation_str.as_str() {
        "daily" | "1 day" | "1day" => (Rotation::Daily, None),
        "hourly" | "1 hour" | "1hour" => (Rotation::Hourly, None),
        _ => {
            if let Some(size) = parse_size(&rotation_str) {
                (Rotation::Never, Some(size))
            } else {
                (Rotation::Never, None)
            }
        }
    }
}

/// Parse retention string like "10 days" or number
pub fn parse_retention(retention_str: &str) -> (Option<u32>, Option<u32>) {
    let retention_str = retention_str.trim().to_lowercase();

    if retention_str.contains("day") {
        let num_part: String = retention_str
            .chars()
            .filter(|c| c.is_ascii_digit())
            .collect();
        if let Ok(days) = num_part.parse::<u32>() {
            return (Some(days), None);
        }
    }

    if let Ok(count) = retention_str.parse::<u32>() {
        return (None, Some(count));
    }

    (None, None)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_size() {
        assert_eq!(parse_size("100"), Some(100));
        assert_eq!(parse_size("100B"), Some(100));
        assert_eq!(parse_size("1 KB"), Some(KB));
        assert_eq!(parse_size("1KB"), Some(KB));
        assert_eq!(parse_size("500 MB"), Some(500 * MB));
        assert_eq!(parse_size("1 GB"), Some(GB));
    }

    #[test]
    fn test_parse_rotation() {
        assert_eq!(parse_rotation("daily"), (Rotation::Daily, None));
        assert_eq!(parse_rotation("hourly"), (Rotation::Hourly, None));
        assert_eq!(parse_rotation("500 MB"), (Rotation::Never, Some(500 * MB)));
    }

    #[test]
    fn test_parse_retention() {
        assert_eq!(parse_retention("10 days"), (Some(10), None));
        assert_eq!(parse_retention("5"), (None, Some(5)));
    }
}
