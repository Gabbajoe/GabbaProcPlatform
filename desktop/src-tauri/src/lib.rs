use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs,
    path::PathBuf,
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};
use tauri::{Manager, State};
const API: &str = "https://gabbaproc.kellerkind.info/api";
type Result<T> = std::result::Result<T, String>;
#[derive(Clone, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct Choice {
    enabled: bool,
    named: bool,
}
#[derive(Clone, Default, Serialize, Deserialize)]
#[serde(default, rename_all = "camelCase")]
struct Config {
    roots: Vec<PathBuf>,
    choices: BTreeMap<String, Choice>,
    auto_upload: bool,
    #[serde(default = "default_interval")]
    upload_interval_minutes: u64,
    upload_bandwidth_kib: u64,
    token_digest: Option<String>,
    acks: BTreeMap<String, String>,
}
fn default_interval() -> u64 {
    15
}
struct Inner {
    config: Config,
    token: Option<String>,
    persistent: bool,
    busy: bool,
    last_auto_attempt: Option<Instant>,
    last_queue_attempt: Option<Instant>,
    manual_drain: bool,
    status: String,
    progress: BTreeMap<String, Value>,
    files: BTreeMap<String, PathBuf>,
    config_file: PathBuf,
}
#[derive(Clone)]
struct AppState(Arc<Mutex<Inner>>);
struct RestartTarget(Mutex<Option<PathBuf>>);
fn key() -> Result<keyring::Entry> {
    keyring::Entry::new(
        if cfg!(debug_assertions) {
            "info.kellerkind.gabbaproc.dev"
        } else {
            "info.kellerkind.gabbaproc"
        },
        "upload-token",
    )
    .map_err(|_| "System keyring unavailable".into())
}
fn save(s: &Inner) -> Result<()> {
    let data = serde_json::to_vec_pretty(&s.config).map_err(|_| "Cannot encode preferences")?;
    let temp = s.config_file.with_extension("tmp");
    fs::write(&temp, data).map_err(|_| "Cannot save preferences")?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&temp, fs::Permissions::from_mode(0o600))
            .map_err(|_| "Cannot protect preferences")?;
    }
    fs::rename(temp, &s.config_file).map_err(|_| "Cannot replace preferences".into())
}
fn api_base() -> String {
    #[cfg(debug_assertions)]
    if let Ok(value) = std::env::var("GABBAPROC_TEST_API") {
        if let Ok(url) = reqwest::Url::parse(&value) {
            if url.scheme() == "http" && url.host_str() == Some("127.0.0.1") && url.path() == "/api"
            {
                return value;
            }
        }
    }
    if cfg!(debug_assertions) {
        "http://127.0.0.1:8771/api".to_string()
    } else {
        API.to_string()
    }
}
fn client() -> Result<reqwest::blocking::Client> {
    reqwest::blocking::Client::builder()
        .https_only(!api_base().starts_with("http://127.0.0.1:"))
        .redirect(reqwest::redirect::Policy::none())
        .timeout(Duration::from_secs(25))
        .build()
        .map_err(|_| "Cannot initialize HTTPS".into())
}
fn response(r: std::result::Result<reqwest::blocking::Response, reqwest::Error>) -> Result<Value> {
    use std::io::Read;
    let r = r.map_err(|_| "Connection failed; data stays local")?;
    let status = r.status();
    let mut bytes = Vec::new();
    r.take(65537)
        .read_to_end(&mut bytes)
        .map_err(|_| "Cannot read response")?;
    if bytes.len() > 65536 {
        return Err("Server response too large".into());
    }
    if !status.is_success() {
        return Err(match status.as_u16() {
            401 => "Upload token invalid or revoked",
            403 => "Invite invalid or expired",
            409 => "Snapshot conflict or character belongs to another device",
            422 => "Server rejected inconsistent measurements",
            429 => "Upload limit reached; retry later",
            _ => "Server rejected request",
        }
        .into());
    }
    serde_json::from_slice(&bytes).map_err(|_| "Invalid server response".into())
}
#[tauri::command]
fn overview(state: State<AppState>, app: tauri::AppHandle) -> Value {
    let s = state.0.lock().unwrap();
    json!({"version":app.package_info().version.to_string(),"localBuild":cfg!(debug_assertions),"autoUpload":s.config.auto_upload,"uploadIntervalMinutes":s.config.upload_interval_minutes,"uploadBandwidthKib":s.config.upload_bandwidth_kib,"hasToken":s.token.is_some(),"persistentToken":s.persistent,"busy":s.busy,"status":s.status,"progress":s.progress,"finishingUpload":s.manual_drain})
}
#[tauri::command]
fn discover(state: State<AppState>) -> Result<Value> {
    let home = std::env::var_os(if cfg!(windows) { "USERPROFILE" } else { "HOME" })
        .map(PathBuf::from)
        .ok_or("Home directory unavailable")?;
    let mut roots = gabbaproc_core::roots(&home);
    let mut s = state.0.lock().unwrap();
    roots.extend(s.config.roots.clone());
    let paths = gabbaproc_core::discover(&roots);
    s.files.clear();
    let mut out = Vec::new();
    for path in paths {
        let mut row = gabbaproc_core::source_labels(&path);
        match gabbaproc_core::read_file(&path) {
            Ok(raw) => match gabbaproc_core::payload(&raw, false) {
                Ok(payload) => {
                    let id = payload["characterId"].as_str().unwrap().to_string();
                    if s.files.contains_key(&id) {
                        row["error"] = json!("duplicate");
                    } else {
                        row["id"] = json!(id);
                        row["choice"] =
                            json!(s.config.choices.get(&id).cloned().unwrap_or_default());
                        row["sequence"] = payload["sequence"].clone();
                        row["rows"] = json!(payload["totals"].as_array().map_or(0, |a| a.len()));
                        s.files.insert(id, path);
                    }
                }
                Err(_) => {
                    row["error"] = json!(if raw.get("export").is_none_or(Value::is_null) {
                        "missing_snapshot"
                    } else {
                        "invalid_export"
                    })
                }
            },
            Err(_) => row["error"] = json!("unreadable_export"),
        }
        out.push(row);
    }
    Ok(json!(out))
}
#[tauri::command]
fn add_root(path: String, state: State<AppState>) -> Result<()> {
    let path = PathBuf::from(path);
    if !path.is_dir() {
        return Err("Choose the World of Warcraft folder".into());
    }
    let mut s = state.0.lock().unwrap();
    if s.config.roots.len() >= 20 {
        return Err("Folder limit reached".into());
    }
    if !s.config.roots.contains(&path) {
        s.config.roots.push(path)
    }
    save(&s)
}
#[tauri::command]
fn set_auto(enabled: bool, state: State<AppState>) -> Result<()> {
    let mut s = state.0.lock().unwrap();
    s.config.auto_upload = enabled;
    if !enabled {
        s.manual_drain = false;
    }
    s.last_auto_attempt = Some(Instant::now());
    save(&s)
}
#[tauri::command]
fn set_interval(minutes: u64, state: State<AppState>) -> Result<()> {
    if !gabbaproc_core::valid_upload_interval(minutes) {
        return Err("Choose 5–60 minutes in steps of 5".into());
    }
    let mut s = state.0.lock().unwrap();
    s.config.upload_interval_minutes = minutes;
    s.last_auto_attempt = Some(Instant::now());
    save(&s)
}
#[tauri::command]
fn set_bandwidth(kib: u64, state: State<AppState>) -> Result<()> {
    if ![0, 64, 128, 256, 512, 1024].contains(&kib) {
        return Err("Invalid bandwidth limit".into());
    }
    let mut s = state.0.lock().unwrap();
    if s.busy {
        return Err("Wait until the current upload finishes".into());
    }
    s.config.upload_bandwidth_kib = kib;
    save(&s)
}
#[tauri::command]
fn quit_app(app: tauri::AppHandle) {
    app.exit(0);
}

