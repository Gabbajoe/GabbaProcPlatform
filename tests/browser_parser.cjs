const fs=require('node:fs'),assert=require('node:assert/strict');
const fixture={export:{schemaVersion:2,addonVersion:'0.1.3',characterId:'12345678-1234-4234-8234-123456789abc',collectionId:'22345678-1234-4234-8234-123456789abc',sequence:1,exportedAt:1792530000,historyTruncated:false,character:{name:'Privatechar',realm:'Privaterealm'},totals:[{spellId:20007,group:'world',procs:1,combatProcs:1,combatSeconds:60,effectName:'UNWANTED'}],history:[],path:'UNWANTED'}};
function lua(o){if(Array.isArray(o))return '{'+o.map(lua).join(',')+'}';if(o&&typeof o==='object')return '{'+Object.entries(o).map(([k,v])=>'['+JSON.stringify(k)+']='+lua(v)).join(',')+'}';return JSON.stringify(o);}
(async()=>{
 const {instance}=await WebAssembly.instantiate(fs.readFileSync(process.argv[2]||'web/assets/export-parser.wasm'));
 const a=instance.exports;
 function parse(text,named){const bytes=Buffer.from(text),ptr=a.allocate(bytes.length);new Uint8Array(a.memory.buffer,ptr,bytes.length).set(bytes);const result=a.parse_export(ptr,bytes.length,named);a.release(ptr,bytes.length);const out=Number(result>>32n),len=Number(result&0xffffffffn);const decoded=JSON.parse(new TextDecoder().decode(new Uint8Array(a.memory.buffer,out,len)));a.release(out,len);return decoded;}
 const text='GabbaProcTrackerDB='+lua(fixture);
 const anonymous=parse(text,0);assert.equal(anonymous.packets[0].privacy,'anonymous');assert(!JSON.stringify(anonymous).includes('Private'));assert(!JSON.stringify(anonymous).includes('UNWANTED'));
 assert.equal(parse(text,1).packets[0].name,'Privatechar');
 for(const invalid of ['GabbaProcTrackerDB=os.execute("bad")',text+';print("bad")','GabbaProcTrackerDB={a=1,a=2}','GabbaProcTrackerDB={}'])assert(parse(invalid,0).error);
 assert.equal(a.allocate(64*1024*1024+1),0);
 console.log('PASS: WebAssembly privacy projection, supported export, invalid/executable Lua rejection and size limit');
})().catch(e=>{console.error(e);process.exit(1)});
