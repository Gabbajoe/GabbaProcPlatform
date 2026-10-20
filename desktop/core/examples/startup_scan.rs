use std::{path::PathBuf, time::Instant};
fn main() {
    let home = PathBuf::from(std::env::args().nth(1).expect("Home directory required"));
    let start = Instant::now();
    let paths = gabbaproc_core::discover(&gabbaproc_core::roots(&home));
    let discovery = start.elapsed();
    let mut valid = 0;
    for path in &paths {
        if let Ok(raw) = gabbaproc_core::read_file(path) {
            if gabbaproc_core::payload(&raw, false).is_ok() {
                valid += 1;
            }
        }
    }
    println!(
        "files={} valid={} discovery_ms={} total_ms={}",
        paths.len(),
        valid,
        discovery.as_millis(),
        start.elapsed().as_millis()
    );
}
