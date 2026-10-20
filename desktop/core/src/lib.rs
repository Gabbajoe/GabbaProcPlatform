use serde_json::{json, Map, Value};
use std::{
    collections::HashSet,
    fs,
    path::{Path, PathBuf},
};
pub const MAX_FILE: usize = 8 * 1024 * 1024;
struct Parser<'a> {
    b: &'a [u8],
    p: usize,
    nodes: usize,
}
type Result<T> = std::result::Result<T, String>;
impl<'a> Parser<'a> {
    fn ws(&mut self) {
        loop {
            while self.p < self.b.len() && self.b[self.p].is_ascii_whitespace() {
                self.p += 1
            }
            if self.b.get(self.p..self.p + 2) == Some(b"--") {
                while self.p < self.b.len() && self.b[self.p] != b'\n' {
                    self.p += 1
                }
            } else {
                break;
            }
        }
    }
    fn take(&mut self, c: u8) -> bool {
        self.ws();
        if self.b.get(self.p) == Some(&c) {
            self.p += 1;
            true
        } else {
            false
        }
    }
    fn expect(&mut self, c: u8) -> Result<()> {
        if self.take(c) {
            Ok(())
        } else {
            Err("Unexpected token in SavedVariables".into())
        }
    }
    fn ident(&mut self) -> Result<String> {
        self.ws();
        let start = self.p;
        while self.p < self.b.len()
            && (self.b[self.p].is_ascii_alphanumeric() || self.b[self.p] == b'_')
        {
            self.p += 1
        }
        if start == self.p {
            return Err("Identifier expected".into());
        }
        Ok(String::from_utf8(self.b[start..self.p].to_vec()).unwrap())
    }
    fn string(&mut self) -> Result<String> {
        self.ws();
        let quote = *self.b.get(self.p).ok_or("Missing string")?;
        if quote != b'"' && quote != b'\'' {
            return Err("String expected".into());
        }
        self.p += 1;
        let mut out = Vec::new();
        loop {
            let c = *self.b.get(self.p).ok_or("Unterminated string")?;
            self.p += 1;
            if c == quote {
                break;
            }
            if c == b'\\' {
                let c = *self.b.get(self.p).ok_or("Invalid escape")?;
                self.p += 1;
                match c {
                    b'n' => out.push(b'\n'),
                    b'r' => out.push(b'\r'),
                    b't' => out.push(b'\t'),
                    b'\\' | b'"' | b'\'' => out.push(c),
                    b'0'..=b'9' => {
                        let mut v = (c - b'0') as u16;
                        for _ in 0..2 {
                            if let Some(c @ b'0'..=b'9') = self.b.get(self.p) {
                                v = v * 10 + (c - b'0') as u16;
                                self.p += 1
                            } else {
                                break;
                            }
                        }
                        if v > 255 {
                            return Err("Invalid byte escape".into());
                        }
                        out.push(v as u8)
                    }
                    _ => return Err("Unsupported escape".into()),
                }
            } else {
                if c < 32 {
                    return Err("Control character in string".into());
                }
                out.push(c)
            }
            if out.len() > 8192 {
                return Err("String too long".into());
            }
        }
        String::from_utf8(out).map_err(|_| "Invalid UTF-8".into())
    }
    fn value(&mut self, depth: usize) -> Result<Value> {
        self.ws();
        self.nodes += 1;
        if depth > 40 || self.nodes > 250000 {
            return Err("Export structure exceeds limits".into());
        }
        match self.b.get(self.p).copied() {
            Some(b'{') => {
                self.p += 1;
                let mut table = Map::new();
                let mut index = 1usize;
                loop {
                    if self.take(b'}') {
                        break;
                    }
                    let key;
                    if self.take(b'[') {
                        let v = self.value(depth + 1)?;
                        key = match v {
                            Value::String(s) => s,
                            Value::Number(n) if n.as_u64().is_some() => n.to_string(),
                            _ => return Err("Invalid table key".into()),
                        };
                        self.expect(b']')?;
                        self.expect(b'=')?;
                    } else {
                        let save = self.p;
                        let named = if self
                            .b
                            .get(self.p)
                            .is_some_and(|c| c.is_ascii_alphabetic() || *c == b'_')
                        {
                            let n = self.ident()?;
                            if self.take(b'=') {
                                Some(n)
                            } else {
                                self.p = save;
                                None
                            }
                        } else {
                            None
                        };
                        key = named.unwrap_or_else(|| {
                            let k = index.to_string();
                            index += 1;
                            k
                        });
                    }
                    let v = self.value(depth + 1)?;
                    if table.insert(key, v).is_some() {
                        return Err("Duplicate table key".into());
                    }
                    if self.take(b',') || self.take(b';') {
                        continue;
                    }
                    self.expect(b'}')?;
                    break;
                }
                Ok(Value::Object(table))
            }
            Some(b'"' | b'\'') => Ok(Value::String(self.string()?)),
            Some(b'-' | b'0'..=b'9') => {
                let start = self.p;
                while self.p < self.b.len()
                    && matches!(
                        self.b[self.p],
                        b'0'..=b'9' | b'.' | b'e' | b'E' | b'+' | b'-'
                    )
                {
                    self.p += 1
                }
                let s =
                    std::str::from_utf8(&self.b[start..self.p]).map_err(|_| "Invalid number")?;
                let v: Value = serde_json::from_str(s).map_err(|_| "Invalid number")?;
                if !v.is_number() {
                    return Err("Number expected".into());
                }
                Ok(v)
            }
            Some(_) => match self.ident()?.as_str() {
                "true" => Ok(json!(true)),
                "false" => Ok(json!(false)),
                "nil" => Ok(Value::Null),
                _ => Err("Executable Lua is not accepted".into()),
            },
            None => Err("Incomplete file".into()),
        }
    }
}
pub fn parse(raw: &str) -> Result<Value> {
    if raw.len() > MAX_FILE {
        return Err("SavedVariables exceeds 8 MiB".into());
    }
    let raw = raw.strip_prefix('\u{feff}').unwrap_or(raw);
    let mut p = Parser {
        b: raw.as_bytes(),
        p: 0,
        nodes: 0,
    };
    if p.ident()? != "GabbaProcTrackerDB" {
        return Err("Not a GabbaProcTracker SavedVariables file".into());
    }
    p.expect(b'=')?;
    let result = p.value(0)?;
    p.take(b';');
    p.ws();
    if p.p != p.b.len() {
        return Err("Trailing executable content is not accepted".into());
    }
    Ok(result)
}
fn object(v: &Value) -> Result<&Map<String, Value>> {
    v.as_object().ok_or_else(|| "Expected table".into())
}
fn string(v: &Value) -> Result<&str> {
    v.as_str().ok_or_else(|| "Expected text".into())
}
fn integer(v: &Value) -> Result<u64> {
    v.as_u64()
        .filter(|n| *n <= 9_007_199_254_740_991)
        .ok_or_else(|| "Expected bounded integer".into())
}
fn number(v: &Value) -> Result<f64> {
    v.as_f64()
        .filter(|n| n.is_finite() && *n >= 0.0 && *n <= 315_576_000.0)
        .ok_or_else(|| "Expected bounded duration".into())
}
fn uuid(v: &Value) -> Result<&str> {
    let s = string(v)?;
    if s.len() != 36
        || !s.bytes().enumerate().all(|(i, c)| {
            if [8, 13, 18, 23].contains(&i) {
                c == b'-'
            } else {
                c.is_ascii_digit() || (b'a'..=b'f').contains(&c)
            }
        })
    {
        return Err("Invalid UUID".into());
    }
    Ok(s)
}
fn entries(v: &Value) -> Result<Vec<&Value>> {
    let t = object(v)?;
    let mut keys: Vec<(usize, &Value)> = t
        .iter()
        .map(|(k, v)| {
            k.parse::<usize>()
                .map(|i| (i, v))
                .map_err(|_| "Invalid array index".to_string())
        })
        .collect::<Result<_>>()?;
    keys.sort_by_key(|v| v.0);
    for (i, (k, _)) in keys.iter().enumerate() {
        if *k != i + 1 {
            return Err("Sparse array".into());
        }
    }
    Ok(keys.into_iter().map(|(_, v)| v).collect())
}
fn group(v: &Value) -> Result<&str> {
    match string(v)? {
        "world" => Ok("world"),
        "party" => Ok("party"),
        "raid" => Ok("raid"),
        _ => Err("Unsupported area group".into()),
    }
}
pub fn known() -> HashSet<u64> {
    let catalog: Map<String, Value> =
        serde_json::from_str(include_str!("../../../server/catalog.json")).unwrap();
    catalog.keys().filter_map(|k| k.parse().ok()).collect()
}
/// Build a fresh allowlisted DTO. Raw names, paths, zones, stamps and effect names
/// cannot leak through anonymous mode; executable Lua is never evaluated.
pub fn payload(root: &Value, named: bool) -> Result<Value> {
    let e = &root["export"];
    if integer(&e["schemaVersion"])? != 1 {
        return Err("Unsupported or missing export; export in the addon first".into());
    }
    let ids = known();
    let version = string(&e["addonVersion"])?;
    if version.len() > 11
        || version.split('.').count() != 3
        || !version
            .split('.')
            .all(|s| !s.is_empty() && s.len() <= 3 && s.bytes().all(|b| b.is_ascii_digit()))
    {
        return Err("Invalid addon version".into());
    }
    let mut totals = Vec::new();
    let mut seen = HashSet::new();
    for r in entries(&e["totals"])? {
        let id = integer(&r["spellId"])?;
        if !ids.contains(&id) {
            continue;
        }
        let area = group(&r["group"])?;
        if !seen.insert((id, area.to_string())) {
            return Err("Duplicate total".into());
        }
        let procs = integer(&r["procs"])?;
        let combat = integer(&r["combatProcs"])?;
        let seconds = number(&r["combatSeconds"])?;
        if combat > procs || procs > 100_000_000 || (seconds == 0.0 && combat > 0) {
            return Err("Invalid counters".into());
        }
        totals.push(json!({"spellId":id,"group":area,"procs":procs,"combatProcs":combat,"combatSeconds":seconds}));
    }
    if totals.is_empty() || totals.len() > 600 {
        return Err("No supported measurements to upload".into());
    }
    let mut segments = Vec::new();
    for s in entries(&e["history"])? {
        let counts = object(&s["counts"])?;
        let effects = object(&s["effects"])?;
        let mut keys: HashSet<String> = counts.keys().cloned().collect();
        keys.extend(effects.keys().cloned());
        let mut keys: Vec<String> = keys.into_iter().collect();
        keys.sort();
        let mut rows = Vec::new();
        for k in keys {
            let id: u64 = k.parse().map_err(|_| "Invalid spell ID")?;
            if !ids.contains(&id) {
                continue;
            }
            let count = match counts.get(&k) {
                Some(v) => integer(v)?,
                None => 0,
            };
            rows.push(json!({"spellId":id,"procs":count,"eligible":effects.get(&k)==Some(&Value::Bool(true))}));
        }
        let status = string(&s["status"])?;
        if !["active", "complete"].contains(&status) {
            return Err("Invalid segment status".into());
        }
        segments.push(json!({"id":integer(&s["id"])?,"group":group(&s["context"])?,"seconds":number(&s["duration"])?,"status":status,"rows":rows}));
    }
    if segments.len() > 301 {
        return Err("Too many segments".into());
    }
    let mut result = json!({"schemaVersion":1,"addonVersion":version,"characterId":uuid(&e["characterId"])?,"collectionId":uuid(&e["collectionId"])?,"sequence":integer(&e["sequence"])?,"exportedAt":integer(&e["exportedAt"])?,"privacy":if named{"named"}else{"anonymous"},"historyTruncated":e["historyTruncated"].as_bool().ok_or("Invalid history flag")?,"totals":totals,"segments":segments});
    if named {
        for (key, min, max) in [("name", 2, 40), ("realm", 1, 80)] {
            let v = string(&e["character"][key])?;
            if v.chars().count() < min
                || v.chars().count() > max
                || !v.chars().all(|c| c.is_alphabetic() || " '-".contains(c))
            {
                return Err("Invalid character name or realm".into());
            }
            result[key] = json!(v);
        }
    }
    Ok(result)
}
pub fn read_file(path: &Path) -> Result<Value> {
    if path.file_name().and_then(|v| v.to_str()) != Some("GabbaProcTracker.lua") {
        return Err("Select GabbaProcTracker.lua".into());
    }
    let meta = fs::symlink_metadata(path).map_err(|_| "File is unavailable")?;
    if !meta.is_file() || meta.len() > MAX_FILE as u64 {
        return Err("Not a regular export file or too large".into());
    }
    use std::io::Read;
    let mut buf = Vec::new();
    fs::File::open(path)
        .map_err(|_| "Cannot open export")?
        .take((MAX_FILE + 1) as u64)
        .read_to_end(&mut buf)
        .map_err(|_| "Cannot read export")?;
    let after = fs::metadata(path).map_err(|_| "File changed during read")?;
    if after.len() != meta.len() || after.modified().ok() != meta.modified().ok() {
        return Err("WoW is still writing; retry shortly".into());
    }
    parse(std::str::from_utf8(&buf).map_err(|_| "Invalid UTF-8")?)
}
fn dirs(path: &Path) -> Vec<PathBuf> {
    fs::read_dir(path)
        .into_iter()
        .flatten()
        .take(2048)
        .filter_map(|e| {
            let e = e.ok()?;
            if e.file_type().ok()?.is_dir() {
                Some(e.path())
            } else {
                None
            }
        })
        .collect()
}
pub fn roots(home: &Path) -> Vec<PathBuf> {
    let mut out = vec![
        home.join("Faugus/battlenet/drive_c/Program Files (x86)/World of Warcraft"),
        home.join("Games/battlenet/drive_c/Program Files (x86)/World of Warcraft"),
        home.join(".wine/drive_c/Program Files (x86)/World of Warcraft"),
    ];
    #[cfg(target_os = "windows")]
    for drive in 'C'..='Z' {
        for dir in [
            "Program Files (x86)/World of Warcraft",
            "Program Files/World of Warcraft",
            "World of Warcraft",
        ] {
            out.push(PathBuf::from(format!("{drive}:/{dir}")));
        }
    }
    #[cfg(target_os = "macos")]
    {
        out.push(PathBuf::from("/Applications/World of Warcraft"));
        out.push(home.join("Applications/World of Warcraft"));
    }
    for base in [
        home.join(".local/share/Steam/steamapps/compatdata"),
        home.join(".steam/steam/steamapps/compatdata"),
    ] {
        for prefix in dirs(&base).into_iter().take(200) {
            out.push(prefix.join("pfx/drive_c/Program Files (x86)/World of Warcraft"));
        }
    }
    for base in [home.join("Faugus"), home.join("Games")] {
        for prefix in dirs(&base).into_iter().take(100) {
            out.push(prefix.join("drive_c/Program Files (x86)/World of Warcraft"));
        }
    }
    out
}
/// Local-only source labels; these never enter the upload payload.
pub fn source_labels(path: &Path) -> Value {
    let character = path.parent().and_then(Path::parent);
    let realm = character.and_then(Path::parent);
    let installation = path
        .ancestors()
        .find(|p| p.file_name().is_some_and(|n| n == "_classic_era_"));
    json!({
        "sourcePath": path.to_string_lossy(),
        "installationPath": installation.unwrap_or(path).to_string_lossy(),
        "client": "Classic Era / Hardcore",
        "localName": character.and_then(Path::file_name).unwrap_or_default().to_string_lossy(),
        "realm": realm.and_then(Path::file_name).unwrap_or_default().to_string_lossy(),
    })
}

