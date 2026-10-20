fn main() {
    let path = std::env::args().nth(1).expect("SavedVariables fixture path required");
    let root = gabbaproc_core::read_file(std::path::Path::new(&path)).expect("Parse SavedVariables");
    let packets = gabbaproc_core::payload_batches(&root, false).expect("Build anonymous packets");
    println!("{}", serde_json::to_string(&packets).unwrap());
}
