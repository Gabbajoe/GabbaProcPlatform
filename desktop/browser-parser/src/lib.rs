//! Browser worker ABI. Uses the same non-executing parser and projection as the companion.
//! Allocations are owned by the worker and released before its termination.
#[no_mangle]
pub extern "C" fn allocate(len: usize) -> *mut u8 {
    if len > gabbaproc_core::MAX_FILE { return std::ptr::null_mut(); }
    Box::into_raw(vec![0u8; len].into_boxed_slice()) as *mut u8
}
#[no_mangle]
pub unsafe extern "C" fn release(ptr: *mut u8, len: usize) {
    if !ptr.is_null() { drop(Box::from_raw(std::ptr::slice_from_raw_parts_mut(ptr, len))); }
}
#[no_mangle]
pub unsafe extern "C" fn parse_export(ptr: *const u8, len: usize, named: u32) -> u64 {
    let result = if len > gabbaproc_core::MAX_FILE || ptr.is_null() {
        Err("File too large".to_string())
    } else {
        std::str::from_utf8(std::slice::from_raw_parts(ptr, len))
            .map_err(|_| "Invalid UTF-8".to_string())
            .and_then(gabbaproc_core::parse)
            .and_then(|root| gabbaproc_core::payload_batches(&root, named != 0))
    };
    let json = match result {
        Ok(packets) => serde_json::json!({"packets": packets}),
        Err(error) => serde_json::json!({"error": error}),
    };
    let output = serde_json::to_vec(&json).unwrap().into_boxed_slice();
    let size = output.len() as u64;
    let address = Box::into_raw(output) as *mut u8 as u64;
    (address << 32) | size
}