pub fn valid_upload_interval(minutes: u64) -> bool {
    (5..=60).contains(&minutes) && minutes % 5 == 0
}

/// Quote one executable path for a freedesktop Exec field, not a shell command.
pub fn desktop_exec(path: &str) -> std::result::Result<String, String> {
    if path.contains(['\n', '\r', '\0']) {
        return Err("Invalid launcher path".into());
    }
    let mut quoted = String::from("\"");
    for ch in path.chars() {
        match ch {
            '%' => quoted.push_str("%%"),
            '\\' => quoted.push_str("\\\\\\\\"),
            '"' | '$' | '`' => {
                quoted.push_str("\\\\");
                quoted.push(ch);
            }
            _ => quoted.push(ch),
        }
    }
    quoted.push('"');
    Ok(quoted)
}

/// Keep one user launcher pointing at the currently launched application.
pub fn install_desktop_entry(
    data: &Path,
    executable: &Path,
    icon_bytes: &[u8],
) -> std::result::Result<(), Box<dyn std::error::Error>> {
    let exec = desktop_exec(&executable.to_string_lossy())?;
    let applications = data.join("applications");
    let icons = data.join("icons/hicolor/128x128/apps");
    fs::create_dir_all(&applications)?;
    fs::create_dir_all(&icons)?;
    let icon = icons.join("info.kellerkind.gabbaproc.png");
    fs::write(&icon, icon_bytes)?;
    let icon_path = icon
        .to_string_lossy()
        .replace('\\', "\\\\")
        .replace('\n', "\\n")
        .replace('\r', "\\r");
    let entry = format!("[Desktop Entry]\nType=Application\nName=GabbaProc Companion\nComment=Upload your WoW proc exports\nExec={exec}\nIcon={icon_path}\nTerminal=false\nCategories=Utility;\nStartupWMClass=info.kellerkind.gabbaproc\n");
    let temporary = applications.join(format!(".gabbaproc-{}.desktop.tmp", std::process::id()));
    fs::write(&temporary, entry)?;
    fs::rename(
        temporary,
        applications.join("info.kellerkind.gabbaproc.desktop"),
    )?;
    Ok(())
}

