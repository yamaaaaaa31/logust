use std::fs::{self, File, OpenOptions};
use std::io::{self, BufWriter, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicI64, AtomicU32, AtomicU64, Ordering};
use std::sync::{Arc, LazyLock, OnceLock, Weak};
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

#[cfg(unix)]
static ATFORK_REGISTRATION: OnceLock<Result<(), i32>> = OnceLock::new();

#[cfg(unix)]
static ASYNC_SINK_REGISTRY: LazyLock<Mutex<Vec<Weak<FileSinkInner>>>> =
    LazyLock::new(|| Mutex::new(Vec::new()));

/// Rotation strategy
#[pyclass(eq, eq_int, from_py_object)]
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
#[pyclass(eq, eq_int, from_py_object)]
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
    Flush { ack: Sender<()> },
}

struct AsyncWriterState {
    sender: Option<Sender<WriterMessage>>,
    handle: Option<JoinHandle<()>>,
}

struct SyncWriterState {
    writer: Option<BufWriter<File>>,
}

/// Writer backend for FileSink
enum WriterBackend {
    /// Async writer with channel and background thread
    Async(AsyncWriterState),
    /// Sync writer with direct file access
    Sync(SyncWriterState),
}

struct FileSinkState {
    backend: WriterBackend,
}

struct FileSinkInner {
    config: FileSinkConfig,
    state: Mutex<FileSinkState>,
    /// Current file size in bytes (lock-free for hot path)
    current_size: AtomicU64,
    current_file_time: Mutex<DateTime<Local>>,
    /// Cached next rotation boundary as epoch milliseconds for O(1) time-based rotation check.
    /// 0 means no rotation boundary (equivalent to None).
    next_rotation_boundary: AtomicI64,
    /// PID of the process that currently owns the live backend.
    /// Child processes created via fork() lazily reopen/recreate the backend on first use.
    creation_pid: AtomicU32,
}

/// File sink with optional async writing support
pub struct FileSink {
    inner: Arc<FileSinkInner>,
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

        #[cfg(unix)]
        if config.enqueue {
            ensure_atfork_registered()?;
        }

        let backend = if config.enqueue {
            WriterBackend::Async(FileSinkInner::spawn_async_writer(&path)?)
        } else {
            WriterBackend::Sync(SyncWriterState {
                writer: Some(BufWriter::new(FileSinkInner::open_log_file(&path)?)),
            })
        };

        let now = Local::now();
        let next_boundary = FileSinkInner::calculate_next_rotation_boundary(&config.rotation, &now);

        let inner = Arc::new(FileSinkInner {
            config,
            state: Mutex::new(FileSinkState { backend }),
            current_size: AtomicU64::new(current_size),
            current_file_time: Mutex::new(now),
            next_rotation_boundary: AtomicI64::new(
                next_boundary.map(|b| b.timestamp_millis()).unwrap_or(0),
            ),
            creation_pid: AtomicU32::new(std::process::id()),
        });

        #[cfg(unix)]
        if inner.config.enqueue {
            register_async_sink(&inner);
        }

        Ok(FileSink { inner })
    }

    /// Write a message to the file (borrows message)
    #[inline]
    pub fn write(&self, message: &str) -> io::Result<()> {
        self.write_owned(message.to_string())
    }

    /// Write a message to the file (takes ownership, avoids clone in async mode)
    #[inline]
    pub fn write_owned(&self, message: String) -> io::Result<()> {
        self.inner.write_owned(message)
    }

    /// Flush pending writes
    pub fn flush(&self) -> io::Result<()> {
        self.inner.flush()
    }
}

impl FileSinkInner {
    fn open_log_file(path: &Path) -> io::Result<File> {
        OpenOptions::new().create(true).append(true).open(path)
    }

