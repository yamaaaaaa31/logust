use std::fs::{self, File, OpenOptions};
use std::io::{self, BufWriter, Read, Seek, Write};
#[cfg(unix)]
use std::os::fd::AsRawFd;
#[cfg(unix)]
use std::os::unix::fs::MetadataExt;
#[cfg(windows)]
use std::os::windows::io::AsRawHandle;
use std::path::{Path, PathBuf};
#[cfg(unix)]
use std::sync::TryLockError;
use std::sync::atomic::{AtomicBool, AtomicI64, AtomicU32, AtomicU64, Ordering};
use std::sync::{Arc, Mutex as StdMutex};
#[cfg(unix)]
use std::sync::{LazyLock, OnceLock, Weak};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

use bzip2::write::BzEncoder;
use chrono::{DateTime, Local, Timelike};
use crossbeam_channel::{RecvTimeoutError, Sender, bounded};
use flate2::Compression;
use flate2::write::GzEncoder;
use pyo3::prelude::*;
#[cfg(windows)]
use windows_sys::Win32::Foundation::HANDLE;
#[cfg(windows)]
use windows_sys::Win32::Storage::FileSystem::{
    BY_HANDLE_FILE_INFORMATION, GetFileInformationByHandle, LOCKFILE_EXCLUSIVE_LOCK, LockFileEx,
    UnlockFileEx,
};
#[cfg(windows)]
use windows_sys::Win32::System::IO::OVERLAPPED;

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
static ASYNC_SINK_REGISTRY: LazyLock<StdMutex<Vec<Weak<FileSinkInner>>>> =
    LazyLock::new(|| StdMutex::new(Vec::new()));

/// PID of the process that imported the extension. A different PID later means
/// this process is a fork() child.
#[cfg(target_vendor = "apple")]
static INIT_PID: std::sync::OnceLock<u32> = std::sync::OnceLock::new();

/// Record the importing process; called once from the module initializer.
pub fn record_init_pid() {
    #[cfg(target_vendor = "apple")]
    let _ = INIT_PID.set(std::process::id());
}

/// Whether `enqueue=True` may start a writer thread in this process.
///
/// On Apple platforms std's thread parking uses libdispatch, which traps
/// (SIGTRAP) in a fork() child once the parent has used it. A sink created in a
/// forked child therefore writes synchronously, the same fallback that
/// inherited `enqueue=True` sinks already use after fork().
fn async_writer_allowed() -> bool {
    #[cfg(target_vendor = "apple")]
    {
        INIT_PID.get().is_none_or(|pid| *pid == std::process::id())
    }
    #[cfg(not(target_vendor = "apple"))]
    {
        true
    }
}

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

/// Archive/compression format applied to rotated files.
///
/// Names follow loguru's `compression=` strings. Compression only runs at
/// rotation time, so the chosen format never affects the per-write path.
#[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
pub enum CompressionFormat {
    /// Keep rotated files as-is
    #[default]
    None,
    /// `.gz` (gzip)
    Gzip,
    /// `.bz2` (bzip2)
    Bzip2,
    /// `.zip` (single deflated entry)
    Zip,
    /// `.tar` (uncompressed tarball)
    Tar,
    /// `.tar.gz`
    TarGz,
    /// `.tar.bz2`
    TarBz2,
}

impl CompressionFormat {
    /// Every format logust can produce (used for retention matching).
    pub const ALL: [CompressionFormat; 6] = [
        CompressionFormat::Gzip,
        CompressionFormat::Bzip2,
        CompressionFormat::Zip,
        CompressionFormat::Tar,
        CompressionFormat::TarGz,
        CompressionFormat::TarBz2,
    ];

    /// File extension appended to the rotated file name (without leading dot).
    pub fn extension(self) -> Option<&'static str> {
        match self {
            CompressionFormat::None => None,
            CompressionFormat::Gzip => Some("gz"),
            CompressionFormat::Bzip2 => Some("bz2"),
            CompressionFormat::Zip => Some("zip"),
            CompressionFormat::Tar => Some("tar"),
            CompressionFormat::TarGz => Some("tar.gz"),
            CompressionFormat::TarBz2 => Some("tar.bz2"),
        }
    }
}

/// Supported `compression=` strings, for error messages.
pub const SUPPORTED_COMPRESSION_FORMATS: &str = "gz, bz2, zip, tar, tar.gz, tar.bz2";

/// Parse a loguru-style compression format string ("gz", ".zip", "tar.gz", ...).
pub fn parse_compression(format: &str) -> Result<CompressionFormat, String> {
    let normalized = format.trim().trim_start_matches('.').to_ascii_lowercase();
    match normalized.as_str() {
        "gz" => Ok(CompressionFormat::Gzip),
        "bz2" => Ok(CompressionFormat::Bzip2),
        "zip" => Ok(CompressionFormat::Zip),
        "tar" => Ok(CompressionFormat::Tar),
        "tar.gz" => Ok(CompressionFormat::TarGz),
        "tar.bz2" => Ok(CompressionFormat::TarBz2),
        "xz" | "lzma" | "tar.xz" => Err(format!(
            "compression format '{format}' is not supported by logust \
             (no LZMA encoder is bundled); supported formats: {SUPPORTED_COMPRESSION_FORMATS}"
        )),
        _ => Err(format!(
            "Invalid compression format: '{format}'; supported formats: \
             {SUPPORTED_COMPRESSION_FORMATS}"
        )),
    }
}

/// File sink configuration
#[derive(Clone)]
pub struct FileSinkConfig {
    pub path: PathBuf,
    pub rotation: Rotation,
    pub max_size: Option<u64>,
    pub retention_days: Option<u32>,
    pub retention_count: Option<u32>,
    pub compression: CompressionFormat,
    /// If true, writes are queued and processed asynchronously (thread-safe)
    /// If false, writes are synchronous (faster for single-threaded use)
    pub enqueue: bool,
    /// Truncate the file when it is first opened (loguru `mode="w"`).
    /// Re-opens after rotation or fork always append.
    pub truncate: bool,
    /// Defer creating/opening the file until the first message is written
    /// (loguru `delay=True`).
    pub delay: bool,
}

impl Default for FileSinkConfig {
    fn default() -> Self {
        FileSinkConfig {
            path: PathBuf::from("app.log"),
            rotation: Rotation::Never,
            max_size: None,
            retention_days: None,
            retention_count: None,
            compression: CompressionFormat::None,
            enqueue: false,
            truncate: false,
            delay: false,
        }
    }
}

/// Async message for file writer thread
enum WriterMessage {
    Write(String),
    Flush { ack: Sender<()> },
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct FileIdentity {
    #[cfg(unix)]
    dev: u64,
    #[cfg(unix)]
    ino: u64,
    #[cfg(windows)]
    volume: u32,
    #[cfg(windows)]
    index: u64,
}

impl FileIdentity {
    #[cfg(unix)]
    fn from_metadata(metadata: &fs::Metadata) -> io::Result<Self> {
        Ok(Self {
            dev: metadata.dev(),
            ino: metadata.ino(),
        })
    }

    #[cfg(not(any(unix, windows)))]
    fn from_metadata(_metadata: &fs::Metadata) -> io::Result<Self> {
        Ok(Self {})
    }

    #[cfg(windows)]
    fn from_file(file: &File) -> io::Result<Self> {
        Self::from_handle(file.as_raw_handle() as HANDLE)
    }

    #[cfg(unix)]
    fn from_file(file: &File) -> io::Result<Self> {
        Self::from_metadata(&file.metadata()?)
    }

    #[cfg(not(any(unix, windows)))]
    fn from_file(file: &File) -> io::Result<Self> {
        Self::from_metadata(&file.metadata()?)
    }

    #[cfg(windows)]
    fn from_path(path: &Path) -> io::Result<Self> {
        // `std::os::windows::fs::MetadataExt::{volume_serial_number, file_index}`
        // are nightly-only (`windows_by_handle`), so open the file with shared
        // access and read the identity via `GetFileInformationByHandle`.
        let file = OpenOptions::new().read(true).open(path)?;
        Self::from_file(&file)
    }

    #[cfg(not(windows))]
    fn from_path(path: &Path) -> io::Result<Self> {
        Self::from_metadata(&fs::metadata(path)?)
    }

    #[cfg(windows)]
    fn from_handle(handle: HANDLE) -> io::Result<Self> {
        let mut info = BY_HANDLE_FILE_INFORMATION::default();
        let rc = unsafe { GetFileInformationByHandle(handle, &mut info) };
        if rc == 0 {
            return Err(io::Error::last_os_error());
        }

        Ok(Self::from_handle_info(info))
    }

    #[cfg(windows)]
    fn from_handle_info(info: BY_HANDLE_FILE_INFORMATION) -> Self {
        Self {
            volume: info.dwVolumeSerialNumber,
            index: ((info.nFileIndexHigh as u64) << 32) | info.nFileIndexLow as u64,
        }
    }
}

#[derive(Default)]
struct SharedFileIdentity {
    present: AtomicBool,
    #[cfg(unix)]
    dev: AtomicU64,
    #[cfg(unix)]
    ino: AtomicU64,
    #[cfg(windows)]
    volume: AtomicU32,
    #[cfg(windows)]
    index: AtomicU64,
}

impl SharedFileIdentity {
    fn store(&self, identity: Option<FileIdentity>) {
        if let Some(identity) = identity {
            #[cfg(unix)]
            {
                self.dev.store(identity.dev, Ordering::Release);
                self.ino.store(identity.ino, Ordering::Release);
            }

            #[cfg(windows)]
            {
                self.volume.store(identity.volume, Ordering::Release);
                self.index.store(identity.index, Ordering::Release);
            }

            self.present.store(true, Ordering::Release);
        } else {
            self.present.store(false, Ordering::Release);
        }
    }

    fn load(&self) -> Option<FileIdentity> {
        if !self.present.load(Ordering::Acquire) {
            return None;
        }

        #[cfg(unix)]
        {
            Some(FileIdentity {
                dev: self.dev.load(Ordering::Acquire),
                ino: self.ino.load(Ordering::Acquire),
            })
        }

        #[cfg(windows)]
        {
            Some(FileIdentity {
                volume: self.volume.load(Ordering::Acquire),
                index: self.index.load(Ordering::Acquire),
            })
        }

        #[cfg(not(any(unix, windows)))]
        {
            None
        }
    }
}

/// Holds a lock on the rotation lock file until dropped.
///
/// The guard keeps its own `Arc` to the open file, so the lock outlives a
/// writer re-open that replaces the file handle (as a `dup()`ed descriptor
/// would) without a `dup`/`close` syscall pair per locked write.
struct FileLockGuard {
    #[cfg(any(unix, windows))]
    file: Arc<File>,
    #[cfg(not(any(unix, windows)))]
    _phantom: std::marker::PhantomData<()>,
}

impl FileLockGuard {
    fn shared(file: &Arc<File>) -> io::Result<Self> {
        #[cfg(unix)]
        {
            flock_file(file, libc::LOCK_SH)?;
            Ok(Self {
                file: Arc::clone(file),
            })
        }

        #[cfg(windows)]
        {
            windows_lock_file(file, false)?;
            Ok(Self {
                file: Arc::clone(file),
            })
        }

        #[cfg(not(any(unix, windows)))]
        {
            let _ = file;
            Ok(Self {
                _phantom: std::marker::PhantomData,
            })
        }
    }

