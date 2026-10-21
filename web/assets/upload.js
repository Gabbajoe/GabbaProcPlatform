"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const tr = (en,de) => document.documentElement.lang === 'de' ? de : en;
  let packets = [], worker, generation=0, busy=false;
  const show = text => $('export-status').textContent=text;
  async function prepare() {
    const current = ++generation;
    worker?.terminate(); packets=[]; $('export-upload').disabled=true; $('export-progress').hidden=true;
    $('export-preview').textContent=''; $('export-summary').textContent='';
    const file=$('export-file').files[0]; if (!file) return;
    if(file.size>64*1024*1024) {show(tr('File exceeds 64 MiB.','Datei ist größer als 64 MiB.'));return;}
    show(tr('Reading locally…','Wird lokal gelesen…'));
    worker=new Worker('/assets/export-worker.js');
    const timeout=setTimeout(()=>{worker.terminate(); if(current===generation)show(tr('File processing timed out.','Zeitlimit beim Einlesen erreicht.'));},30000);
    worker.onerror=()=>{clearTimeout(timeout);show(tr('Cannot load export parser.','Export-Parser konnte nicht geladen werden.'));worker.terminate();};
    worker.onmessage=({data})=>{
      clearTimeout(timeout);worker.terminate();if(current!==generation)return;
      if(data.error){show(tr('Invalid or missing export. Export in WoW and /reload first.','Ungültiger oder fehlender Export. Zuerst in WoW exportieren und /reload ausführen.'));return;}
      packets=data.packets;
      const identity=packets[0];
      $('export-summary').textContent=($('export-named').checked ? `${identity.name} · ${identity.realm}`:tr('Anonymous character','Anonymer Charakter')+' '+identity.characterId.slice(0,8))+` · ${packets.length} `+tr('packets','Pakete');
      // Preview is the actual allowlisted wire payload, never the raw file.
      $('export-preview').textContent=JSON.stringify({packets},null,2);
      $('export-upload').disabled=false;
      show(tr('Ready. Review the preview, then upload.','Bereit. Vorschau prüfen, dann hochladen.'));
    };
    worker.postMessage({file,named:$('export-named').checked});
  }
  async function request(path, packet) {
    const response=await fetch('/api/account/upload-jobs'+path,{method:packet?'POST':'GET',headers:packet?{'Content-Type':'application/json'}:{},body:packet?JSON.stringify(packet):undefined});
    if(!response.ok)throw new Error(response.status===401?tr('Please sign in, then select the file again.','Bitte anmelden und die Datei erneut auswählen.'):response.status===409?tr('Link your existing upload access to this account before retrying.','Zuerst den bisherigen Upload-Zugang mit diesem Konto verknüpfen.'):tr('Upload failed. Retry later; confirmed packets will not be counted twice.','Upload fehlgeschlagen. Später erneut versuchen; bestätigte Pakete werden nicht doppelt gezählt.'));
    return response.json();
  }
  $('export-file').addEventListener('change',prepare);
  $('export-named').addEventListener('change',prepare);
  $('export-upload').addEventListener('click',async()=>{
    if(busy||!packets.length)return;
    busy=true;for(const id of ['export-upload','export-file','export-named'])$(id).disabled=true;
    const progress=$('export-progress'); progress.hidden=false;progress.max=packets.length*2;progress.value=0;
    try {
      const jobs=[];
      for(const packet of packets){jobs.push(await request('',packet));progress.value++;show(tr('Uploaded','Hochgeladen')+` ${jobs.length}/${packets.length}`);}
      const deadline=Date.now()+15*60*1000;
      while(true){
        let done=0;
        for(let i=0;i<jobs.length;i++){
          if(jobs[i].status!=='processed')jobs[i]=await request('/'+encodeURIComponent(jobs[i].jobId));
          if(['rejected','cancelled'].includes(jobs[i].status))throw new Error(tr('Server could not import this export. Check account ownership and export version.','Server konnte den Export nicht importieren. Kontozuordnung und Exportversion prüfen.'));
          if(jobs[i].status==='processed')done++;
        }
        progress.value=packets.length+done;show(tr('Uploaded. Processed by server:','Hochgeladen. Vom Server verarbeitet:')+` ${done}/${packets.length}`);
        if(done===packets.length)break;
        if(Date.now()>deadline)throw new Error(tr('Still queued. You may retry the same file later without double counting.','Noch in der Warteschlange. Dieselbe Datei kann später ohne Doppelzählung erneut hochgeladen werden.'));
        await new Promise(r=>setTimeout(r,5000));
      }
      show(tr('Upload complete — confirmed by server.','Upload abgeschlossen — vom Server bestätigt.'));
    }catch(error){show(error.message);}
    finally{busy=false;for(const id of ['export-upload','export-file','export-named'])$(id).disabled=false;}
  });
  addEventListener('beforeunload',event=>{if(busy){event.preventDefault();event.returnValue='';}});
})();
