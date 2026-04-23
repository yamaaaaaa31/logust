use std::fs::{self, File, OpenOptions};
use std::io::{self, BufWriter, Write};
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

struct FileLockGuard {
    #[cfg(any(unix, windows))]
    file: File,
    #[cfg(not(any(unix, windows)))]
    _phantom: std::marker::PhantomData<()>,
}

impl FileLockGuard {
    fn shared(file: &File) -> io::Result<Self> {
        #[cfg(unix)]
        {
            let file = file.try_clone()?;
            flock_file(&file, libc::LOCK_SH)?;
            Ok(Self { file })
        }

        #[cfg(windows)]
        {
            let file = file.try_clone()?;
            windows_lock_file(&file, false)?;
            Ok(Self { file })
        }

        #[cfg(not(any(unix, windows)))]
        {
            let _ = file;
            Ok(Self {
                _phantom: std::marker::PhantomData,
            })
        }
    }

    fn exclusive(file: &File) -> io::Result<Self> {
        #[cfg(unix)]
        {
            let file = file.try_clone()?;
            flock_file(&file, libc::LOCK_EX)?;
            Ok(Self { file })
        }

        #[cfg(windows)]
        {
            let file = file.try_clone()?;
            windows_lock_file(&file, true)?;
            Ok(Self { file })
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
    lock_file: File,
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
            lock_file,
            file_identity,
            shared_identity,
        };
        writer.update_shared_identity();
        writer
    }

    fn write_line(&mut self, path: &Path, message: &str) -> io::Result<()> {
        let _lock = self.acquire_shared_lock(path)?;
        writeln!(self.writer, "{}", message)?;
        self.writer.flush()
    }

    fn write_line_unlocked(&mut self, message: &str) -> io::Result<()> {
        writeln!(self.writer, "{}", message)
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

        writeln!(self.writer, "{}", message)
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
    /// 0 means no rotation boundary (equivalent to None).
    next_rotation_boundary: AtomicI64,
    /// PID of the process that currently owns the live backend.
    /// Child processes created via fork() lazily reopen/recreate the backend on first use.
    creation_pid: AtomicU32,
    pending_rotation: StdMutex<Option<PendingRotation>>,
    pending_rotation_active: AtomicBool,
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

        let current_size = fs::metadata(&path).map(|m| m.len()).unwrap_or(0);

        #[cfg(unix)]
        if config.enqueue {
            ensure_atfork_registered()?;
        }

        let backend = if config.enqueue {
            WriterBackend::Async(FileSinkInner::create_async_writer_state(
                &path,
                FileSinkInner::rotation_coordination_enabled_for_config(&config),
            )?)
        } else {
            WriterBackend::Sync(SyncWriterState {
                writer: Some(FileSinkInner::open_sync_writer(&path)?),
            })
        };

        let now = Local::now();
        let next_boundary = FileSinkInner::calculate_next_rotation_boundary(&config.rotation, &now);

        let inner = Arc::new(FileSinkInner {
            config,
            state: StdMutex::new(FileSinkState { backend }),
            current_size: AtomicU64::new(current_size),
            current_file_time: StdMutex::new(now),
            next_rotation_boundary: AtomicI64::new(
                next_boundary.map(|b| b.timestamp_millis()).unwrap_or(0),
            ),
            creation_pid: AtomicU32::new(std::process::id()),
            pending_rotation: StdMutex::new(None),
            pending_rotation_active: AtomicBool::new(false),
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

    fn open_log_file(path: &Path) -> io::Result<File> {
        OpenOptions::new().create(true).append(true).open(path)
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
                            eprintln!("Failed to write to log: {}", err);
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
            Local::now().timestamp_millis() >= boundary_millis
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

        let rotation_lock_file = Self::open_rotation_lock_file(&self.config.path)?;
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
            needs_compression: self.config.compression && rotated_path.exists(),
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
        let lock_filename = Self::format_lock_filename(&self.config.path);

        let mut rotated_files: Vec<(PathBuf, SystemTime)> = fs::read_dir(parent)?
            .filter_map(|e| e.ok())
            .filter_map(|e| {
                let path = e.path();
                let filename = path.file_name()?.to_str()?;
                if path == lock_filename {
                    None
                } else if filename.starts_with(stem) && filename != current_filename {
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
}