    fn exclusive(file: &Arc<File>) -> io::Result<Self> {
        #[cfg(unix)]
        {
            flock_file(file, libc::LOCK_EX)?;
            Ok(Self {
                file: Arc::clone(file),
            })
        }

        #[cfg(windows)]
        {
            windows_lock_file(file, true)?;
            Ok(Self {
                file: Arc::clone(file),
            })
        }

        #[cfg(not(any(unix, windows)))]
        {
            let _ = file;
            Ok(Self {
                _phantom: std::marker::PhantomData,
            })
        }
    }
}

impl Drop for FileLockGuard {
    fn drop(&mut self) {
        #[cfg(unix)]
        let _ = flock_file(&self.file, libc::LOCK_UN);

        #[cfg(windows)]
        let _ = windows_unlock_file(&self.file);
    }
}

#[cfg(unix)]
fn flock_file(file: &File, operation: i32) -> io::Result<()> {
    loop {
        let rc = unsafe { libc::flock(file.as_raw_fd(), operation) };
        if rc == 0 {
            return Ok(());
        }

        let err = io::Error::last_os_error();
        if err.raw_os_error() == Some(libc::EINTR) {
            continue;
        }
        return Err(err);
    }
}

#[cfg(windows)]
fn windows_lock_file(file: &File, exclusive: bool) -> io::Result<()> {
    let mut overlapped = OVERLAPPED::default();
    let flags = if exclusive {
        LOCKFILE_EXCLUSIVE_LOCK
    } else {
        0
    };
    let rc = unsafe {
        LockFileEx(
            file.as_raw_handle() as HANDLE,
            flags,
            0,
            1,
            0,
            &mut overlapped,
        )
    };

    if rc == 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(())
    }
}

#[cfg(windows)]
fn windows_unlock_file(file: &File) -> io::Result<()> {
    let mut overlapped = OVERLAPPED::default();
    let rc = unsafe { UnlockFileEx(file.as_raw_handle() as HANDLE, 0, 1, 0, &mut overlapped) };

    if rc == 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(())
    }
}

struct RotatingFileWriter {
    writer: BufWriter<File>,
    lock_file: Arc<File>,
    file_identity: Option<FileIdentity>,
    shared_identity: Option<Arc<SharedFileIdentity>>,
}

impl RotatingFileWriter {
    fn open(path: &Path, shared_identity: Option<Arc<SharedFileIdentity>>) -> io::Result<Self> {
        let file = FileSinkInner::open_log_file(path)?;
        let lock_file = FileSinkInner::open_rotation_lock_file(path)?;
        Ok(Self::from_open_files(file, lock_file, shared_identity))
    }

    fn from_open_files(
        file: File,
        lock_file: File,
        shared_identity: Option<Arc<SharedFileIdentity>>,
    ) -> Self {
        let file_identity = FileIdentity::from_file(&file).ok();

        let writer = Self {
            writer: BufWriter::new(file),
            lock_file: Arc::new(lock_file),
            file_identity,
            shared_identity,
        };
        writer.update_shared_identity();
        writer
    }

    fn write_line(&mut self, path: &Path, message: &str) -> io::Result<()> {
        let _lock = self.acquire_shared_lock(path)?;
        self.write_line_unlocked(message)?;
        self.writer.flush()
    }

    /// Append `message` and a newline to the buffer (no fmt machinery)
    fn write_line_unlocked(&mut self, message: &str) -> io::Result<()> {
        self.writer.write_all(message.as_bytes())?;
        self.writer.write_all(b"\n")
    }

    fn write_line_buffered(
        &mut self,
        path: &Path,
        message: &str,
        batch_lock: &mut Option<FileLockGuard>,
    ) -> io::Result<()> {
        if batch_lock.is_none() {
            *batch_lock = Some(self.acquire_shared_lock(path)?);
        }

        self.write_line_unlocked(message)
    }

    fn flush_buffered(
        &mut self,
        path: &Path,
        batch_lock: &mut Option<FileLockGuard>,
    ) -> io::Result<()> {
        let _temporary_lock = if batch_lock.is_none() {
            Some(self.acquire_shared_lock(path)?)
        } else {
            None
        };

        let result = self.writer.flush();
        batch_lock.take();
        result
    }

    fn acquire_shared_lock(&mut self, path: &Path) -> io::Result<FileLockGuard> {
        let lock = FileLockGuard::shared(&self.lock_file)?;
        self.reopen_if_rotated(path)?;
        Ok(lock)
    }

    fn flush(&mut self, path: &Path) -> io::Result<()> {
        let _lock = self.acquire_shared_lock(path)?;
        self.writer.flush()
    }

    fn flush_without_lock(&mut self) -> io::Result<()> {
        self.writer.flush()
    }

    fn reopen_if_rotated(&mut self, path: &Path) -> io::Result<bool> {
        #[cfg(any(unix, windows))]
        {
            let current_identity = match FileIdentity::from_path(path) {
                Ok(identity) => Some(identity),
                Err(err) if err.kind() == io::ErrorKind::NotFound => None,
                Err(err) => return Err(err),
            };

            if current_identity == self.file_identity {
                return Ok(false);
            }

            self.writer.flush()?;
            let shared_identity = self.shared_identity.clone();
            *self = Self::open(path, shared_identity)?;
            Ok(true)
        }

        #[cfg(not(any(unix, windows)))]
        {
            let _ = path;
            Ok(false)
        }
    }

    fn update_shared_identity(&self) {
        if let Some(shared_identity) = &self.shared_identity {
            shared_identity.store(self.file_identity);
        }
    }
}

struct AsyncWriterState {
    sender: Option<Sender<WriterMessage>>,
    handle: Option<JoinHandle<()>>,
    file_identity: Arc<SharedFileIdentity>,
}