/// Move an installed update without overwriting another download.
/// A hard link keeps the operation no-clobber; the old file survives on failure.
pub fn versioned_appimage(current: &Path, version: &str) -> std::result::Result<PathBuf, String> {
    if version.is_empty()
        || version.len() > 64
        || !version.starts_with(|c: char| c.is_ascii_digit())
        || !version
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '-' | '+'))
    {
        return Err("Invalid update version".into());
    }
    if !fs::symlink_metadata(current).is_ok_and(|m| m.is_file()) {
        return Err("AppImage is not a regular file".into());
    }
    let target = current.with_file_name(format!("GabbaProc.Companion_{version}_amd64.AppImage"));
    if target == current {
        return Ok(target);
    }
    fs::hard_link(current, &target).map_err(|_| "Update installed, but the versioned filename already exists or this filesystem cannot rename safely. The original AppImage is still available.")?;
    if fs::remove_file(current).is_err() {
        let _ = fs::remove_file(&target);
        return Err("Cannot rename updated AppImage; original file retained".into());
    }
    Ok(target)
}

pub fn discover(roots: &[PathBuf]) -> Vec<PathBuf> {
    let mut result = HashSet::new();
    let mut visited = 0usize;
    'scan: for root in roots {
        let era = if root.file_name().and_then(|s| s.to_str()) == Some("_classic_era_") {
            root.clone()
        } else {
            root.join("_classic_era_")
        };
        for account in dirs(&era.join("WTF/Account")) {
            visited += 1;
            if visited > 20000 {
                break 'scan;
            }
            for realm in dirs(&account) {
                visited += 1;
                if visited > 20000 {
                    break 'scan;
                }
                for character in dirs(&realm) {
                    visited += 1;
                    if visited > 20000 {
                        break 'scan;
                    }
                    let f = character.join("SavedVariables/GabbaProcTracker.lua");
                    if fs::symlink_metadata(&f)
                        .is_ok_and(|m| m.is_file() && m.len() <= MAX_FILE as u64)
                    {
                        result.insert(f);
                    }
                    if result.len() >= 2000 {
                        break 'scan;
                    }
                }
            }
        }
    }
    let mut out: Vec<_> = result.into_iter().collect();
    out.sort();
    out
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn source_labels_keep_distinct_installations_and_invalid_exports_identifiable() {
        let a = source_labels(Path::new(
            "/games/one/_classic_era_/WTF/Account/A/Realm/Hero/SavedVariables/GabbaProcTracker.lua",
        ));
        let b = source_labels(Path::new(
            "/games/two/_classic_era_/WTF/Account/A/Realm/Hero/SavedVariables/GabbaProcTracker.lua",
        ));
        assert_eq!(a["localName"], "Hero");
        assert_eq!(a["realm"], "Realm");
        assert_eq!(a["client"], "Classic Era / Hardcore");
        assert_ne!(a["installationPath"], b["installationPath"]);
    }
    #[test]
    fn upload_intervals_are_bounded() {
        for n in [5, 15, 60] {
            assert!(valid_upload_interval(n));
        }
        for n in [0, 1, 6, 61, u64::MAX] {
            assert!(!valid_upload_interval(n));
        }
    }
    #[test]
    fn desktop_paths_cannot_inject_fields_or_commands() {
        assert_eq!(
            desktop_exec("/a b/app.AppImage").unwrap(),
            "\"/a b/app.AppImage\""
        );
        assert_eq!(desktop_exec("/a%f/app").unwrap(), "\"/a%%f/app\"");
        assert!(desktop_exec("/a\nExec=bad").is_err());
        assert!(desktop_exec("/a$`\"/app").unwrap().contains("\\\\$"));
    }
    #[test]
    fn launcher_tracks_moved_appimage_without_duplicate_entries() {
        let temp = std::env::temp_dir().join(format!(
            "gabbaproc-launcher-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        install_desktop_entry(&temp, Path::new("/first/GabbaProc.AppImage"), b"icon").unwrap();
        install_desktop_entry(&temp, Path::new("/new folder/GabbaProc.AppImage"), b"icon").unwrap();
        let entries = fs::read_dir(temp.join("applications"))
            .unwrap()
            .collect::<Vec<_>>();
        assert_eq!(entries.len(), 1);
        let text = fs::read_to_string(temp.join("applications/info.kellerkind.gabbaproc.desktop"))
            .unwrap();
        assert!(text.contains("Exec=\"/new folder/GabbaProc.AppImage\""));
        assert!(!text.contains("/first/"));
        assert!(text.contains("StartupWMClass=info.kellerkind.gabbaproc"));
        assert_eq!(
            fs::read(temp.join("icons/hicolor/128x128/apps/info.kellerkind.gabbaproc.png"))
                .unwrap(),
            b"icon"
        );
        fs::remove_dir_all(temp).unwrap();
    }
    #[test]
    fn update_rename_preserves_payload_and_never_overwrites() {
        let temp = std::env::temp_dir().join(format!("gabbaproc-rename-{}", std::process::id()));
        fs::create_dir_all(&temp).unwrap();
        let old = temp.join("custom.AppImage");
        fs::write(&old, b"signed update bytes").unwrap();
        let new = versioned_appimage(&old, "0.1.2").unwrap();
        assert!(!old.exists());
        assert_eq!(fs::read(&new).unwrap(), b"signed update bytes");
        fs::write(&old, b"another download").unwrap();
        assert!(versioned_appimage(&old, "0.1.2").is_err());
        assert_eq!(fs::read(&old).unwrap(), b"another download");
        assert_eq!(fs::read(&new).unwrap(), b"signed update bytes");
        assert!(versioned_appimage(&old, "../../bad").is_err());
        fs::remove_dir_all(temp).unwrap();
    }
    #[test]
    fn accepts_tables_and_utf8() {
        let v=parse("GabbaProcTrackerDB = { [\"test\"] = {1,2,}, name = \"Jäger\", -- comment\n flag=true, }").unwrap();
        assert_eq!(v["test"]["2"], 2);
        assert_eq!(v["name"], "Jäger");
    }
    #[test]
    fn never_executes() {
        for raw in [
            "GabbaProcTrackerDB = os.execute('bad')",
            "GabbaProcTrackerDB = {}; print('bad')",
            "GabbaProcTrackerDB={a=1,a=2}",
            "GabbaProcTrackerDB={a=0/0}",
            "Other = {}",
            "GabbaProcTrackerDB={a=function()end}",
        ] {
            assert!(parse(raw).is_err(), "{raw}");
        }
    }
    #[test]
    fn rejects_depth_and_large_text() {
        assert!(parse(&format!(
            "GabbaProcTrackerDB={}{}",
            "{".repeat(50),
            "}".repeat(50)
        ))
        .is_err());
        assert!(parse(&format!(
            "GabbaProcTrackerDB={{a=\"{}\"}}",
            "x".repeat(9000)
        ))
        .is_err());
    }
    #[test]
    fn anonymity_allowlist() {
        let root = json!({"export":{"schemaVersion":1,"addonVersion":"0.1.0","characterId":"12345678-1234-4234-8234-123456789abc","collectionId":"22345678-1234-4234-8234-123456789abc","sequence":1,"exportedAt":1792320000,"historyTruncated":false,"character":{"name":"Secretname","realm":"Secretrealm"},"totals":{"1":{"spellId":20007,"group":"world","procs":1,"combatProcs":1,"combatSeconds":60.0,"effectName":"LEAK"}},"history":{},"zone":"LEAK","path":"LEAK"}});
        let p = payload(&root, false).unwrap().to_string();
        assert!(!p.contains("Secret") && !p.contains("LEAK"));
        assert_eq!(payload(&root, true).unwrap()["name"], "Secretname");
    }
    #[test]
    fn windows_byte_escapes() {
        let v = parse(r#"GabbaProcTrackerDB = {x="J\195\164ger"}"#).unwrap();
        assert_eq!(v["x"], "Jäger");
    }
}