    fn spawn_async_writer(path: &Path) -> io::Result<AsyncWriterState> {
        let file = Self::open_log_file(path)?;
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
                    Ok(WriterMessage::Flush { ack }) => {
                        let _ = writer.flush();
                        let _ = ack.send(());
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

        Ok(AsyncWriterState {
            sender: Some(sender),
            handle: Some(writer_handle),
        })
    }

    fn write_owned(&self, message: String) -> io::Result<()> {
        self.maybe_rotate()?;

        let msg_len = message.len() as u64 + 1;

        let maybe_sender = {
            let mut state = self.state.lock();
            self.ensure_backend_ready_locked(&mut state)?;

            match &mut state.backend {
                WriterBackend::Async(async_state) => Some(
                    async_state
                        .sender
                        .as_ref()
                        .expect("async backend must have sender after ensure")
                        .clone(),
                ),
                WriterBackend::Sync(sync_state) => {
                    let writer = sync_state
                        .writer
                        .as_mut()
                        .ok_or_else(|| io::Error::other("sync backend writer missing"))?;
                    writeln!(writer, "{}", message)?;
                    None
                }
            }
        };

        if let Some(sender) = maybe_sender {
            self.send_with_retry(WriterMessage::Write(message), sender)?;
        }

        self.current_size.fetch_add(msg_len, Ordering::Relaxed);

        Ok(())
    }

    fn flush(&self) -> io::Result<()> {
        let maybe_sender = {
            let mut state = self.state.lock();
            self.ensure_backend_ready_locked(&mut state)?;

            match &mut state.backend {
                WriterBackend::Async(async_state) => Some(
                    async_state
                        .sender
                        .as_ref()
                        .expect("async backend must have sender after ensure")
                        .clone(),
                ),
                WriterBackend::Sync(sync_state) => {
                    if let Some(writer) = sync_state.writer.as_mut() {
                        writer.flush()?;
                    }
                    None
                }
            }
        };

        if let Some(sender) = maybe_sender {
            self.flush_async_sender(sender)?;
        }

        Ok(())
    }

    fn send_with_retry(
        &self,
        mut message: WriterMessage,
        mut sender: Sender<WriterMessage>,
    ) -> io::Result<()> {
        for attempt in 0..2 {
            match sender.send(message) {
                Ok(()) => return Ok(()),
                Err(err) => {
                    if attempt == 1 {
                        return Err(io::Error::other(err.to_string()));
                    }

                    message = err.0;
                    let mut state = self.state.lock();
                    self.reset_async_backend_locked(&mut state);
                    self.ensure_backend_ready_locked(&mut state)?;
                    sender = match &mut state.backend {
                        WriterBackend::Async(async_state) => async_state
                            .sender
                            .as_ref()
                            .expect("async backend must have sender after reset")
                            .clone(),
                        WriterBackend::Sync(_) => {
                            return Err(io::Error::other(
                                "async backend switched to sync unexpectedly",
                            ));
                        }
                    };
                }
            }
        }

        unreachable!("send_with_retry must return from the loop")
    }

    fn flush_async_sender(&self, sender: Sender<WriterMessage>) -> io::Result<()> {
        let (ack_tx, ack_rx) = bounded(0);
        self.send_with_retry(WriterMessage::Flush { ack: ack_tx }, sender)?;
        ack_rx.recv().map_err(|e| io::Error::other(e.to_string()))
    }

    fn ensure_backend_ready_locked(&self, state: &mut FileSinkState) -> io::Result<()> {
        let current_pid = std::process::id();
        let creation_pid = self.creation_pid.load(Ordering::Acquire);
        let pid_changed = current_pid != creation_pid;

        match &mut state.backend {
            WriterBackend::Async(async_state) => {
                if pid_changed {
                    Self::stop_async_writer_locked(async_state, false);
                    self.restart_async_writer_locked(async_state, current_pid)?;
                } else if async_state.sender.is_none() || async_state.handle.is_none() {
                    self.restart_async_writer_locked(async_state, current_pid)?;
                }
            }
            WriterBackend::Sync(sync_state) => {
                if pid_changed {
                    if let Some(writer) = sync_state.writer.take() {
                        std::mem::forget(writer);
                    }
                    sync_state.writer =
                        Some(BufWriter::new(Self::open_log_file(&self.config.path)?));
                    self.creation_pid.store(current_pid, Ordering::Release);
                    self.refresh_current_size_from_disk();
                } else if sync_state.writer.is_none() {
                    sync_state.writer =
                        Some(BufWriter::new(Self::open_log_file(&self.config.path)?));
                    self.creation_pid.store(current_pid, Ordering::Release);
                    self.refresh_current_size_from_disk();
                }
            }
        }

        Ok(())
    }

    fn restart_async_writer_locked(
        &self,
        async_state: &mut AsyncWriterState,
        current_pid: u32,
    ) -> io::Result<()> {
        *async_state = Self::spawn_async_writer(&self.config.path)?;
        self.creation_pid.store(current_pid, Ordering::Release);
        self.refresh_current_size_from_disk();
        Ok(())
    }

    fn reset_async_backend_locked(&self, state: &mut FileSinkState) {
        if let WriterBackend::Async(async_state) = &mut state.backend {
            let can_join = std::process::id() == self.creation_pid.load(Ordering::Acquire);
            Self::stop_async_writer_locked(async_state, can_join);
        }
    }

    fn stop_async_writer_locked(async_state: &mut AsyncWriterState, can_join: bool) {
        async_state.sender.take();

        if let Some(handle) = async_state.handle.take() {
            if can_join {
                let _ = handle.join();
            } else {
                std::mem::forget(handle);
            }
        }
    }

    fn pause_for_fork_best_effort(&self) {
        if let Some(mut state) = self.state.try_lock()
            && let WriterBackend::Async(async_state) = &mut state.backend
        {
            Self::stop_async_writer_locked(async_state, true);
        }
    }

    fn refresh_current_size_from_disk(&self) {
        let size = fs::metadata(&self.config.path)
            .map(|m| m.len())
            .unwrap_or(0);
        self.current_size.store(size, Ordering::Relaxed);
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

    /// Check and perform rotation if needed
    #[inline]
    fn maybe_rotate(&self) -> io::Result<()> {
        if std::process::id() != self.creation_pid.load(Ordering::Acquire) {
            let mut state = self.state.lock();
            self.ensure_backend_ready_locked(&mut state)?;

            if self.config.rotation == Rotation::Never && self.config.max_size.is_none() {
                return Ok(());
            }

            if self.check_rotation_needed() {
                self.rotate_locked(&mut state)?;
            }

            return Ok(());
        }

        if self.config.rotation == Rotation::Never && self.config.max_size.is_none() {
            return Ok(());
        }

        if !self.check_rotation_needed() {
            return Ok(());
        }

        let mut state = self.state.lock();
        if self.check_rotation_needed() {
            self.rotate_locked(&mut state)?;
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

    /// Perform rotation while holding the backend state lock.
    fn rotate_locked(&self, state: &mut FileSinkState) -> io::Result<()> {
        let now = Local::now();
        let can_join = std::process::id() == self.creation_pid.load(Ordering::Acquire);

        match &mut state.backend {
            WriterBackend::Async(async_state) => {
                Self::stop_async_writer_locked(async_state, can_join);
            }
            WriterBackend::Sync(sync_state) => {
                if let Some(writer) = sync_state.writer.as_mut() {
                    writer.flush()?;
                }
            }
        }

        let rotated_path = self.generate_rotated_path(&now);
        let mut rotation_error = None;

        if self.config.path.exists() {
            if let Err(err) = fs::rename(&self.config.path, &rotated_path) {
                if err.kind() != io::ErrorKind::NotFound {
                    rotation_error = Some(err);
                }
            } else if self.config.compression
                && let Err(err) = self.compress_file(&rotated_path)
            {
                rotation_error = Some(err);
            }
        }

        if rotation_error.is_none()
            && let Err(err) = self.apply_retention()
        {
            rotation_error = Some(err);
        }

        let reopen_result = match &mut state.backend {
            WriterBackend::Async(async_state) => {
                self.restart_async_writer_locked(async_state, std::process::id())
            }
            WriterBackend::Sync(sync_state) => {
                sync_state.writer = Some(BufWriter::new(Self::open_log_file(&self.config.path)?));
                self.creation_pid
                    .store(std::process::id(), Ordering::Release);
                self.refresh_current_size_from_disk();
                Ok(())
            }
        };

        if let Err(err) = reopen_result {
            return Err(rotation_error.unwrap_or(err));
        }

        *self.current_file_time.lock() = now;
        let next_boundary = Self::calculate_next_rotation_boundary(&self.config.rotation, &now);
        self.next_rotation_boundary.store(
            next_boundary.map(|b| b.timestamp_millis()).unwrap_or(0),
            Ordering::Relaxed,
        );

        if let Some(err) = rotation_error {
            return Err(err);
        }

        Ok(())
    }

    /// Generate path for rotated file.
    ///
    /// Include microseconds and PID to avoid cross-process rename collisions when
    /// multiple writers rotate the same sink concurrently.
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
        let micros = time.timestamp_subsec_micros();
        let filename = format!(
            "{}.{}_{:06}.pid{}.{}",
            stem,
            timestamp,
            micros,
            std::process::id(),
            ext
        );

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

impl Drop for FileSinkInner {
    fn drop(&mut self) {
        // If we're in a child process after fork(), inherited backend state belongs
        // to the parent process. The child either lazily rebuilt the backend and
        // updated `creation_pid`, or it never touched the sink and should drop it
        // without flushing/joining inherited resources.
        if std::process::id() != self.creation_pid.load(Ordering::Acquire) {
            let state = self.state.get_mut();
            match &mut state.backend {
                WriterBackend::Async(async_state) => {
                    async_state.sender.take();
                    if let Some(handle) = async_state.handle.take() {
                        std::mem::forget(handle);
                    }
                }
                WriterBackend::Sync(sync_state) => {
                    if let Some(writer) = sync_state.writer.take() {
                        std::mem::forget(writer);
                    }
                }
            }
            return;
        }

        let state = self.state.get_mut();
        match &mut state.backend {
            WriterBackend::Async(async_state) => {
                Self::stop_async_writer_locked(async_state, true);
            }
            WriterBackend::Sync(sync_state) => {
                if let Some(writer) = sync_state.writer.as_mut() {
                    let _ = writer.flush();
                }
            }
        }
    }
}

#[cfg(unix)]
fn ensure_atfork_registered() -> io::Result<()> {
    let result = ATFORK_REGISTRATION.get_or_init(|| {
        let rc = unsafe {
            libc::pthread_atfork(
                Some(file_sink_atfork_prepare),
                Some(file_sink_atfork_parent),
                Some(file_sink_atfork_child),
            )
        };

        if rc == 0 { Ok(()) } else { Err(rc) }
    });

    match result {
        Ok(()) => Ok(()),
        Err(code) => Err(io::Error::from_raw_os_error(*code)),
    }
}

#[cfg(unix)]
fn register_async_sink(sink: &Arc<FileSinkInner>) {
    let mut registry = ASYNC_SINK_REGISTRY.lock();
    registry.retain(|weak| weak.upgrade().is_some());
    registry.push(Arc::downgrade(sink));
}

#[cfg(unix)]
extern "C" fn file_sink_atfork_prepare() {
    if let Some(mut registry) = ASYNC_SINK_REGISTRY.try_lock() {
        registry.retain(|weak| {
            if let Some(sink) = weak.upgrade() {
                sink.pause_for_fork_best_effort();
                true
            } else {
                false
            }
        });
    }
}

#[cfg(unix)]
extern "C" fn file_sink_atfork_parent() {}

#[cfg(unix)]
extern "C" fn file_sink_atfork_child() {}

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