struct SyncWriterState {
    writer: Option<RotatingFileWriter>,
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

#[derive(Clone)]
struct PendingRotation {
    rotated_path: PathBuf,
    rotation_time: DateTime<Local>,
    needs_compression: bool,
    needs_retention: bool,
}

struct FileSinkInner {
    config: FileSinkConfig,
    state: StdMutex<FileSinkState>,
    /// Current file size in bytes (lock-free for hot path)
    current_size: AtomicU64,
    current_file_time: StdMutex<DateTime<Local>>,
    /// Cached next rotation boundary as epoch milliseconds for O(1) time-based rotation check.
    /// 0 means no time-based rotation is configured (`Rotation::Never`); with
    /// `Daily` or `Hourly` this is always a real instant, see
    /// `calculate_next_rotation_boundary`.
    next_rotation_boundary: AtomicI64,
    /// PID of the process that currently owns the live backend.
    /// Child processes created via fork() lazily reopen/recreate the backend on first use.
    creation_pid: AtomicU32,
    pending_rotation: StdMutex<Option<PendingRotation>>,
    pending_rotation_active: AtomicBool,
    /// `mode="w"` with `delay=True`: truncate when the backend is first opened.
    /// Only consulted on open paths, never per write.
    truncate_on_open: AtomicBool,
}

/// File sink with optional async writing support
pub struct FileSink {
    inner: Arc<FileSinkInner>,
}

impl FileSink {
    /// Create a new file sink
    pub fn new(mut config: FileSinkConfig) -> io::Result<Self> {
        if config.enqueue && !async_writer_allowed() {
            config.enqueue = false;
        }
        let path = config.path.clone();

        if !config.delay {
            FileSinkInner::create_parent_dirs(&path)?;
            if config.truncate {
                FileSinkInner::truncate_log_file(&path)?;
            }
        }

        let current_size = if config.truncate {
            0
        } else {
            fs::metadata(&path).map(|m| m.len()).unwrap_or(0)
        };

        #[cfg(unix)]
        if config.enqueue {
            ensure_atfork_registered()?;
        }

        // With `delay`, the backend starts unopened; the existing lazy-open
        // path in `ensure_backend_ready_locked` opens it on the first write.
        let backend = if config.enqueue {
            if config.delay {
                WriterBackend::Async(AsyncWriterState {
                    sender: None,
                    handle: None,
                    file_identity: Arc::new(SharedFileIdentity::default()),
                })
            } else {
                WriterBackend::Async(FileSinkInner::create_async_writer_state(
                    &path,
                    FileSinkInner::rotation_coordination_enabled_for_config(&config),
                )?)
            }
        } else if config.delay {
            WriterBackend::Sync(SyncWriterState { writer: None })
        } else {
            WriterBackend::Sync(SyncWriterState {
                writer: Some(FileSinkInner::open_sync_writer(&path)?),
            })
        };
        let truncate_on_open = config.delay && config.truncate;

        // A non-empty file left over from an earlier run belongs to the period
        // it was last written in, so the first write after that period's
        // boundary rotates it (loguru rotates on the file's creation time).
        let now = Local::now();
        let file_time = if config.truncate || current_size == 0 {
            now
        } else {
            fs::metadata(&path)
                .and_then(|m| m.modified())
                .map(DateTime::<Local>::from)
                .ok()
                .filter(|modified| *modified <= now)
                .unwrap_or(now)
        };
        let next_boundary =
            FileSinkInner::calculate_next_rotation_boundary(&config.rotation, &file_time);

        let inner = Arc::new(FileSinkInner {
            config,
            state: StdMutex::new(FileSinkState { backend }),
            current_size: AtomicU64::new(current_size),
            current_file_time: StdMutex::new(file_time),
            next_rotation_boundary: AtomicI64::new(
                next_boundary.map(|b| b.timestamp_millis()).unwrap_or(0),
            ),
            creation_pid: AtomicU32::new(std::process::id()),
            pending_rotation: StdMutex::new(None),
            pending_rotation_active: AtomicBool::new(false),
            truncate_on_open: AtomicBool::new(truncate_on_open),
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
    fn rotation_coordination_enabled_for_config(config: &FileSinkConfig) -> bool {
        config.rotation != Rotation::Never || config.max_size.is_some()
    }

    fn rotation_coordination_enabled(&self) -> bool {
        Self::rotation_coordination_enabled_for_config(&self.config)
            || self.pending_rotation_active.load(Ordering::Acquire)
    }

    fn format_lock_filename(path: &Path) -> PathBuf {
        let mut lock_path = path.as_os_str().to_os_string();
        lock_path.push(".lock");
        PathBuf::from(lock_path)
    }

    fn create_parent_dirs(path: &Path) -> io::Result<()> {
        if let Some(parent) = path.parent()
            && !parent.as_os_str().is_empty()
        {
            fs::create_dir_all(parent)?;
        }
        Ok(())
    }

    fn truncate_log_file(path: &Path) -> io::Result<()> {
        OpenOptions::new()
            .create(true)
            .write(true)
            .truncate(true)
            .open(path)
            .map(drop)
    }

    fn open_log_file(path: &Path) -> io::Result<File> {
        match OpenOptions::new().create(true).append(true).open(path) {
            // The parent directory may not exist yet with `delay=True`, or may
            // have been removed since the sink was added: create it and retry.
            Err(err) if err.kind() == io::ErrorKind::NotFound => {
                Self::create_parent_dirs(path)?;
                OpenOptions::new().create(true).append(true).open(path)
            }
            result => result,
        }
    }

    fn open_rotation_lock_file(path: &Path) -> io::Result<File> {
        let lock_path = Self::format_lock_filename(path);
        OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .open(lock_path)
    }

    /// `mode="w"` + `delay=True`: truncate once, right before the first open.
    fn apply_pending_truncate(&self) -> io::Result<()> {
        if self.truncate_on_open.load(Ordering::Acquire)
            && self.truncate_on_open.swap(false, Ordering::AcqRel)
        {
            Self::create_parent_dirs(&self.config.path)?;
            Self::truncate_log_file(&self.config.path)?;
            self.current_size.store(0, Ordering::Relaxed);
        }
        Ok(())
    }

    /// True while a `delay=True` sink has not opened its file yet (or the
    /// backend was torn down and nothing is buffered).
    fn backend_unopened(state: &FileSinkState) -> bool {
        match &state.backend {
            WriterBackend::Async(async_state) => {
                async_state.sender.is_none() || async_state.handle.is_none()
            }
            WriterBackend::Sync(sync_state) => sync_state.writer.is_none(),
        }
    }

    fn open_sync_writer(path: &Path) -> io::Result<RotatingFileWriter> {
        RotatingFileWriter::open(path, None)
    }

    fn create_async_writer_state(
        path: &Path,
        coordinate_rotation: bool,
    ) -> io::Result<AsyncWriterState> {
        let file_identity = Arc::new(SharedFileIdentity::default());
        let writer = RotatingFileWriter::open(path, Some(Arc::clone(&file_identity)))?;
        Ok(Self::spawn_async_writer(
            path.to_path_buf(),
            writer,
            file_identity,
            coordinate_rotation,
        ))
    }

    fn spawn_async_writer(
        path: PathBuf,
        mut writer: RotatingFileWriter,
        file_identity: Arc<SharedFileIdentity>,
        coordinate_rotation: bool,
    ) -> AsyncWriterState {
        let (sender, receiver) = bounded::<WriterMessage>(ASYNC_QUEUE_CAPACITY);

        let writer_handle = thread::spawn(move || {
            let flush_interval = Duration::from_millis(ASYNC_FLUSH_INTERVAL_MS);
            let mut last_flush = Instant::now();
            let mut batch_lock = None;

            loop {
                let timeout = if coordinate_rotation {
                    flush_interval
                        .checked_sub(last_flush.elapsed())
                        .unwrap_or(Duration::ZERO)
                } else {
                    flush_interval
                };

                match receiver.recv_timeout(timeout) {
                    Ok(WriterMessage::Write(msg)) => {
                        let result = if coordinate_rotation {
                            writer.write_line_buffered(&path, &msg, &mut batch_lock)
                        } else {
                            writer.write_line_unlocked(&msg)
                        };

                        if let Err(err) = result {
                            // Never `eprintln!` here: a broken stderr would
                            // panic and kill the writer thread.
                            let _ = writeln!(io::stderr(), "Failed to write to log: {}", err);
                        }

                        if coordinate_rotation && last_flush.elapsed() >= flush_interval {
                            let _ = writer.flush_buffered(&path, &mut batch_lock);
                            last_flush = Instant::now();
                        }
                    }
                    Ok(WriterMessage::Flush { ack }) => {
                        if coordinate_rotation {
                            let _ = writer.flush_buffered(&path, &mut batch_lock);
                            last_flush = Instant::now();
                        } else {
                            let _ = writer.flush_without_lock();
                        }
                        let _ = ack.send(());
                    }
                    Err(RecvTimeoutError::Timeout) => {
                        if coordinate_rotation {
                            if batch_lock.is_some() {
                                let _ = writer.flush_buffered(&path, &mut batch_lock);
                            }
                            last_flush = Instant::now();
                        } else {
                            let _ = writer.flush_without_lock();
                        }
                    }
                    Err(RecvTimeoutError::Disconnected) => {
                        if coordinate_rotation {
                            let _ = writer.flush_buffered(&path, &mut batch_lock);
                        } else {
                            let _ = writer.flush_without_lock();
                        }
                        break;
                    }
                }
            }
        });

        AsyncWriterState {
            sender: Some(sender),
            handle: Some(writer_handle),
            file_identity,
        }
    }

    fn write_owned(&self, message: String) -> io::Result<()> {
        self.maybe_rotate()?;

        let msg_len = message.len() as u64 + 1;
        let coordinate_rotation = self.rotation_coordination_enabled();

        let maybe_sender = {
            let mut state = self.state.lock().unwrap_or_else(|e| e.into_inner());
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
                    if coordinate_rotation {
                        writer.write_line(&self.config.path, &message)?;
                    } else {
                        writer.write_line_unlocked(&message)?;
                    }
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
        let coordinate_rotation = self.rotation_coordination_enabled();

        let maybe_sender = {
            let mut state = self.state.lock().unwrap_or_else(|e| e.into_inner());
            // Nothing can be buffered in an unopened backend; returning early
            // also keeps `delay=True` sinks from creating the file on flush.
            if Self::backend_unopened(&state) {
                return Ok(());
            }
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
                        if coordinate_rotation {
                            writer.flush(&self.config.path)?;
                        } else {
                            writer.flush_without_lock()?;
                        }
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
                    let mut state = self.state.lock().unwrap_or_else(|e| e.into_inner());
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
        let coordinate_rotation = self.rotation_coordination_enabled();

        if pid_changed {
            match &mut state.backend {
                WriterBackend::Async(async_state) => {
                    // Forked children inherit enqueue=True configuration but avoid
                    // creating a new writer thread in the post-fork process.
                    Self::stop_async_writer_locked(async_state, false);
                    self.apply_pending_truncate()?;
                    state.backend = WriterBackend::Sync(SyncWriterState {
                        writer: Some(Self::open_sync_writer(&self.config.path)?),
                    });
                    self.creation_pid.store(current_pid, Ordering::Release);
                    self.sync_rotation_state_from_path();
                }
                WriterBackend::Sync(sync_state) => {
                    if let Some(writer) = sync_state.writer.take() {
                        std::mem::forget(writer);
                    }
                    self.apply_pending_truncate()?;
                    sync_state.writer = Some(Self::open_sync_writer(&self.config.path)?);
                    self.creation_pid.store(current_pid, Ordering::Release);
                    self.sync_rotation_state_from_path();
                }
            }

            return Ok(());
        }

        match &mut state.backend {
            WriterBackend::Async(async_state) => {
                if async_state.sender.is_none() || async_state.handle.is_none() {
                    self.restart_async_writer_locked(async_state, current_pid)?;
                } else if coordinate_rotation
                    && self.path_identity_changed(async_state.file_identity.load())?
                {
                    self.sync_rotation_state_from_path();
                }
            }
            WriterBackend::Sync(sync_state) => {
                if let Some(writer) = sync_state.writer.as_mut() {
                    if coordinate_rotation && writer.reopen_if_rotated(&self.config.path)? {
                        self.sync_rotation_state_from_path();
                    }
                } else {
                    self.apply_pending_truncate()?;
                    sync_state.writer = Some(Self::open_sync_writer(&self.config.path)?);
                    self.creation_pid.store(current_pid, Ordering::Release);
                    self.sync_rotation_state_from_path();
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
        self.apply_pending_truncate()?;
        *async_state = Self::create_async_writer_state(
            &self.config.path,
            self.rotation_coordination_enabled(),
        )?;
        self.creation_pid.store(current_pid, Ordering::Release);
        self.sync_rotation_state_from_path();
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

        async_state.file_identity.store(None);
    }

    #[cfg(unix)]
    fn pause_for_fork_prepare(&self) {
        let Some(mut state) = try_lock_or_recover(&self.state) else {
            return;
        };
        if let WriterBackend::Async(async_state) = &mut state.backend {
            let can_join = std::process::id() == self.creation_pid.load(Ordering::Acquire);
            Self::stop_async_writer_locked(async_state, can_join);
        }
    }

    fn sync_rotation_state_from_path(&self) {
        match fs::metadata(&self.config.path) {
            Ok(metadata) => {
                self.current_size.store(metadata.len(), Ordering::Relaxed);

                let file_time = metadata
                    .modified()
                    .map(DateTime::<Local>::from)
                    .unwrap_or_else(|_| Local::now());
                *self
                    .current_file_time
                    .lock()
                    .unwrap_or_else(|e| e.into_inner()) = file_time;
                let next_boundary =
                    Self::calculate_next_rotation_boundary(&self.config.rotation, &file_time);
                self.next_rotation_boundary.store(
                    next_boundary.map(|b| b.timestamp_millis()).unwrap_or(0),
                    Ordering::Relaxed,
                );
            }
            Err(err) if err.kind() == io::ErrorKind::NotFound => {
                self.current_size.store(0, Ordering::Relaxed);
            }
            Err(_) => {}
        }
    }

    fn path_identity_changed(&self, known_identity: Option<FileIdentity>) -> io::Result<bool> {
        #[cfg(any(unix, windows))]
        {
            let path_identity = match FileIdentity::from_path(&self.config.path) {
                Ok(identity) => Some(identity),
                Err(err) if err.kind() == io::ErrorKind::NotFound => None,
                Err(err) => return Err(err),
            };
            Ok(path_identity != known_identity)
        }

        #[cfg(not(any(unix, windows)))]
        {
            let _ = known_identity;
            Ok(false)
        }
    }

    /// Calculate the next rotation boundary based on rotation strategy.
    ///
    /// The boundary is the next local wall-clock midnight (`Daily`) or top of
    /// the hour (`Hourly`) after `from`, resolved to an instant with the same
    /// rules loguru applies to its naive local times:
    ///
    /// - an ambiguous wall-clock time (DST fall-back) rotates at its first
    ///   occurrence; the repeated hour does not rotate a second time
    /// - a nonexistent wall-clock time (DST spring-forward gap) rotates at the
    ///   first instant after the gap, that is at the transition itself
    ///
    /// Only `Rotation::Never` yields `None`. If the local zone cannot resolve
    /// the boundary at all, the sink falls back to `from` plus one period
    /// measured in absolute time, so a configured rotation never stops.
    /// This runs only when a file is opened or rotated, never per write.
    fn calculate_next_rotation_boundary(
        rotation: &Rotation,
        from: &DateTime<Local>,
    ) -> Option<DateTime<Local>> {
        use chrono::Duration;

        let (naive_boundary, period) = match rotation {
            Rotation::Never => return None,
            Rotation::Daily => {
                let tomorrow = from.date_naive() + Duration::days(1);
                (
                    tomorrow.and_hms_opt(0, 0, 0).unwrap_or(from.naive_local()),
                    Duration::days(1),
                )
            }
            Rotation::Hourly => {
                let this_hour = from
                    .date_naive()
                    .and_hms_opt(from.hour(), 0, 0)
                    .unwrap_or(from.naive_local());
                (this_hour + Duration::hours(1), Duration::hours(1))
            }
        };

        let boundary = Self::resolve_local_boundary(naive_boundary)
            .filter(|boundary| boundary > from)
            .unwrap_or_else(|| *from + period);
        Some(boundary)
    }

    /// Map a local wall-clock boundary to an instant, tolerating DST changes.
    ///
    /// Returns the earliest instant at which a local clock shows `naive`, or
    /// the first instant after a gap (probed minute by minute, since DST gaps
    /// are whole minutes). `None` only if the zone has no valid local time for
    /// two days after `naive`.
    fn resolve_local_boundary(naive: chrono::NaiveDateTime) -> Option<DateTime<Local>> {
        use chrono::{LocalResult, TimeZone};

        const MAX_GAP_PROBES: u32 = 48 * 60;

        let mut probe = naive;
        for _ in 0..MAX_GAP_PROBES {
            let candidates = match probe.and_local_timezone(Local) {
                LocalResult::Single(instant) => [Some(instant), None],
                // chrono orders the pair differently for TZif data and POSIX
                // rule strings, so order by instant instead of trusting it
                LocalResult::Ambiguous(a, b) if a <= b => [Some(a), Some(b)],
                LocalResult::Ambiguous(a, b) => [Some(b), Some(a)],
                LocalResult::None => [None, None],
            };
            for candidate in candidates.into_iter().flatten() {
                // chrono reports the instant that closes a transition (02:00
                // on a US fall-back day, 02:00 on a spring-forward day) as a
                // valid local time although no clock ever shows it. Re-derive
                // the wall-clock time from the instant to skip those.
                let shown = Local
                    .from_utc_datetime(&candidate.naive_utc())
                    .naive_local();
                if shown == probe {
                    return Some(candidate);
                }
            }
            probe += chrono::Duration::minutes(1);
        }
        None
    }

    /// Check and perform rotation if needed
    #[inline]
    fn maybe_rotate(&self) -> io::Result<()> {
        let pid_changed = std::process::id() != self.creation_pid.load(Ordering::Acquire);

        if self.config.rotation == Rotation::Never && self.config.max_size.is_none() {
            if pid_changed {
                let mut state = self.state.lock().unwrap_or_else(|e| e.into_inner());
                self.ensure_backend_ready_locked(&mut state)?;
            }
            return Ok(());
        }

        if pid_changed {
            let mut state = self.state.lock().unwrap_or_else(|e| e.into_inner());
            self.ensure_backend_ready_locked(&mut state)?;

            if self.check_rotation_needed() {
                self.rotate_locked(&mut state)?;
            }

            return Ok(());
        }

        if !self.check_rotation_needed() {
            return Ok(());
        }

        let mut state = self.state.lock().unwrap_or_else(|e| e.into_inner());
        self.ensure_backend_ready_locked(&mut state)?;
        if self.check_rotation_needed() {
            self.rotate_locked(&mut state)?;
        }

        Ok(())
    }

    /// Check if rotation is needed (lock-free hot path)
    #[inline]
    fn check_rotation_needed(&self) -> bool {
        if self.pending_rotation_active.load(Ordering::Acquire) {
            return true;
        }

        if let Some(max_size) = self.config.max_size {
            let current_size = self.current_size.load(Ordering::Relaxed);
            if current_size >= max_size {
                match fs::metadata(&self.config.path) {
                    Ok(metadata) => {
                        let actual_size = metadata.len();
                        self.current_size.store(actual_size, Ordering::Relaxed);
                        if actual_size >= max_size {
                            return true;
                        }
                    }
                    Err(err) if err.kind() == io::ErrorKind::NotFound => {
                        self.current_size.store(0, Ordering::Relaxed);
                    }
                    Err(_) => return true,
                }
            }
        }

        let boundary_millis = self.next_rotation_boundary.load(Ordering::Relaxed);
        if boundary_millis > 0 {
            // Same value as `Local::now().timestamp_millis()`, without the zone lookup
            chrono::Utc::now().timestamp_millis() >= boundary_millis
        } else {
            false
        }
    }

    fn load_pending_rotation(&self) -> Option<PendingRotation> {
        if !self.pending_rotation_active.load(Ordering::Acquire) {
            return None;
        }

        self.pending_rotation
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .clone()
    }

    fn store_pending_rotation(&self, pending: PendingRotation) {
        *self
            .pending_rotation
            .lock()
            .unwrap_or_else(|e| e.into_inner()) = Some(pending);
        self.pending_rotation_active.store(true, Ordering::Release);
    }

    fn clear_pending_rotation(&self) {
        *self
            .pending_rotation
            .lock()
            .unwrap_or_else(|e| e.into_inner()) = None;
        self.pending_rotation_active.store(false, Ordering::Release);
    }

    fn advance_rotation_time_boundary(&self, rotation_time: DateTime<Local>) {
        *self
            .current_file_time
            .lock()
            .unwrap_or_else(|e| e.into_inner()) = rotation_time;
        let next_boundary =
            Self::calculate_next_rotation_boundary(&self.config.rotation, &rotation_time);
        self.next_rotation_boundary.store(
            next_boundary.map(|b| b.timestamp_millis()).unwrap_or(0),
            Ordering::Relaxed,
        );
    }

    fn reopen_backend_locked(&self, state: &mut FileSinkState) -> io::Result<()> {
        match &mut state.backend {
            WriterBackend::Async(async_state) => {
                self.restart_async_writer_locked(async_state, std::process::id())
            }
            WriterBackend::Sync(sync_state) => {
                self.apply_pending_truncate()?;
                sync_state.writer = Some(Self::open_sync_writer(&self.config.path)?);
                self.creation_pid
                    .store(std::process::id(), Ordering::Release);
                self.sync_rotation_state_from_path();
                Ok(())
            }
        }
    }

    /// Perform rotation while holding the backend state lock.
    fn rotate_locked(&self, state: &mut FileSinkState) -> io::Result<()> {
        let can_join = std::process::id() == self.creation_pid.load(Ordering::Acquire);

        match &mut state.backend {
            WriterBackend::Async(async_state) => {
                Self::stop_async_writer_locked(async_state, can_join);
            }
            WriterBackend::Sync(sync_state) => {
                if let Some(writer) = sync_state.writer.as_mut() {
                    writer.flush_without_lock()?;
                }
            }
        }

        let rotation_lock_file = Arc::new(Self::open_rotation_lock_file(&self.config.path)?);
        let _rotation_lock = FileLockGuard::exclusive(&rotation_lock_file)?;

        if let Some(mut pending) = self.load_pending_rotation() {
            self.reopen_backend_locked(state)?;

            if pending.needs_compression && pending.rotated_path.exists() {
                if let Err(err) = self.compress_file(&pending.rotated_path) {
                    self.store_pending_rotation(pending);
                    return Err(err);
                }
                pending.needs_compression = false;
            }

            if pending.needs_retention {
                if let Err(err) = self.apply_retention() {
                    self.store_pending_rotation(pending);
                    return Err(err);
                }
                pending.needs_retention = false;
            }

            self.clear_pending_rotation();
            self.advance_rotation_time_boundary(pending.rotation_time);
            return Ok(());
        }

        self.sync_rotation_state_from_path();
        if !self.check_rotation_needed() {
            return self.reopen_backend_locked(state);
        }

        let now = Local::now();
        let rotated_path = self.generate_rotated_path(&now);
        let mut rename_error = None;

        if self.config.path.exists()
            && let Err(err) = fs::rename(&self.config.path, &rotated_path)
            && err.kind() != io::ErrorKind::NotFound
        {
            rename_error = Some(err);
        }

        let reopen_result = self.reopen_backend_locked(state);
        if let Err(err) = reopen_result {
            return Err(rename_error.unwrap_or(err));
        }

        if let Some(err) = rename_error {
            return Err(err);
        }

        let mut pending = PendingRotation {
            rotated_path: rotated_path.clone(),
            rotation_time: now,
            needs_compression: self.config.compression != CompressionFormat::None
                && rotated_path.exists(),
            needs_retention: self.config.retention_count.is_some()
                || self.config.retention_days.is_some(),
        };

        if pending.needs_compression {
            if let Err(err) = self.compress_file(&rotated_path) {
                self.store_pending_rotation(pending);
                return Err(err);
            }
            pending.needs_compression = false;
        }

        if pending.needs_retention {
            if let Err(err) = self.apply_retention() {
                self.store_pending_rotation(pending);
                return Err(err);
            }
            pending.needs_retention = false;
        }

        self.clear_pending_rotation();
        self.advance_rotation_time_boundary(now);
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

    /// Compress a rotated file into the configured archive format.
    fn compress_file(&self, path: &Path) -> io::Result<()> {
        compress_rotated_file(path, self.config.compression).map(drop)
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
        let extension = self
            .config
            .path
            .extension()
            .and_then(|e| e.to_str())
            .unwrap_or("log");

        let current_filename = self
            .config
            .path
            .file_name()
            .and_then(|f| f.to_str())
            .unwrap_or("");
        let lock_filename = Self::format_lock_filename(&self.config.path);

        let mut rotated_files: Vec<(PathBuf, SystemTime)> = fs::read_dir(parent)?
            .filter_map(|e| e.ok())
            .filter_map(|e| {
                let path = e.path();
                let filename = path.file_name()?.to_str()?;
                if path == lock_filename {
                    None
                } else if filename != current_filename
                    && Self::is_generated_rotated_log_filename(filename, stem, extension)
                {
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

    fn is_generated_rotated_log_filename(filename: &str, stem: &str, extension: &str) -> bool {
        let prefix = format!("{stem}.");
        let Some(rest) = filename.strip_prefix(&prefix) else {
            return false;
        };

        // Rotated files keep the log extension and may carry any archive
        // extension logust produces, regardless of the current setting (the
        // compression format may have changed between runs).
        let suffix = format!(".{extension}");
        let rotation_id = CompressionFormat::ALL
            .iter()
            .filter_map(|format| format.extension())
            .find_map(|archive_ext| {
                rest.strip_suffix(archive_ext)
                    .and_then(|value| value.strip_suffix('.'))
                    .and_then(|value| value.strip_suffix(&suffix))
            })
            .or_else(|| rest.strip_suffix(&suffix));
        let Some(rotation_id) = rotation_id else {
            return false;
        };

        let Some((timestamp, pid)) = rotation_id.rsplit_once(".pid") else {
            return false;
        };
        if pid.is_empty() || !pid.chars().all(|c| c.is_ascii_digit()) {
            return false;
        }

        let Some((datetime, micros)) = timestamp.rsplit_once('_') else {
            return false;
        };
        if micros.len() != 6 || !micros.chars().all(|c| c.is_ascii_digit()) {
            return false;
        }

        let bytes = datetime.as_bytes();
        bytes.len() == 19
            && bytes[4] == b'-'
            && bytes[7] == b'-'
            && bytes[10] == b'_'
            && bytes[13] == b'-'
            && bytes[16] == b'-'
            && bytes
                .iter()
                .enumerate()
                .all(|(idx, byte)| matches!(idx, 4 | 7 | 10 | 13 | 16) || byte.is_ascii_digit())
    }
}

impl Drop for FileSinkInner {
    fn drop(&mut self) {
        // If we're in a child process after fork(), inherited backend state belongs
        // to the parent process. The child either lazily rebuilt the backend and
        // updated `creation_pid`, or it never touched the sink and should drop it
        // without flushing/joining inherited resources.
        if std::process::id() != self.creation_pid.load(Ordering::Acquire) {
            let state = self.state.get_mut().unwrap_or_else(|e| e.into_inner());
            match &mut state.backend {
                WriterBackend::Async(async_state) => {
                    async_state.sender.take();
                    async_state.file_identity.store(None);
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

        let state = self.state.get_mut().unwrap_or_else(|e| e.into_inner());
        match &mut state.backend {
            WriterBackend::Async(async_state) => {
                Self::stop_async_writer_locked(async_state, true);
            }
            WriterBackend::Sync(sync_state) => {
                if let Some(writer) = sync_state.writer.as_mut() {
                    let _ = writer.flush_without_lock();
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
    let mut registry = ASYNC_SINK_REGISTRY
        .lock()
        .unwrap_or_else(|e| e.into_inner());
    registry.retain(|weak| weak.upgrade().is_some());
    registry.push(Arc::downgrade(sink));
}

#[cfg(unix)]
extern "C" fn file_sink_atfork_prepare() {
    // Acquisition order: registry lock -> per-sink state lock.
    // atfork prepare must never block; if either lock cannot be obtained,
    // we skip pausing that sink and keep best-effort behavior.
    let Some(mut registry) = try_lock_or_recover(&ASYNC_SINK_REGISTRY) else {
        return;
    };
    registry.retain(|weak| {
        if let Some(sink) = weak.upgrade() {
            sink.pause_for_fork_prepare();
            true
        } else {
            false
        }
    });
}

#[cfg(unix)]
extern "C" fn file_sink_atfork_parent() {}

#[cfg(unix)]
extern "C" fn file_sink_atfork_child() {}

#[cfg(unix)]
fn try_lock_or_recover<T>(mutex: &StdMutex<T>) -> Option<std::sync::MutexGuard<'_, T>> {
    match mutex.try_lock() {
        Ok(guard) => Some(guard),
        Err(TryLockError::Poisoned(err)) => Some(err.into_inner()),
        Err(TryLockError::WouldBlock) => None,
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

/// Compress `path` into `<path>.<ext>` using `format`, then remove `path`.
///
/// Runs only at rotation time. On failure the partial archive is removed and
/// the original file is left in place so the pending rotation can retry.
/// Returns the archive path (or `None` when `format` is `None`).
pub(crate) fn compress_rotated_file(
    path: &Path,
    format: CompressionFormat,
) -> io::Result<Option<PathBuf>> {
    let Some(ext) = format.extension() else {
        return Ok(None);
    };

    let mut archive_name = path.as_os_str().to_os_string();
    archive_name.push(".");
    archive_name.push(ext);
    let archive_path = PathBuf::from(archive_name);

    let input = File::open(path)?;
    let metadata = input.metadata()?;
    let size = metadata.len();
    let mtime: DateTime<Local> = metadata
        .modified()
        .map(DateTime::<Local>::from)
        .unwrap_or_else(|_| Local::now());
    let entry_name = path
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_else(|| "log".to_string());
    let mut reader = io::BufReader::new(input);

    let output = File::create(&archive_path)?;
    let result = write_compressed(output, format, &entry_name, &mut reader, size, mtime);
    if let Err(err) = result {
        let _ = fs::remove_file(&archive_path);
        return Err(err);
    }

    fs::remove_file(path)?;
    Ok(Some(archive_path))
}

fn write_compressed<R: Read>(
    output: File,
    format: CompressionFormat,
    entry_name: &str,
    reader: &mut R,
    size: u64,
    mtime: DateTime<Local>,
) -> io::Result<()> {
    let mtime_secs = u64::try_from(mtime.timestamp()).unwrap_or(0);
    match format {
        CompressionFormat::None => Ok(()),
        CompressionFormat::Gzip => {
            let mut encoder = GzEncoder::new(output, Compression::default());
            copy_exact(reader, &mut encoder, size)?;
            encoder.finish().map(drop)
        }
        CompressionFormat::Bzip2 => {
            let mut encoder = BzEncoder::new(output, bzip2::Compression::default());
            copy_exact(reader, &mut encoder, size)?;
            encoder.finish().map(drop)
        }
        CompressionFormat::Tar => {
            let mut writer = BufWriter::new(output);
            write_tar_archive(&mut writer, entry_name, reader, size, mtime_secs)?;
            finish_buffered(writer)
        }
        CompressionFormat::TarGz => {
            let mut encoder = GzEncoder::new(BufWriter::new(output), Compression::default());
            write_tar_archive(&mut encoder, entry_name, reader, size, mtime_secs)?;
            finish_buffered(encoder.finish()?)
        }
        CompressionFormat::TarBz2 => {
            let mut encoder = BzEncoder::new(BufWriter::new(output), bzip2::Compression::default());
            write_tar_archive(&mut encoder, entry_name, reader, size, mtime_secs)?;
            finish_buffered(encoder.finish()?)
        }
        CompressionFormat::Zip => {
            let mut writer = BufWriter::new(output);
            write_zip_archive(&mut writer, entry_name, reader, size, mtime, false)?;
            finish_buffered(writer)
        }
    }
}

fn finish_buffered(writer: BufWriter<File>) -> io::Result<()> {
    writer
        .into_inner()
        .map(drop)
        .map_err(|err| err.into_error())
}

/// Copy exactly `size` bytes; a short read means the file changed under us.
fn copy_exact<R: Read, W: Write>(reader: &mut R, writer: &mut W, size: u64) -> io::Result<()> {
    let copied = io::copy(&mut reader.by_ref().take(size), writer)?;
    if copied != size {
        return Err(io::Error::new(
            io::ErrorKind::UnexpectedEof,
            format!("rotated file shrank during compression ({copied} of {size} bytes)"),
        ));
    }
    Ok(())
}

const TAR_BLOCK: usize = 512;
/// Archives are padded to 20 blocks, matching GNU tar and Python's tarfile.
const TAR_RECORD: usize = TAR_BLOCK * 20;

/// Write a single-entry GNU tar archive (long names via `././@LongLink`,
/// sizes >= 8 GiB via base-256).
fn write_tar_archive<R: Read, W: Write>(
    out: &mut W,
    name: &str,
    reader: &mut R,
    size: u64,
    mtime: u64,
) -> io::Result<()> {
    let name_bytes = name.as_bytes();
    let mut written: u64 = 0;

    if name_bytes.len() > 100 {
        let mut long_name = name_bytes.to_vec();
        long_name.push(0);
        out.write_all(&tar_header(
            b"././@LongLink",
            long_name.len() as u64,
            0,
            b'L',
        ))?;
        out.write_all(&long_name)?;
        let padding = tar_padding(long_name.len() as u64);
        out.write_all(&[0u8; TAR_BLOCK][..padding])?;
        written += (TAR_BLOCK + long_name.len() + padding) as u64;
    }

    let short_name = &name_bytes[..name_bytes.len().min(100)];
    out.write_all(&tar_header(short_name, size, mtime, b'0'))?;
    copy_exact(reader, out, size)?;
    let padding = tar_padding(size);
    out.write_all(&[0u8; TAR_BLOCK][..padding])?;
    written += TAR_BLOCK as u64 + size + padding as u64;

    // End-of-archive marker (two zero blocks), then pad to a full record.
    out.write_all(&[0u8; TAR_BLOCK * 2])?;
    written += (TAR_BLOCK * 2) as u64;
    let record = TAR_RECORD as u64;
    let record_padding = ((record - written % record) % record) as usize;
    out.write_all(&vec![0u8; record_padding])?;
    Ok(())
}

fn tar_padding(len: u64) -> usize {
    let rem = (len % TAR_BLOCK as u64) as usize;
    (TAR_BLOCK - rem) % TAR_BLOCK
}

fn tar_header(name: &[u8], size: u64, mtime: u64, typeflag: u8) -> [u8; TAR_BLOCK] {
    let mut header = [0u8; TAR_BLOCK];
    header[..name.len()].copy_from_slice(name);
    tar_octal(&mut header[100..108], 0o644); // mode
    tar_octal(&mut header[108..116], 0); // uid
    tar_octal(&mut header[116..124], 0); // gid
    tar_numeric(&mut header[124..136], size);
    tar_numeric(&mut header[136..148], mtime);
    header[148..156].fill(b' '); // checksum placeholder
    header[156] = typeflag;
    header[257..265].copy_from_slice(b"ustar  \0"); // GNU magic + version

    let checksum: u32 = header.iter().map(|&b| u32::from(b)).sum();
    let checksum = format!("{checksum:06o}\0 ");
    header[148..156].copy_from_slice(checksum.as_bytes());
    header
}

/// Zero-padded octal digits followed by NUL.
fn tar_octal(field: &mut [u8], value: u64) {
    let digits = field.len() - 1;
    let text = format!("{value:0digits$o}");
    field[..digits].copy_from_slice(text.as_bytes());
    field[digits] = 0;
}

/// Octal when it fits, otherwise GNU base-256 (big-endian with 0x80 marker).
fn tar_numeric(field: &mut [u8], value: u64) {
    let digits = field.len() - 1;
    if value < 1u64 << (3 * digits as u32) {
        tar_octal(field, value);
    } else {
        field.fill(0);
        field[0] = 0x80;
        let bytes = value.to_be_bytes();
        let len = field.len();
        field[len - bytes.len()..].copy_from_slice(&bytes);
    }
}

/// Above this size the entry is written with ZIP64 fields. Kept below
/// `u32::MAX` so deflate overhead on incompressible data can't overflow.
const ZIP64_THRESHOLD: u64 = 0xFFF0_0000;

/// Write a single-entry deflated ZIP archive. Sizes and CRC are patched into
/// the local header after streaming, so no data descriptor is needed.
fn write_zip_archive<R: Read, W: Write + Seek>(
    out: &mut W,
    name: &str,
    reader: &mut R,
    size: u64,
    mtime: DateTime<Local>,
    force_zip64: bool,
) -> io::Result<()> {
    use chrono::Datelike;
    use flate2::write::DeflateEncoder;
    use io::SeekFrom;

    let zip64 = force_zip64 || size >= ZIP64_THRESHOLD;
    let name_bytes = name.as_bytes();
    let name_len = u16::try_from(name_bytes.len())
        .map_err(|_| io::Error::new(io::ErrorKind::InvalidInput, "file name too long for zip"))?;
    let flags: u16 = if name.is_ascii() { 0 } else { 0x0800 }; // UTF-8 names
    let version_needed: u16 = if zip64 { 45 } else { 20 };
    let version_made_by: u16 = (3 << 8) | version_needed; // UNIX
    let extra_len: u16 = if zip64 { 20 } else { 0 };
    let (dos_time, dos_date) = if mtime.year() < 1980 {
        (0, (1 << 5) | 1)
    } else {
        (
            ((mtime.hour() as u16) << 11)
                | ((mtime.minute() as u16) << 5)
                | (mtime.second() as u16 / 2),
            (((mtime.year() - 1980).min(127) as u16) << 9)
                | ((mtime.month() as u16) << 5)
                | mtime.day() as u16,
        )
    };
    let size32 = |value: u64| if zip64 { u32::MAX } else { value as u32 };

    let start = out.stream_position()?;
    // Local file header; CRC and sizes are patched below.
    out.write_all(&0x0403_4b50u32.to_le_bytes())?;
    out.write_all(&version_needed.to_le_bytes())?;
    out.write_all(&flags.to_le_bytes())?;
    out.write_all(&8u16.to_le_bytes())?; // deflate
    out.write_all(&dos_time.to_le_bytes())?;
    out.write_all(&dos_date.to_le_bytes())?;
    out.write_all(&[0u8; 12])?; // crc, compressed size, uncompressed size
    out.write_all(&name_len.to_le_bytes())?;
    out.write_all(&extra_len.to_le_bytes())?;
    out.write_all(name_bytes)?;
    if zip64 {
        out.write_all(&1u16.to_le_bytes())?;
        out.write_all(&16u16.to_le_bytes())?;
        out.write_all(&[0u8; 16])?;
    }

    let data_start = out.stream_position()?;
    let mut crc = flate2::Crc::new();
    let mut remaining = size;
    {
        let mut encoder = DeflateEncoder::new(&mut *out, Compression::default());
        let mut buf = vec![0u8; 64 * 1024];
        while remaining > 0 {
            let want = buf
                .len()
                .min(usize::try_from(remaining).unwrap_or(usize::MAX));
            let read = reader.read(&mut buf[..want])?;
            if read == 0 {
                return Err(io::Error::new(
                    io::ErrorKind::UnexpectedEof,
                    "rotated file shrank during compression",
                ));
            }
            crc.update(&buf[..read]);
            encoder.write_all(&buf[..read])?;
            remaining -= read as u64;
        }
        encoder.finish()?;
    }
    let data_end = out.stream_position()?;
    let compressed = data_end - data_start;
    if !zip64 && (compressed > u64::from(u32::MAX) || data_end > u64::from(u32::MAX)) {
        return Err(io::Error::other("zip entry exceeded 4 GiB without ZIP64"));
    }
    let crc = crc.sum();

    out.seek(SeekFrom::Start(start + 14))?;
    out.write_all(&crc.to_le_bytes())?;
    out.write_all(&size32(compressed).to_le_bytes())?;
    out.write_all(&size32(size).to_le_bytes())?;
    if zip64 {
        out.seek(SeekFrom::Start(start + 30 + u64::from(name_len) + 4))?;
        out.write_all(&size.to_le_bytes())?;
        out.write_all(&compressed.to_le_bytes())?;
    }
    out.seek(SeekFrom::Start(data_end))?;

    // Central directory
    let cd_start = data_end;
    out.write_all(&0x0201_4b50u32.to_le_bytes())?;
    out.write_all(&version_made_by.to_le_bytes())?;
    out.write_all(&version_needed.to_le_bytes())?;
    out.write_all(&flags.to_le_bytes())?;
    out.write_all(&8u16.to_le_bytes())?;
    out.write_all(&dos_time.to_le_bytes())?;
    out.write_all(&dos_date.to_le_bytes())?;
    out.write_all(&crc.to_le_bytes())?;
    out.write_all(&size32(compressed).to_le_bytes())?;
    out.write_all(&size32(size).to_le_bytes())?;
    out.write_all(&name_len.to_le_bytes())?;
    out.write_all(&extra_len.to_le_bytes())?;
    out.write_all(&0u16.to_le_bytes())?; // comment length
    out.write_all(&0u16.to_le_bytes())?; // disk number start
    out.write_all(&0u16.to_le_bytes())?; // internal attributes
    out.write_all(&(0o100644u32 << 16).to_le_bytes())?; // external attributes
    out.write_all(&u32::try_from(start).unwrap_or(u32::MAX).to_le_bytes())?;
    out.write_all(name_bytes)?;
    if zip64 {
        out.write_all(&1u16.to_le_bytes())?;
        out.write_all(&16u16.to_le_bytes())?;
        out.write_all(&size.to_le_bytes())?;
        out.write_all(&compressed.to_le_bytes())?;
    }
    let cd_end = out.stream_position()?;
    let cd_size = cd_end - cd_start;

    if zip64 {
        // ZIP64 end of central directory record + locator
        out.write_all(&0x0606_4b50u32.to_le_bytes())?;
        out.write_all(&44u64.to_le_bytes())?;
        out.write_all(&version_made_by.to_le_bytes())?;
        out.write_all(&version_needed.to_le_bytes())?;
        out.write_all(&0u32.to_le_bytes())?;
        out.write_all(&0u32.to_le_bytes())?;
        out.write_all(&1u64.to_le_bytes())?;
        out.write_all(&1u64.to_le_bytes())?;
        out.write_all(&cd_size.to_le_bytes())?;
        out.write_all(&cd_start.to_le_bytes())?;
        out.write_all(&0x0706_4b50u32.to_le_bytes())?;
        out.write_all(&0u32.to_le_bytes())?;
        out.write_all(&cd_end.to_le_bytes())?;
        out.write_all(&1u32.to_le_bytes())?;
    }

    // End of central directory record
    out.write_all(&0x0605_4b50u32.to_le_bytes())?;
    out.write_all(&0u16.to_le_bytes())?;
    out.write_all(&0u16.to_le_bytes())?;
    out.write_all(&1u16.to_le_bytes())?;
    out.write_all(&1u16.to_le_bytes())?;
    out.write_all(&(cd_size as u32).to_le_bytes())?;
    out.write_all(&size32(cd_start).to_le_bytes())?;
    out.write_all(&0u16.to_le_bytes())?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn unique_temp_path(name: &str) -> PathBuf {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        std::env::temp_dir().join(format!("logust-{name}-{}-{nanos}", std::process::id()))
    }

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

    #[test]
    fn test_rotated_log_filename_matching_is_strict() {
        assert!(FileSinkInner::is_generated_rotated_log_filename(
            "app.2000-01-01_00-00-00_000000.pid0.log",
            "app",
            "log"
        ));
        assert!(FileSinkInner::is_generated_rotated_log_filename(
            "app.2000-01-01_00-00-00_000000.pid123.log.gz",
            "app",
            "log"
        ));
        for archive in ["bz2", "zip", "tar", "tar.gz", "tar.bz2"] {
            assert!(
                FileSinkInner::is_generated_rotated_log_filename(
                    &format!("app.2000-01-01_00-00-00_000000.pid123.log.{archive}"),
                    "app",
                    "log"
                ),
                "{archive} archives must be matched by retention"
            );
        }
        assert!(!FileSinkInner::is_generated_rotated_log_filename(
            "app.2000-01-01_00-00-00_000000.pid123.log.7z",
            "app",
            "log"
        ));
        assert!(!FileSinkInner::is_generated_rotated_log_filename(
            "app.2000-01-01_00-00-00_000000.pid123.tar.gz",
            "app",
            "log"
        ));
        assert!(!FileSinkInner::is_generated_rotated_log_filename(
            "app.keep", "app", "log"
        ));
        assert!(!FileSinkInner::is_generated_rotated_log_filename(
            "app.2000-01-01_00-00-00_000000.pid0.log.bak",
            "app",
            "log"
        ));
        assert!(!FileSinkInner::is_generated_rotated_log_filename(
            "application.2000-01-01_00-00-00_000000.pid0.log",
            "app",
            "log"
        ));
    }

    #[test]
    fn test_retention_preserves_same_stem_unrelated_files() {
        let dir = unique_temp_path("retention-preserve-unrelated");
        fs::create_dir_all(&dir).unwrap();

        let path = dir.join("app.log");
        let unrelated = dir.join("app.keep");
        let unrelated_backup = dir.join("app.2000-01-01_00-00-00_000000.pid0.log.bak");
        let stale_rotated = dir.join("app.2000-01-01_00-00-00_000000.pid0.log");
        fs::write(&unrelated, "keep").unwrap();
        fs::write(&unrelated_backup, "keep").unwrap();
        fs::write(&stale_rotated, "stale").unwrap();

        let sink = FileSink::new(FileSinkConfig {
            path: path.clone(),
            max_size: Some(1),
            retention_count: Some(0),
            ..FileSinkConfig::default()
        })
        .unwrap();

        sink.write("first").unwrap();
        sink.write("second").unwrap();
        sink.flush().unwrap();

        assert!(unrelated.exists(), "retention deleted a same-stem sibling");
        assert!(
            unrelated_backup.exists(),
            "retention deleted a non-generated backup"
        );
        assert!(
            !stale_rotated.exists(),
            "retention should still delete generated rotated logs"
        );

        drop(sink);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn test_pending_rotation_forces_retry_even_before_boundary() {
        let path = unique_temp_path("pending-rotation").join("app.log");
        let sink = FileSink::new(FileSinkConfig {
            path: path.clone(),
            rotation: Rotation::Hourly,
            ..FileSinkConfig::default()
        })
        .unwrap();

        let future_boundary = Local::now() + chrono::Duration::hours(1);
        sink.inner
            .next_rotation_boundary
            .store(future_boundary.timestamp_millis(), Ordering::Relaxed);
        sink.inner.store_pending_rotation(PendingRotation {
            rotated_path: path.with_extension("rotated.log"),
            rotation_time: Local::now(),
            needs_compression: false,
            needs_retention: true,
        });

        assert!(sink.inner.check_rotation_needed());

        sink.inner.clear_pending_rotation();
        let _ = fs::remove_file(&path);
        if let Some(parent) = path.parent() {
            let _ = fs::remove_dir(parent);
        }
    }

    #[test]
    fn test_async_writer_state_open_error_surfaces_immediately() {
        let path = unique_temp_path("async-open-error");
        fs::create_dir_all(&path).unwrap();

        let err = match FileSinkInner::create_async_writer_state(&path, false) {
            Ok(_) => panic!("async writer state unexpectedly opened a directory path"),
            Err(err) => err,
        };
        assert!(matches!(
            err.kind(),
            io::ErrorKind::IsADirectory | io::ErrorKind::PermissionDenied
        ));

        fs::remove_dir(&path).unwrap();
    }

    fn write_test_log(dir: &Path, name: &str, contents: &[u8]) -> PathBuf {
        fs::create_dir_all(dir).unwrap();
        let path = dir.join(name);
        fs::write(&path, contents).unwrap();
        path
    }

    fn sample_log_bytes() -> Vec<u8> {
        (0..2000)
            .map(|i| format!("line {i} with some text\n"))
            .collect::<String>()
            .into_bytes()
    }

    fn read_u16(buf: &[u8], at: usize) -> u16 {
        u16::from_le_bytes(buf[at..at + 2].try_into().unwrap())
    }

    fn read_u32(buf: &[u8], at: usize) -> u32 {
        u32::from_le_bytes(buf[at..at + 4].try_into().unwrap())
    }

    fn read_u64(buf: &[u8], at: usize) -> u64 {
        u64::from_le_bytes(buf[at..at + 8].try_into().unwrap())
    }

    /// Minimal single-entry tar reader: (name, data) after validating checksums.
    fn read_tar(archive: &[u8]) -> (String, Vec<u8>) {
        assert_eq!(archive.len() % TAR_RECORD, 0, "tar must be record aligned");
        let mut offset = 0;
        let mut long_name = None;
        loop {
            let header = &archive[offset..offset + TAR_BLOCK];
            let stored =
                u32::from_str_radix(std::str::from_utf8(&header[148..154]).unwrap().trim(), 8)
                    .unwrap();
            let mut copy = header.to_vec();
            copy[148..156].fill(b' ');
            assert_eq!(stored, copy.iter().map(|&b| u32::from(b)).sum::<u32>());
            let size = if header[124] & 0x80 != 0 {
                u64::from_be_bytes(header[128..136].try_into().unwrap())
            } else {
                u64::from_str_radix(std::str::from_utf8(&header[124..135]).unwrap(), 8).unwrap()
            } as usize;
            let data = &archive[offset + TAR_BLOCK..offset + TAR_BLOCK + size];
            offset += TAR_BLOCK + size + tar_padding(size as u64);
            if header[156] == b'L' {
                long_name = Some(String::from_utf8(data[..data.len() - 1].to_vec()).unwrap());
                continue;
            }
            let name = long_name.take().unwrap_or_else(|| {
                let end = header[..100].iter().position(|&b| b == 0).unwrap_or(100);
                String::from_utf8(header[..end].to_vec()).unwrap()
            });
            assert!(
                archive[offset..offset + 2 * TAR_BLOCK]
                    .iter()
                    .all(|&b| b == 0)
            );
            return (name, data.to_vec());
        }
    }

    /// Minimal single-entry zip reader: (name, data) after validating the CRC.
    fn read_zip(archive: &[u8]) -> (String, Vec<u8>) {
        use flate2::read::DeflateDecoder;

        let eocd = archive.len() - 22;
        assert_eq!(read_u32(archive, eocd), 0x0605_4b50);
        assert_eq!(read_u16(archive, eocd + 10), 1, "one entry");
        let mut cd = read_u32(archive, eocd + 16) as usize;
        if cd == u32::MAX as usize {
            let locator = eocd - 20;
            assert_eq!(read_u32(archive, locator), 0x0706_4b50);
            let record = read_u64(archive, locator + 8) as usize;
            assert_eq!(read_u32(archive, record), 0x0606_4b50);
            cd = read_u64(archive, record + 48) as usize;
        }
        assert_eq!(read_u32(archive, cd), 0x0201_4b50);
        let crc = read_u32(archive, cd + 16);
        let name_len = read_u16(archive, cd + 28) as usize;
        let extra_len = read_u16(archive, cd + 30) as usize;
        let name = String::from_utf8(archive[cd + 46..cd + 46 + name_len].to_vec()).unwrap();
        let mut compressed = read_u32(archive, cd + 20) as u64;
        let mut size = read_u32(archive, cd + 24) as u64;
        if extra_len > 0 {
            let extra = cd + 46 + name_len;
            assert_eq!(read_u16(archive, extra), 1, "zip64 extra id");
            size = read_u64(archive, extra + 4);
            compressed = read_u64(archive, extra + 12);
        }

        assert_eq!(read_u32(archive, 0), 0x0403_4b50);
        assert_eq!(read_u32(archive, 14), crc, "local header crc patched");
        let data_start = 30 + read_u16(archive, 26) as usize + read_u16(archive, 28) as usize;
        let mut data = Vec::new();
        DeflateDecoder::new(&archive[data_start..data_start + compressed as usize])
            .read_to_end(&mut data)
            .unwrap();
        assert_eq!(data.len() as u64, size);
        let mut actual_crc = flate2::Crc::new();
        actual_crc.update(&data);
        assert_eq!(actual_crc.sum(), crc);
        (name, data)
    }

    #[test]
    fn test_parse_compression() {
        assert_eq!(parse_compression("gz"), Ok(CompressionFormat::Gzip));
        assert_eq!(parse_compression(".zip"), Ok(CompressionFormat::Zip));
        assert_eq!(parse_compression(" TAR.GZ "), Ok(CompressionFormat::TarGz));
        assert_eq!(parse_compression("bz2"), Ok(CompressionFormat::Bzip2));
        assert_eq!(parse_compression("tar"), Ok(CompressionFormat::Tar));
        assert_eq!(parse_compression("tar.bz2"), Ok(CompressionFormat::TarBz2));
        for unsupported in ["xz", "lzma", "tar.xz"] {
            let err = parse_compression(unsupported).unwrap_err();
            assert!(err.contains("not supported"), "{err}");
        }
        assert!(parse_compression("rar").unwrap_err().contains("Invalid"));
    }

    #[test]
    fn test_compress_rotated_file_all_formats_round_trip() {
        use flate2::read::GzDecoder;

        let dir = unique_temp_path("compress-formats");
        let contents = sample_log_bytes();

        for format in CompressionFormat::ALL {
            let ext = format.extension().unwrap();
            let name = format!("app.{}.log", ext.replace('.', "-"));
            let path = write_test_log(&dir, &name, &contents);
            let archive_path = compress_rotated_file(&path, format).unwrap().unwrap();

            assert!(!path.exists(), "{format:?}: source must be removed");
            assert_eq!(
                archive_path.file_name().unwrap().to_str().unwrap(),
                format!("{name}.{ext}")
            );

            let raw = fs::read(&archive_path).unwrap();
            let mut decoded = Vec::new();
            match format {
                CompressionFormat::Gzip | CompressionFormat::TarGz => {
                    GzDecoder::new(raw.as_slice())
                        .read_to_end(&mut decoded)
                        .unwrap();
                }
                CompressionFormat::Bzip2 | CompressionFormat::TarBz2 => {
                    bzip2::read::BzDecoder::new(raw.as_slice())
                        .read_to_end(&mut decoded)
                        .unwrap();
                }
                _ => decoded = raw,
            }

            let (entry, data) = match format {
                CompressionFormat::Gzip | CompressionFormat::Bzip2 => (name.clone(), decoded),
                CompressionFormat::Tar | CompressionFormat::TarGz | CompressionFormat::TarBz2 => {
                    read_tar(&decoded)
                }
                CompressionFormat::Zip => read_zip(&decoded),
                CompressionFormat::None => unreachable!(),
            };
            assert_eq!(entry, name, "{format:?}");
            assert_eq!(data, contents, "{format:?}");
        }

        assert_eq!(
            compress_rotated_file(&dir.join("missing.log"), CompressionFormat::None).unwrap(),
            None
        );
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn test_zip64_layout_round_trips() {
        let contents = sample_log_bytes();
        let mut archive = io::Cursor::new(Vec::new());
        write_zip_archive(
            &mut archive,
            "app.log",
            &mut contents.as_slice(),
            contents.len() as u64,
            Local::now(),
            true,
        )
        .unwrap();
        let archive = archive.into_inner();
        assert_eq!(read_u32(&archive, archive.len() - 22 + 16), u32::MAX);
        let (name, data) = read_zip(&archive);
        assert_eq!(name, "app.log");
        assert_eq!(data, contents);
    }

    #[test]
    fn test_tar_long_name_and_base256_size() {
        let long_name = format!("{}.log", "n".repeat(150));
        let mut archive = Vec::new();
        write_tar_archive(&mut archive, &long_name, &mut &b"hello\n"[..], 6, 0).unwrap();
        let (name, data) = read_tar(&archive);
        assert_eq!(name, long_name);
        assert_eq!(data, b"hello\n");

        let mut field = [0u8; 12];
        tar_numeric(&mut field, 8u64.pow(11) - 1);
        assert_eq!(&field, b"77777777777\0");
        tar_numeric(&mut field, 8u64.pow(11));
        assert_eq!(field[0], 0x80);
        assert_eq!(
            u64::from_be_bytes(field[4..].try_into().unwrap()),
            8u64.pow(11)
        );
    }

    #[test]
    fn test_compress_failure_keeps_source() {
        let dir = unique_temp_path("compress-failure");
        let path = write_test_log(&dir, "app.log", b"data\n");
        // A directory squatting on the archive path makes File::create fail.
        fs::create_dir_all(dir.join("app.log.zip")).unwrap();
        assert!(compress_rotated_file(&path, CompressionFormat::Zip).is_err());
        assert!(path.exists(), "source must survive a failed compression");
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn test_rotation_with_zip_compression_and_retention() {
        let dir = unique_temp_path("rotation-zip-retention");
        let path = dir.join("app.log");
        let sink = FileSink::new(FileSinkConfig {
            path: path.clone(),
            max_size: Some(1),
            retention_count: Some(2),
            compression: CompressionFormat::Zip,
            ..FileSinkConfig::default()
        })
        .unwrap();

        for i in 0..6 {
            sink.write(&format!("message {i}")).unwrap();
        }
        sink.flush().unwrap();

        let archives: Vec<_> = fs::read_dir(&dir)
            .unwrap()
            .filter_map(|e| e.ok())
            .map(|e| e.file_name().to_string_lossy().into_owned())
            .filter(|name| name.ends_with(".log.zip"))
            .collect();
        assert_eq!(
            archives.len(),
            2,
            "retention keeps 2 archives: {archives:?}"
        );
        for name in &archives {
            let (_, data) = read_zip(&fs::read(dir.join(name)).unwrap());
            assert!(data.starts_with(b"message "));
        }

        drop(sink);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn test_delay_defers_file_creation_until_first_write() {
        for enqueue in [false, true] {
            let dir = unique_temp_path(&format!("delay-{enqueue}"));
            let path = dir.join("nested").join("app.log");
            let sink = FileSink::new(FileSinkConfig {
                path: path.clone(),
                delay: true,
                enqueue,
                ..FileSinkConfig::default()
            })
            .unwrap();

            assert!(!dir.exists(), "delay must not create directories or files");
            sink.flush().unwrap();
            assert!(!path.exists(), "flush must not open a delayed sink");

            sink.write("first").unwrap();
            sink.flush().unwrap();
            assert_eq!(fs::read_to_string(&path).unwrap(), "first\n");

            drop(sink);
            let _ = fs::remove_dir_all(&dir);
        }
    }

    #[test]
    fn test_truncate_mode_replaces_existing_content() {
        for (delay, enqueue) in [(false, false), (true, false), (false, true), (true, true)] {
            let dir = unique_temp_path(&format!("truncate-{delay}-{enqueue}"));
            let path = write_test_log(&dir, "app.log", b"old content\n");
            let sink = FileSink::new(FileSinkConfig {
                path: path.clone(),
                truncate: true,
                delay,
                enqueue,
                ..FileSinkConfig::default()
            })
            .unwrap();

            let expected_before = if delay { "old content\n" } else { "" };
            assert_eq!(fs::read_to_string(&path).unwrap(), expected_before);

            sink.write("new").unwrap();
            sink.write("more").unwrap();
            sink.flush().unwrap();
            assert_eq!(fs::read_to_string(&path).unwrap(), "new\nmore\n");

            drop(sink);
            let _ = fs::remove_dir_all(&dir);
        }
    }

    #[test]
    fn test_append_mode_keeps_existing_content() {
        let dir = unique_temp_path("append");
        let path = write_test_log(&dir, "app.log", b"old\n");
        let sink = FileSink::new(FileSinkConfig {
            path: path.clone(),
            ..FileSinkConfig::default()
        })
        .unwrap();
        sink.write("new").unwrap();
        sink.flush().unwrap();
        assert_eq!(fs::read_to_string(&path).unwrap(), "old\nnew\n");
        drop(sink);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn test_existing_file_from_previous_period_rotates_on_first_write() {
        let dir = unique_temp_path("stale-file-rotation");
        fs::create_dir_all(&dir).unwrap();
        let path = dir.join("app.log");
        fs::write(&path, "old\n").unwrap();
        let two_days_ago = SystemTime::now() - Duration::from_secs(2 * 24 * 60 * 60);
        OpenOptions::new()
            .write(true)
            .open(&path)
            .unwrap()
            .set_modified(two_days_ago)
            .unwrap();

        let sink = FileSink::new(FileSinkConfig {
            path: path.clone(),
            rotation: Rotation::Daily,
            ..FileSinkConfig::default()
        })
        .unwrap();
        assert!(
            sink.inner.check_rotation_needed(),
            "a file last written two days ago should rotate on the first write"
        );

        sink.write("new").unwrap();
        sink.flush().unwrap();

        assert_eq!(fs::read_to_string(&path).unwrap(), "new\n");
        let rotated: Vec<PathBuf> = fs::read_dir(&dir)
            .unwrap()
            .map(|e| e.unwrap().path())
            .filter(|p| p != &path && p.extension().is_some_and(|ext| ext == "log"))
            .collect();
        assert_eq!(
            rotated.len(),
            1,
            "expected one rotated file, got {rotated:?}"
        );
        assert_eq!(fs::read_to_string(&rotated[0]).unwrap(), "old\n");
        assert!(
            sink.inner.next_rotation_boundary.load(Ordering::Relaxed)
                > chrono::Utc::now().timestamp_millis(),
            "the boundary after rotation must be in the future"
        );

        drop(sink);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn test_fresh_sink_never_stores_zero_boundary_for_time_rotation() {
        for rotation in [Rotation::Daily, Rotation::Hourly] {
            let path = unique_temp_path("fresh-boundary").join("app.log");
            let sink = FileSink::new(FileSinkConfig {
                path: path.clone(),
                rotation,
                ..FileSinkConfig::default()
            })
            .unwrap();
            let boundary = sink.inner.next_rotation_boundary.load(Ordering::Relaxed);
            assert!(
                boundary > chrono::Utc::now().timestamp_millis(),
                "{rotation:?}"
            );
            drop(sink);
            let _ = fs::remove_file(&path);
            if let Some(parent) = path.parent() {
                let _ = fs::remove_dir(parent);
            }
        }
    }

    /// DST handling of `calculate_next_rotation_boundary`. `TZ` is
    /// process-wide, so these run under the crate's TZ lock; Windows chrono
    /// ignores `TZ`, hence unix only. POSIX rule strings keep the tests
    /// independent of the installed tzdata.
    #[cfg(unix)]
    mod rotation_boundary_dst {
        use chrono::{DateTime, Datelike, Utc};

        use super::*;
        use crate::clock::tz_test::with_tz;

        /// Eastern US: spring forward 02:00 -> 03:00 (second Sunday of March),
        /// fall back 02:00 -> 01:00 (first Sunday of November).
        const US_EASTERN: &str = "EST5EDT,M3.2.0,M11.1.0";
        /// Chile: DST starts at 24:00 on the first Saturday of September
        /// (00:00 -> 01:00, so midnight does not exist) and ends at 24:00 on
        /// the first Saturday of April (00:00 -> 23:00).
        const CHILE: &str = "CLT4CLST,M9.1.6/24,M4.1.6/24";
        /// Cuba: fall back at 01:00 -> 00:00 on the first Sunday of November,
        /// so midnight happens twice.
        const CUBA: &str = "CST5CDT,M3.2.0/0,M11.1.0/1";

        fn utc(s: &str) -> DateTime<Utc> {
            DateTime::parse_from_rfc3339(s).unwrap().with_timezone(&Utc)
        }

        fn boundary_after(rotation: Rotation, from: &str) -> DateTime<Utc> {
            let from = utc(from).with_timezone(&Local);
            let boundary = FileSinkInner::calculate_next_rotation_boundary(&rotation, &from)
                .expect("time-based rotation always has a boundary");
            assert!(boundary > from, "boundary {boundary} must follow {from}");
            boundary.with_timezone(&Utc)
        }

        #[test]
        fn never_has_no_boundary() {
            let now = Local::now();
            assert!(
                FileSinkInner::calculate_next_rotation_boundary(&Rotation::Never, &now).is_none()
            );
        }

        #[test]
        fn plain_hours_and_days() {
            with_tz("UTC", || {
                assert_eq!(
                    boundary_after(Rotation::Hourly, "2024-06-15T10:17:42.5Z"),
                    utc("2024-06-15T11:00:00Z")
                );
                assert_eq!(
                    boundary_after(Rotation::Hourly, "2024-06-15T23:59:59.999Z"),
                    utc("2024-06-16T00:00:00Z")
                );
                assert_eq!(
                    boundary_after(Rotation::Daily, "2024-06-15T10:17:42Z"),
                    utc("2024-06-16T00:00:00Z")
                );
                // Exactly on a boundary: the next one, never the same instant
                assert_eq!(
                    boundary_after(Rotation::Hourly, "2024-06-15T10:00:00Z"),
                    utc("2024-06-15T11:00:00Z")
                );
            });
            with_tz(US_EASTERN, || {
                // 2024-06-15 is EDT (UTC-4): 10:17 local -> 11:00 local
                assert_eq!(
                    boundary_after(Rotation::Hourly, "2024-06-15T14:17:42Z"),
                    utc("2024-06-15T15:00:00Z")
                );
                // local midnight 2024-06-16 EDT
                assert_eq!(
                    boundary_after(Rotation::Daily, "2024-06-15T14:17:42Z"),
                    utc("2024-06-16T04:00:00Z")
                );
            });
        }

        #[test]
        fn hourly_spring_forward_gap_rotates_at_the_transition() {
            with_tz(US_EASTERN, || {
                // 2024-03-10 01:30 EST; 02:00 local does not exist, the clock
                // jumps to 03:00 EDT at 07:00Z.
                let transition = utc("2024-03-10T07:00:00Z");
                assert_eq!(
                    boundary_after(Rotation::Hourly, "2024-03-10T06:30:00Z"),
                    transition
                );
                // After rotating at the transition, the next boundary is
                // 04:00 EDT: one rotation per wall-clock hour, no drift.
                assert_eq!(
                    boundary_after(Rotation::Hourly, "2024-03-10T07:00:00.001Z"),
                    utc("2024-03-10T08:00:00Z")
                );
            });
        }

        #[test]
        fn hourly_fall_back_rotates_once_for_the_repeated_hour() {
            with_tz(US_EASTERN, || {
                // 2024-11-03 00:30 EDT; 01:00 local happens twice
                // (05:00Z as EDT, 06:00Z as EST). Rotate at the first.
                assert_eq!(
                    boundary_after(Rotation::Hourly, "2024-11-03T04:30:00Z"),
                    utc("2024-11-03T05:00:00Z")
                );
                // From the rotation at 01:00 EDT the next boundary is 02:00
                // EST (07:00Z): the second 01:00 does not rotate again.
                assert_eq!(
                    boundary_after(Rotation::Hourly, "2024-11-03T05:00:00.001Z"),
                    utc("2024-11-03T07:00:00Z")
                );
                // Opened during the second 01:00 (01:30 EST): 02:00 EST.
                assert_eq!(
                    boundary_after(Rotation::Hourly, "2024-11-03T06:30:00Z"),
                    utc("2024-11-03T07:00:00Z")
                );
            });
        }

        #[test]
        fn daily_midnight_gap_rotates_at_the_transition() {
            with_tz(CHILE, || {
                // Saturday 2024-09-07 23:30 CLT (-04). Midnight does not
                // exist: 24:00 -04 becomes 01:00 -03 at 04:00Z.
                let transition = utc("2024-09-08T04:00:00Z");
                assert_eq!(
                    boundary_after(Rotation::Daily, "2024-09-08T03:30:00Z"),
                    transition
                );
                // Next boundary: midnight 2024-09-09 CLST (-03)
                assert_eq!(
                    boundary_after(Rotation::Daily, "2024-09-08T04:00:00.001Z"),
                    utc("2024-09-09T03:00:00Z")
                );
            });
        }

        #[test]
        fn daily_ambiguous_midnight_rotates_once() {
            with_tz(CUBA, || {
                // Saturday 2024-11-02 23:30 CDT (-04). Sunday 00:00 happens
                // twice: 04:00Z (CDT) and 05:00Z (CST). Rotate at the first.
                assert_eq!(
                    boundary_after(Rotation::Daily, "2024-11-03T03:30:00Z"),
                    utc("2024-11-03T04:00:00Z")
                );
                // Next boundary: Monday 00:00 CST (05:00Z), one rotation per day
                assert_eq!(
                    boundary_after(Rotation::Daily, "2024-11-03T04:00:00.001Z"),
                    utc("2024-11-04T05:00:00Z")
                );
                // Hourly across the same fall-back (01:00 CDT -> 00:00 CST at
                // 05:00Z): from 00:30 CDT the clock never shows 01:00 CDT, so
                // the next hour boundary is 01:00 CST (06:00Z), then 02:00 CST.
                assert_eq!(
                    boundary_after(Rotation::Hourly, "2024-11-03T04:30:00Z"),
                    utc("2024-11-03T06:00:00Z")
                );
                assert_eq!(
                    boundary_after(Rotation::Hourly, "2024-11-03T05:00:00.001Z"),
                    utc("2024-11-03T06:00:00Z")
                );
                assert_eq!(
                    boundary_after(Rotation::Hourly, "2024-11-03T06:00:00.001Z"),
                    utc("2024-11-03T07:00:00Z")
                );
            });
        }

        #[test]
        fn sink_opened_before_a_gap_rotates_after_it() {
            // End-to-end through `FileSink`: a crafted zone whose DST starts
            // right after the sink is opened makes the next hour boundary
            // fall into the gap; the sink must still rotate.
            // Standard time is UTC and DST starts on a whole second 2-3 s
            // from now. The gap is sized so that it ends on a whole minute,
            // because the boundary probe walks whole minutes (real zones
            // always change on one); a real 60-minute shift would make this
            // test wait for the next minute instead. chrono classifies a rule
            // by comparing only the months of its two transitions, so the DST
            // end lands in another month.
            let now = Utc::now();
            let start = (now + chrono::Duration::seconds(3))
                .with_nanosecond(0)
                .unwrap();
            let shift = match start.second() {
                0 => "1".to_string(),
                second => format!("1:00:{:02}", 60 - second),
            };
            let end = start + chrono::Duration::days(40);
            let rule = format!(
                "LST0LDT-{shift},{}/{},{}/{}",
                start.ordinal0(),
                start.format("%H:%M:%S"),
                end.ordinal0(),
                end.format("%H:%M:%S")
            );
            with_tz(&rule, || {
                let dir = unique_temp_path("dst-gap-sink");
                fs::create_dir_all(&dir).unwrap();
                let path = dir.join("app.log");
                let sink = FileSink::new(FileSinkConfig {
                    path: path.clone(),
                    rotation: Rotation::Hourly,
                    ..FileSinkConfig::default()
                })
                .unwrap();
                let boundary = sink.inner.next_rotation_boundary.load(Ordering::Relaxed);
                // Either the transition itself (next hour inside the gap) or,
                // if the hour turned in the 2-3 s before it, that hour.
                assert!(
                    boundary > 0 && boundary <= start.timestamp_millis(),
                    "boundary {boundary} should be at or before the DST transition at {} \
                     (rule {rule}, local now {})",
                    start.timestamp_millis(),
                    Local::now()
                );
                sink.write("before").unwrap();
                sink.flush().unwrap();

                let deadline = Instant::now() + Duration::from_secs(10);
                loop {
                    thread::sleep(Duration::from_millis(50));
                    sink.write("after").unwrap();
                    sink.flush().unwrap();
                    let rotated = fs::read_dir(&dir)
                        .unwrap()
                        .map(|e| e.unwrap().path())
                        .any(|p| p != path && p.extension().is_some_and(|ext| ext == "log"));
                    if rotated {
                        break;
                    }
                    assert!(Instant::now() < deadline, "no rotation across the DST gap");
                }
                assert!(
                    sink.inner.next_rotation_boundary.load(Ordering::Relaxed)
                        > Utc::now().timestamp_millis()
                );
                drop(sink);
                let _ = fs::remove_dir_all(&dir);
            });
        }
    }
}