#[tauri::command]
fn restart_after_update(version: String, app: tauri::AppHandle) -> Result<()> {
    #[cfg(target_os = "linux")]
    if let Some(current) = app.env().appimage {
        let current = PathBuf::from(current);
        let target = gabbaproc_core::versioned_appimage(&current, &version)?;
        // Refresh the launcher before leaving this process, too.
        if let Err(e) = register_linux_desktop_for(&target) {
            // Restore the original name so the existing launcher remains usable.
            if current != target {
                let _ = fs::hard_link(&target, &current).and_then(|_| fs::remove_file(&target));
            }
            return Err(format!(
                "Update installed, but launcher refresh failed: {e}"
            ));
        }
        *app.state::<RestartTarget>().0.lock().unwrap() = Some(target);
        app.exit(0);
        return Ok(());
    }
    let _ = version;
    app.request_restart();
    Ok(())
}

fn tray_menu(app: &tauri::AppHandle, german: bool) -> tauri::Result<tauri::menu::Menu<tauri::Wry>> {
    use tauri::menu::{Menu, MenuItem};
    let open = MenuItem::with_id(
        app,
        "open",
        if german { "Öffnen" } else { "Open" },
        true,
        None::<&str>,
    )?;
    let quit = MenuItem::with_id(
        app,
        "quit",
        if german { "Beenden" } else { "Quit" },
        true,
        None::<&str>,
    )?;
    Menu::with_items(app, &[&open, &quit])
}
#[tauri::command]
fn set_language(language: String, app: tauri::AppHandle) -> Result<()> {
    if let Some(tray) = app.tray_by_id("main") {
        tray.set_menu(Some(
            tray_menu(&app, language == "de").map_err(|e| e.to_string())?,
        ))
        .map_err(|e| e.to_string())?;
    }
    Ok(())
}
fn show_main(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

#[tauri::command]
fn set_choice(id: String, enabled: bool, named: bool, state: State<AppState>) -> Result<()> {
    let mut s = state.0.lock().unwrap();
    if s.busy {
        return Err("Wait until the current upload finishes".into());
    }
    if !s.files.contains_key(&id) {
        return Err("Unknown character".into());
    }
    s.config
        .choices
        .insert(id.clone(), Choice { enabled, named });
    s.config.acks.remove(&id);
    save(&s)
}
#[tauri::command]
fn preview(id: String, state: State<AppState>) -> Result<Value> {
    let s = state.0.lock().unwrap();
    let path = s.files.get(&id).ok_or("Unknown character")?;
    let named = s.config.choices.get(&id).is_some_and(|c| c.named);
    gabbaproc_core::payload_batches(&gabbaproc_core::read_file(path)?, named)
        .map(|packets| json!({"packets": packets}))
}
#[tauri::command]
fn set_token(token: String, state: State<AppState>) -> Result<bool> {
    if token.len() < 30
        || token.len() > 100
        || !token
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"_-".contains(&b))
    {
        return Err("Invalid token format".into());
    }
    let mut s = state.0.lock().unwrap();
    if s.busy {
        return Err("Upload in progress".into());
    }
    s.persistent = key()
        .and_then(|k| k.set_password(&token).map_err(|_| "Keyring locked".into()))
        .is_ok();
    s.config.token_digest = Some(format!("{:x}", Sha256::digest(token.as_bytes())));
    s.token = Some(token);
    s.config.acks.clear();
    save(&s)?;
    Ok(s.persistent)
}
fn outbox_path(s: &Inner, token: &str, id: &str) -> PathBuf {
    s.config_file
        .parent()
        .unwrap()
        .join("outbox")
        .join(format!("{:x}", Sha256::digest(token.as_bytes())))
        .join(format!("{:x}.json", Sha256::digest(id.as_bytes())))
}
fn upload_progress(
    state: &AppState,
    id: &str,
    phase: &str,
    confirmed: usize,
    total: usize,
    next_check: u64,
) {
    state.0.lock().unwrap().progress.insert(
        id.to_string(),
        json!({"phase":phase,"confirmed":confirmed,"total":total,"nextCheck":next_check}),
    );
}
fn epoch_seconds() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}
fn sync_inner(state: &AppState, automatic: bool) -> Result<Value> {
    let (token, jobs, bandwidth) = {
        let mut s = state.0.lock().unwrap();
        if s.busy || (automatic && !s.config.auto_upload && !s.manual_drain) {
            return Ok(json!({"status":"idle"}));
        }
        if automatic
            && s.last_queue_attempt
                .is_some_and(|last| last.elapsed() < Duration::from_secs(30))
        {
            return Ok(json!({"status":"idle"}));
        }
        s.last_queue_attempt = Some(Instant::now());
        let fresh = !automatic
            || (s.config.auto_upload
                && s.last_auto_attempt.is_none_or(|last| {
                    last.elapsed() >= Duration::from_secs(s.config.upload_interval_minutes * 60)
                }));
        if fresh {
            s.last_auto_attempt = Some(Instant::now());
        }
        let token = s.token.clone().ok_or("Set your upload token first")?;
        let jobs: Vec<_> = s
            .config
            .choices
            .iter()
            .filter(|(_, c)| c.enabled)
            .map(|(id, c)| {
                (
                    id.clone(),
                    s.files.get(id).cloned(),
                    c.named,
                    s.config.acks.get(id).cloned(),
                    outbox_path(&s, &token, id),
                )
            })
            .filter(|(_, _, _, _, queue_path)| fresh || queue_path.exists())
            .collect();
        if fresh && (!automatic || !s.manual_drain) {
            s.progress.clear();
        }
        s.busy = true;
        if !automatic {
            s.manual_drain = true;
        }
        (token, jobs, s.config.upload_bandwidth_kib)
    };
    let result: Result<Value> = (|| {
        let client = client()?;
        let mut uploaded = 0;
        let mut pending = 0;
        let mut errors = Vec::new();
        let mut sent_packets = 0;
        for (id, path, named, ack, queue_path) in jobs {
            let attempt: Result<bool> = (|| {
                upload_progress(state, &id, "preparing", 0, 0, 0);
                let mut queue = match gabbaproc_core::outbox::Outbox::load(&queue_path)? {
                    Some(queue) => queue,
                    None => {
                        let raw = gabbaproc_core::read_file(
                            path.as_ref()
                                .ok_or("Export unavailable; select its WoW folder")?,
                        )?;
                        let packets = gabbaproc_core::payload_batches(&raw, named)?;
                        let hash = format!(
                            "{:x}",
                            Sha256::digest(serde_json::to_vec(&packets).unwrap())
                        );
                        if ack.as_deref() == Some(&hash) {
                            upload_progress(state, &id, "unchanged", 0, 0, 0);
                            return Ok(false);
                        }
                        let queue = gabbaproc_core::outbox::Outbox::new(hash, packets, named);
                        queue.save(&queue_path)?;
                        queue
                    }
                };
                upload_progress(
                    state,
                    &id,
                    "ready",
                    queue.cursor,
                    queue.packets.len(),
                    epoch_seconds() + 30,
                );
                // An opt-out applies before resuming any previously named queue.
                if queue.named && !named {
                    let r = client
                        .post(format!("{}/privacy", api_base()))
                        .bearer_auth(&token)
                        .json(&json!({"characterId": id}))
                        .send()
                        .map_err(|_| "Cannot apply anonymous mode; nothing uploaded")?;
                    if r.status().as_u16() != 404 {
                        response(Ok(r))?;
                    }
                    for p in &mut queue.packets {
                        p["privacy"] = json!("anonymous");
                        p.as_object_mut().unwrap().remove("name");
                        p.as_object_mut().unwrap().remove("realm");
                    }
                    queue.named = false;
                    queue.job_id = None;
                    queue.blocked = None;
                    queue.cursor = 0;
                    queue.retry_at = 0;
                    queue.fingerprint = format!(
                        "{:x}",
                        Sha256::digest(serde_json::to_vec(&queue.packets).unwrap())
                    );
                    queue.save(&queue_path)?;
                }
                if let Some(reason) = &queue.blocked {
                    upload_progress(state, &id, "blocked", queue.cursor, queue.packets.len(), 0);
                    return Err(format!("Upload {reason}; local queue retained"));
                }
                let now = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap_or_default()
                    .as_secs();
                if queue.retry_at > now {
                    upload_progress(
                        state,
                        &id,
                        "retry",
                        queue.cursor,
                        queue.packets.len(),
                        queue.retry_at,
                    );
                    pending += queue.packets.len() - queue.cursor;
                    return Ok(false);
                }
                while queue.cursor < queue.packets.len() && sent_packets < 12 {
                    let mut retry_after = 0;
                    let transfer: Result<Value> = (|| {
                        let response_result = if let Some(job) = &queue.job_id {
                            upload_progress(
                                state,
                                &id,
                                "checking",
                                queue.cursor,
                                queue.packets.len(),
                                0,
                            );
                            let r = client
                                .get(format!("{}/upload-jobs/{job}", api_base()))
                                .bearer_auth(&token)
                                .send()
                                .map_err(|_| "Cannot check receipt; data stays local")?;
                            if r.status().as_u16() == 404 {
                                queue.job_id = None; // receipt lost: replay immutable packet safely
                                return Err("Receipt unavailable; packet will be retried".into());
                            }
                            r
                        } else {
                            let bytes = serde_json::to_vec(&queue.packets[queue.cursor])
                                .map_err(|_| "Cannot encode packet")?;
                            let len = bytes.len() as u64;
                            sent_packets += 1;
                            upload_progress(
                                state,
                                &id,
                                "sending",
                                queue.cursor,
                                queue.packets.len(),
                                0,
                            );
                            let body = reqwest::blocking::Body::sized(
                                gabbaproc_core::outbox::LimitedReader::new(bytes, bandwidth),
                                len,
                            );
                            client
                                .post(format!("{}/upload-jobs", api_base()))
                                .bearer_auth(&token)
                                .header("Content-Type", "application/json")
                                .body(body)
                                .send()
                                .map_err(|_| "Connection failed; packet stays local")?
                        };
                        retry_after = response_result
                            .headers()
                            .get("retry-after")
                            .and_then(|v| v.to_str().ok())
                            .and_then(|v| v.parse::<u64>().ok())
                            .unwrap_or(0);
                        response(Ok(response_result))
                    })();
                    match transfer.and_then(|r| queue.receipt(&r)) {
                        Ok(advanced) => {
                            queue.save(&queue_path)?;
                            let phase = if queue.blocked.is_some() {
                                "blocked"
                            } else if queue.cursor == queue.packets.len() {
                                "complete"
                            } else if advanced {
                                "ready"
                            } else {
                                "waiting"
                            };
                            upload_progress(
                                state,
                                &id,
                                phase,
                                queue.cursor,
                                queue.packets.len(),
                                epoch_seconds() + 30,
                            );
                            if !advanced {
                                break;
                            }
                        }
                        Err(e) => {
                            let jitter = std::time::SystemTime::now()
                                .duration_since(std::time::UNIX_EPOCH)
                                .unwrap_or_default()
                                .subsec_nanos() as u64;
                            queue.retry(now, retry_after, jitter);
                            queue.save(&queue_path)?;
                            upload_progress(
                                state,
                                &id,
                                "retry",
                                queue.cursor,
                                queue.packets.len(),
                                queue.retry_at,
                            );
                            return Err(e);
                        }
                    }
                }
                pending += queue.packets.len() - queue.cursor;
                if queue.cursor == queue.packets.len() {
                    let mut s = state.0.lock().unwrap();
                    s.config.acks.insert(id.clone(), queue.fingerprint);
                    save(&s)?;
                    fs::remove_file(&queue_path)
                        .map_err(|_| "Cannot remove completed local queue")?;
                    s.progress.insert(id.clone(), json!({"phase":"complete","confirmed":queue.packets.len(),"total":queue.packets.len(),"nextCheck":0}));
                    return Ok(true);
                }
                if let Some(reason) = queue.blocked {
                    return Err(format!("Upload {reason}; local queue retained"));
                }
                Ok(false)
            })();
            match attempt {
                Ok(true) => uploaded += 1,
                Ok(false) => {}
                Err(e) => {
                    let mut inner = state.0.lock().unwrap();
                    if let Some(p) = inner.progress.get_mut(&id) {
                        if p["phase"] != "retry" && p["phase"] != "blocked" {
                            p["phase"] = json!("error");
                        }
                    }
                    errors.push(format!("{}: {e}", id.chars().take(8).collect::<String>()));
                }
            }
        }
        Ok(json!({"uploaded":uploaded,"pendingPackets":pending,"errors":errors}))
    })();
    let mut s = state.0.lock().unwrap();
    s.busy = false;
    // Finish only existing selected queues; this does not enable scheduled
    // discovery or automatically upload later exports after a manual request.
    if s.manual_drain {
        s.manual_drain = s
            .config
            .choices
            .iter()
            .filter(|(_, choice)| choice.enabled)
            .any(|(id, _)| {
                gabbaproc_core::outbox::Outbox::load(&outbox_path(&s, &token, id))
                    .ok()
                    .flatten()
                    .is_some_and(|queue| queue.blocked.is_none())
            });
    }
    s.status = match &result {
        Ok(v) => v.to_string(),
        Err(e) => e.clone(),
    };
    result
}
#[tauri::command]
async fn sync_now(state: State<'_, AppState>) -> Result<Value> {
    let s = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || sync_inner(&s, false))
        .await
        .map_err(|_| "Upload task failed")?
}
#[tauri::command]
async fn hide_name(id: String, state: State<'_, AppState>) -> Result<()> {
    let s = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let token = {
            let mut inner = s.0.lock().unwrap();
            if inner.busy {
                return Err("Wait until upload finishes".into());
            }
            let token = inner.token.clone().ok_or("Token missing")?;
            let c = inner
                .config
                .choices
                .get_mut(&id)
                .ok_or("Unknown character")?;
            c.named = false;
            c.enabled = false;
            inner.config.acks.remove(&id);
            save(&inner)?;
            inner.busy = true;
            token
        };
        let result = client()
            .and_then(|c| {
                response(
                    c.post(format!("{}/privacy", api_base()))
                        .bearer_auth(token)
                        .json(&json!({"characterId":id}))
                        .send(),
                )
            })
            .map(|_| ());
        s.0.lock().unwrap().busy = false;
        result
    })
    .await
    .map_err(|_| "Privacy task failed")?
}
#[tauri::command]
async fn delete_data(state: State<'_, AppState>) -> Result<()> {
    let s = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let token = {
            let mut i = s.0.lock().unwrap();
            if i.busy {
                return Err("Upload in progress".into());
            }
            let t = i.token.clone().ok_or("Token missing")?;
            i.config.auto_upload = false;
            for c in i.config.choices.values_mut() {
                c.enabled = false
            }
            save(&i)?;
            i.busy = true;
            t
        };
        let result = client().and_then(|c| {
            response(
                c.delete(format!("{}/device", api_base()))
                    .bearer_auth(token)
                    .send(),
            )
        });
        let mut i = s.0.lock().unwrap();
        i.busy = false;
        result?;
        if let Ok(k) = key() {
            let _ = k.delete_credential();
        }
        i.token = None;
        i.config.token_digest = None;
        i.persistent = false;
        i.config.acks.clear();
        save(&i)
    })
    .await
    .map_err(|_| "Delete task failed")?
}
#[cfg(target_os = "linux")]
fn register_linux_desktop_for(
    executable: &std::path::Path,
) -> std::result::Result<(), Box<dyn std::error::Error>> {
    let data = std::env::var_os("XDG_DATA_HOME")
        .map(PathBuf::from)
        .filter(|p| p.is_absolute())
        .or_else(|| std::env::var_os("HOME").map(|h| PathBuf::from(h).join(".local/share")))
        .ok_or("No user data directory")?;
    gabbaproc_core::install_desktop_entry(
        &data,
        &executable,
        include_bytes!("../icons/128x128.png"),
    )?;
    Ok(())
}

