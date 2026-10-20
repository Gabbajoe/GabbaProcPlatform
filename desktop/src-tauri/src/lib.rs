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
    status: String,
    files: BTreeMap<String, PathBuf>,
    config_file: PathBuf,
}
#[derive(Clone)]
struct AppState(Arc<Mutex<Inner>>);
struct RestartTarget(Mutex<Option<PathBuf>>);
fn key() -> Result<keyring::Entry> {
    keyring::Entry::new("info.kellerkind.gabbaproc", "upload-token")
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
fn client() -> Result<reqwest::blocking::Client> {
    reqwest::blocking::Client::builder()
        .https_only(true)
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
fn overview(state: State<AppState>) -> Value {
    let s = state.0.lock().unwrap();
    json!({"autoUpload":s.config.auto_upload,"uploadIntervalMinutes":s.config.upload_interval_minutes,"hasToken":s.token.is_some(),"persistentToken":s.persistent,"busy":s.busy,"status":s.status})
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
    gabbaproc_core::payload(&gabbaproc_core::read_file(path)?, named)
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
fn sync_inner(state: &AppState, automatic: bool) -> Result<Value> {
    let (token, jobs) = {
        let mut s = state.0.lock().unwrap();
        if s.busy || (automatic && !s.config.auto_upload) {
            return Ok(json!({"status":"idle"}));
        }
        if automatic {
            let wait = Duration::from_secs(s.config.upload_interval_minutes * 60);
            if s.last_auto_attempt
                .is_some_and(|last| last.elapsed() < wait)
            {
                return Ok(json!({"status":"idle"}));
            }
        }
        s.last_auto_attempt = Some(Instant::now());
        let token = s.token.clone().ok_or("Set your upload token first")?;
        let jobs: Vec<_> = s
            .files
            .iter()
            .filter_map(|(id, path)| {
                let c = s.config.choices.get(id)?;
                if c.enabled {
                    Some((
                        id.clone(),
                        path.clone(),
                        c.named,
                        s.config.acks.get(id).cloned(),
                    ))
                } else {
                    None
                }
            })
            .collect();
        s.busy = true;
        (token, jobs)
    };
    let result: Result<Value> = (|| {
        let client = client()?;
        let mut uploaded = 0;
        let mut errors = Vec::new();
        for (id, path, named, ack) in jobs {
            let attempt: Result<bool> = (|| {
                let p = gabbaproc_core::payload(&gabbaproc_core::read_file(&path)?, named)?;
                let hash = format!("{:x}", Sha256::digest(serde_json::to_vec(&p).unwrap()));
                if ack.as_deref() == Some(&hash) {
                    return Ok(false);
                }
                let r = response(
                    client
                        .post(format!("{API}/imports"))
                        .bearer_auth(&token)
                        .json(&p)
                        .send(),
                )?;
                let mut s = state.0.lock().unwrap();
                s.config.acks.insert(id.clone(), hash);
                save(&s)?;
                if r["review"] == "quarantine" {
                    return Err("Accepted for review; excluded from public statistics".into());
                }
                Ok(true)
            })();
            match attempt {
                Ok(true) => uploaded += 1,
                Ok(false) => {}
                Err(e) => errors.push(format!("{}: {e}", &id[..8])),
            }
        }
        Ok(json!({"uploaded":uploaded,"errors":errors}))
    })();
    let mut s = state.0.lock().unwrap();
    s.busy = false;
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
                    c.post(format!("{API}/privacy"))
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
        let result = client()
            .and_then(|c| response(c.delete(format!("{API}/device")).bearer_auth(token).send()));
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
    #[cfg(target_os = "linux")]
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
                status: String::new(),
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
