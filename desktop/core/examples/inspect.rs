//! Explicit developer utility: print the exact allowlisted upload JSON for one file.
fn main() {
    let path = std::env::args()
        .nth(1)
        .expect("Usage: inspect /path/to/GabbaProcTracker.lua [--named]");
    let named = std::env::args().any(|a| a == "--named");
    let result = gabbaproc_core::read_file(std::path::Path::new(&path))
        .and_then(|v| gabbaproc_core::payload(&v, named));
    match result {
        Ok(v) => println!("{}", serde_json::to_string_pretty(&v).unwrap()),
        Err(e) => {
            eprintln!("{e}");
            std::process::exit(1);
        }
    }
}