pub fn run() {
    #[cfg(all(target_os = "linux", not(debug_assertions)))]
    {
        let executable = std::env::var_os("APPIMAGE")
            .map(PathBuf::from)
            .filter(|p| p.is_absolute() && p.is_file())
            .unwrap_or_else(|| std::env::current_exe().expect("Cannot locate application"));
        if let Err(e) = register_linux_desktop_for(&executable) {
            eprintln!("Desktop icon registration failed: {e}");
        }
    }
    tauri::Builder::default()
        .manage(RestartTarget(Mutex::new(None)))
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_autostart::Builder::new().build())
        .setup(|app| {
            let dir = app.path().app_config_dir()?;
            fs::create_dir_all(&dir)?;
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                fs::set_permissions(&dir, fs::Permissions::from_mode(0o700))?;
            }
            let file = dir.join("preferences.json");
            let mut config: Config = fs::read(&file)
                .ok()
                .and_then(|b| serde_json::from_slice(&b).ok())
                .unwrap_or_default();
            if !gabbaproc_core::valid_upload_interval(config.upload_interval_minutes) {
                config.upload_interval_minutes = default_interval();
            }
            if ![0, 64, 128, 256, 512, 1024].contains(&config.upload_bandwidth_kib) {
                config.upload_bandwidth_kib = 0;
            }
            let token = key().ok().and_then(|k| k.get_password().ok()).filter(|t| {
                config.token_digest.as_deref()
                    == Some(&format!("{:x}", Sha256::digest(t.as_bytes())))
            });
            let state = AppState(Arc::new(Mutex::new(Inner {
                config,
                persistent: token.is_some(),
                token,
                busy: false,
                last_auto_attempt: Some(Instant::now()),
                last_queue_attempt: None,
                manual_drain: false,
                status: String::new(),
                progress: BTreeMap::new(),
                files: BTreeMap::new(),
                config_file: file,
            })));
            app.manage(state.clone());
            if let Some(icon) = app.default_window_icon() {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.set_icon(icon.clone());
                }
                let tray = tauri::tray::TrayIconBuilder::with_id("main")
                    .icon(icon.clone())
                    .tooltip("GabbaProc Companion")
                    .menu(&tray_menu(app.handle(), false)?)
                    .show_menu_on_left_click(true)
                    .on_menu_event(|app, event| match event.id.as_ref() {
                        "open" => show_main(app),
                        "quit" => app.exit(0),
                        _ => {}
                    })
                    .build(app);
                if let Err(e) = tray {
                    eprintln!("Tray unavailable: {e}");
                }
            }
            std::thread::spawn(move || loop {
                std::thread::sleep(Duration::from_secs(5));
                let _ = sync_inner(&state, true);
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                if window.app_handle().tray_by_id("main").is_some() && window.hide().is_ok() {
                    api.prevent_close();
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            overview,
            discover,
            add_root,
            set_auto,
            set_interval,
            set_bandwidth,
            set_language,
            quit_app,
            restart_after_update,
            set_choice,
            preview,
            set_token,
            sync_now,
            hide_name,
            delete_data
        ])
        .build(tauri::generate_context!())
        .expect("Could not start GabbaProc Companion")
        .run(|app, event| {
            #[cfg(target_os = "linux")]
            if let tauri::RunEvent::Exit = event {
                if let Some(target) = app.state::<RestartTarget>().0.lock().unwrap().take() {
                    let mut env = app.env();
                    env.appimage = Some(target.into_os_string());
                    app.cleanup_before_exit();
                    tauri::process::restart(&env);
                }
            }
            #[cfg(not(target_os = "linux"))]
            let _ = (app, event);
        });
}

