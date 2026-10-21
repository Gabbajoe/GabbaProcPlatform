"use strict";
onmessage = async ({data}) => {
  try {
    if (data.file.size > 64 * 1024 * 1024) throw new Error("File exceeds 64 MiB");
    const {instance} = await WebAssembly.instantiate(await (await fetch('/assets/export-parser.wasm')).arrayBuffer());
    const api = instance.exports;
    const bytes = new Uint8Array(await data.file.arrayBuffer());
    const address = api.allocate(bytes.length);
    if (!address) throw new Error('Cannot allocate file buffer');
    new Uint8Array(api.memory.buffer, address, bytes.length).set(bytes);
    const result = api.parse_export(address, bytes.length, data.named ? 1 : 0);
    api.release(address, bytes.length);
    const pointer = Number(result >> 32n), size = Number(result & 0xffffffffn);
    const output = JSON.parse(new TextDecoder('utf-8', {fatal:true}).decode(new Uint8Array(api.memory.buffer,pointer,size)));
    api.release(pointer,size);
    postMessage(output);
  } catch (_) {
    postMessage({error:'Cannot read this export. Select GabbaProcTracker.lua after exporting and reloading WoW.'});
  }
};
