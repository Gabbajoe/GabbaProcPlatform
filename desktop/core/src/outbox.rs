//! Durable per-character upload state. Tokens are never stored here.
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    fs,
    io::{Read, Write},
    path::Path,
};
type Result<T> = std::result::Result<T, String>;
const MAX_BYTES: u64 = 128 * 1024 * 1024;
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Outbox {
    pub fingerprint: String,
    pub packets: Vec<Value>,
    pub cursor: usize,
    pub job_id: Option<String>,
    pub named: bool,
    pub attempts: u32,
    pub retry_at: u64,
    pub blocked: Option<String>,
}
impl Outbox {
    pub fn new(fingerprint: String, packets: Vec<Value>, named: bool) -> Self {
        Self {
            fingerprint,
            packets,
            named,
            cursor: 0,
            job_id: None,
            attempts: 0,
            retry_at: 0,
            blocked: None,
        }
    }
    pub fn load(path: &Path) -> Result<Option<Self>> {
        match fs::symlink_metadata(path) {
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Ok(meta) if meta.is_file() && meta.len() <= MAX_BYTES => {}
            _ => return Err("Cannot safely read local upload queue".into()),
        }
        let mut bytes = Vec::new();
        fs::File::open(path)
            .map_err(|_| "Cannot read upload queue")?
            .take(MAX_BYTES + 1)
            .read_to_end(&mut bytes)
            .map_err(|_| "Cannot read upload queue")?;
        if bytes.len() as u64 > MAX_BYTES {
            return Err("Local queue exceeds limit; retained on disk".into());
        }
        let out: Self =
            serde_json::from_slice(&bytes).map_err(|_| "Invalid local queue; retained on disk")?;
        if out.cursor > out.packets.len() || out.packets.is_empty() {
            return Err("Invalid local queue position".into());
        }
        Ok(Some(out))
    }
    pub fn save(&self, path: &Path) -> Result<()> {
        let bytes = serde_json::to_vec(self).map_err(|_| "Cannot encode upload queue")?;
        if bytes.len() as u64 > MAX_BYTES {
            return Err("Local queue exceeds 128 MiB; source archive retained".into());
        }
        let parent = path.parent().ok_or("Invalid queue directory")?;
        fs::create_dir_all(parent).map_err(|_| "Cannot create upload queue")?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(parent, fs::Permissions::from_mode(0o700))
                .map_err(|_| "Cannot protect queue")?;
        }
        let temp = path.with_extension("pending");
        let mut options = fs::OpenOptions::new();
        options.write(true).create_new(true);
        // Leftovers belong to an interrupted write; the committed file survives.
        if temp.exists() {
            fs::remove_file(&temp).map_err(|_| "Cannot recover queue write")?;
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        let mut file = options
            .open(&temp)
            .map_err(|_| "Cannot write upload queue")?;
        file.write_all(&bytes)
            .and_then(|_| file.sync_all())
            .map_err(|_| "Cannot persist upload queue")?;
        drop(file);
        fs::rename(&temp, path).map_err(|_| "Cannot commit upload queue")?;
        #[cfg(unix)]
        fs::File::open(parent)
            .and_then(|f| f.sync_all())
            .map_err(|_| "Cannot persist queue directory")?;
        Ok(())
    }
    /// Only a processed receipt advances the cursor. Queued is not an ACK.
    pub fn receipt(&mut self, value: &Value) -> Result<bool> {
        let id = value["jobId"].as_str().ok_or("Missing receipt ID")?;
        if id.len() != 64 || !id.bytes().all(|c| c.is_ascii_hexdigit()) {
            return Err("Invalid receipt ID".into());
        }
        if self
            .job_id
            .as_deref()
            .is_some_and(|previous| previous != id)
        {
            return Err("Mismatched receipt ID".into());
        }
        self.job_id = Some(id.to_string());
        match value["status"].as_str() {
            Some("processed") => {
                self.cursor += 1;
                self.job_id = None;
                self.attempts = 0;
                self.retry_at = 0;
                Ok(true)
            }
            Some("queued") => Ok(false),
            Some("failed" | "rejected" | "cancelled") => {
                self.blocked = Some(value["status"].as_str().unwrap().to_string());
                Ok(false)
            }
            _ => Err("Unknown upload receipt status".into()),
        }
    }
    pub fn retry(&mut self, now: u64, minimum: u64, jitter: u64) {
        self.attempts = self.attempts.saturating_add(1);
        self.retry_at = now
            .saturating_add(
                (5_u64.saturating_mul(1 << self.attempts.min(9)))
                    .max(minimum)
                    .min(86400),
            )
            .saturating_add(jitter % 11);
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn receipt_and_crash_recovery() {
        let dir = std::env::temp_dir().join(format!("gabbaproc-outbox-{}", std::process::id()));
        let path = dir.join("queue.json");
        let mut queue = Outbox::new("source".into(), vec![json!({"a":1}), json!({"a":2})], false);
        queue.save(&path).unwrap();
        let id = "a".repeat(64);
        assert!(!queue
            .receipt(&json!({"jobId":id,"status":"queued"}))
            .unwrap());
        queue.save(&path).unwrap();
        fs::write(path.with_extension("pending"), "interrupted").unwrap();
        let mut restored = Outbox::load(&path).unwrap().unwrap();
        assert_eq!(restored.cursor, 0);
        assert_eq!(restored.job_id, Some(id.clone()));
        assert!(restored
            .receipt(&json!({"jobId":id,"status":"processed"}))
            .unwrap());
        restored.save(&path).unwrap();
        assert_eq!(Outbox::load(&path).unwrap().unwrap().cursor, 1);
        assert!(!restored
            .receipt(&json!({"jobId":id,"status":"rejected"}))
            .unwrap());
        assert_eq!(restored.cursor, 1);
        assert!(restored.blocked.is_some());
        restored.retry(1000, 60, 4);
        assert!(restored.retry_at >= 1060);
        fs::remove_dir_all(dir).unwrap();
    }
}

/// Pace each body chunk before handing it to HTTP. No multi-request concurrency.
pub struct LimitedReader {
    data: std::io::Cursor<Vec<u8>>,
    bytes_per_second: u64,
    sent: u64,
    start: std::time::Instant,
}
impl LimitedReader {
    pub fn new(bytes: Vec<u8>, kib: u64) -> Self {
        Self {
            data: std::io::Cursor::new(bytes),
            bytes_per_second: kib.saturating_mul(1024),
            sent: 0,
            start: std::time::Instant::now(),
        }
    }
}
impl Read for LimitedReader {
    fn read(&mut self, buf: &mut [u8]) -> std::io::Result<usize> {
        let limit = buf.len().min(16 * 1024);
        let n = self.data.read(&mut buf[..limit])?;
        self.sent += n as u64;
        if self.bytes_per_second != 0 && n != 0 {
            let target =
                std::time::Duration::from_secs_f64(self.sent as f64 / self.bytes_per_second as f64);
            if let Some(wait) = target.checked_sub(self.start.elapsed()) {
                std::thread::sleep(wait);
            }
        }
        Ok(n)
    }
}