#[cfg(test)]
mod transport_tests {
    use super::*;
    #[test]
    fn durable_retry_receipt_restart_and_offline_source() {
        use std::io::{Read, Write};
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        std::env::set_var("GABBAPROC_TEST_API", format!("http://127.0.0.1:{port}/api"));
        let job = "b".repeat(64);
        let replies = vec![
            (429, json!({"detail":"Busy"})),
            (202, json!({"jobId":job,"status":"queued"})),
            (200, json!({"jobId":job,"status":"processed"})),
        ];
        let server = std::thread::spawn(move || {
            for (index, (code, reply)) in replies.into_iter().enumerate() {
                let (mut stream, _) = listener.accept().unwrap();
                stream
                    .set_read_timeout(Some(Duration::from_secs(5)))
                    .unwrap();
                let mut request = Vec::new();
                let mut byte = [0u8; 1];
                while !request.ends_with(b"\r\n\r\n") {
                    stream.read_exact(&mut byte).unwrap();
                    request.push(byte[0]);
                    assert!(request.len() < 16384);
                }
                let headers = String::from_utf8(request).unwrap();
                assert!(headers.starts_with(if index == 2 {
                    "GET /api/upload-jobs/"
                } else {
                    "POST /api/upload-jobs "
                }));
                let size = headers
                    .lines()
                    .find_map(|line| {
                        line.to_ascii_lowercase()
                            .strip_prefix("content-length: ")
                            .and_then(|v| v.parse::<usize>().ok())
                    })
                    .unwrap_or(0);
                let mut body = vec![0; size];
                stream.read_exact(&mut body).unwrap();
                if index < 2 {
                    assert_eq!(
                        serde_json::from_slice::<Value>(&body).unwrap()["schemaVersion"],
                        2
                    );
                }
                let body = reply.to_string();
                write!(stream, "HTTP/1.1 {code} Test\r\nContent-Type: application/json\r\nContent-Length: {}\r\nRetry-After: 60\r\nConnection: close\r\n\r\n{body}", body.len()).unwrap();
            }
        });
        let dir = std::env::temp_dir().join(format!("gabbaproc-transport-{}", std::process::id()));
        fs::create_dir_all(&dir).unwrap();
        let id = "12345678-1234-4234-8234-123456789abc";
        let token = "local-test-token";
        let mut config = Config::default();
        config.choices.insert(
            id.into(),
            Choice {
                enabled: true,
                named: false,
            },
        );
        let state = AppState(Arc::new(Mutex::new(Inner {
            config,
            token: Some(token.into()),
            persistent: false,
            busy: false,
            last_auto_attempt: None,
            last_queue_attempt: None,
            manual_drain: false,
            status: String::new(),
            progress: BTreeMap::new(),
            files: BTreeMap::new(),
            config_file: dir.join("preferences.json"),
        })));
        let queue_path = outbox_path(&state.0.lock().unwrap(), token, id);
        let queue = gabbaproc_core::outbox::Outbox::new(
            "fingerprint".into(),
            vec![json!({"schemaVersion":2})],
            false,
        );
        queue.save(&queue_path).unwrap();
        let first = sync_inner(&state, false).unwrap();
        assert_eq!(first["uploaded"], 0);
        let mut queue = gabbaproc_core::outbox::Outbox::load(&queue_path)
            .unwrap()
            .unwrap();
        assert_eq!(queue.cursor, 0);
        assert!(queue.retry_at > 0);
        assert!(state.0.lock().unwrap().config.acks.is_empty());
        queue.retry_at = 0;
        queue.save(&queue_path).unwrap();
        let second = sync_inner(&state, false).unwrap();
        assert_eq!(second["pendingPackets"], 1);
        assert_eq!(state.0.lock().unwrap().progress[id]["phase"], "waiting");
        assert_eq!(state.0.lock().unwrap().progress[id]["confirmed"], 0);
        assert!(state.0.lock().unwrap().config.acks.is_empty());
        // Simulated process state loss; no source file is available.
        state.0.lock().unwrap().last_auto_attempt = None;
        assert!(gabbaproc_core::outbox::Outbox::load(&queue_path)
            .unwrap()
            .unwrap()
            .job_id
            .is_some());
        assert!(!state.0.lock().unwrap().config.auto_upload);
        assert!(state.0.lock().unwrap().manual_drain);
        state.0.lock().unwrap().last_queue_attempt = None;
        let third = sync_inner(&state, true).unwrap();
        assert_eq!(third["uploaded"], 1);
        assert_eq!(state.0.lock().unwrap().progress[id]["phase"], "complete");
        assert_eq!(state.0.lock().unwrap().progress[id]["confirmed"], 1);
        assert_eq!(state.0.lock().unwrap().config.acks[id], "fingerprint");
        assert!(!queue_path.exists());
        assert!(!state.0.lock().unwrap().manual_drain);
        assert_eq!(sync_inner(&state, true).unwrap()["status"], "idle");
        server.join().unwrap();
        std::env::remove_var("GABBAPROC_TEST_API");
        fs::remove_dir_all(dir).unwrap();
    }
}
