import hashlib,json,os,secrets,time
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import JSONResponse,FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from .models import Upload,CATALOG
from .storage import init,connect,digest

@asynccontextmanager
async def lifespan(app):
    init()
    yield
app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
MAX_BODY=2*1024*1024
@app.middleware('http')
async def headers(request,call_next):
    response=await call_next(request)
    response.headers.update({'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','Cache-Control':'no-store','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",'Permissions-Policy':'camera=(), microphone=(), geolocation=()'})
    return response

def unique(pairs):
    result={}
    for k,v in pairs:
        if k in result: raise ValueError('duplicate key')
        result[k]=v
    return result
async def body(request):
    if request.headers.get('content-type','').split(';')[0]!='application/json': raise HTTPException(415,'JSON required')
    if request.headers.get('content-encoding','identity')!='identity': raise HTTPException(415,'compressed bodies not accepted')
    parts=[]; size=0
    async for chunk in request.stream():
        size+=len(chunk)
        if size>MAX_BODY: raise HTTPException(413,'Upload too large')
        parts.append(chunk)
    try:
        result=json.loads(b''.join(parts),object_pairs_hook=unique,parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if not isinstance(result,dict): raise ValueError()
        return result
    except (ValueError,UnicodeError,RecursionError): raise HTTPException(400,'Invalid JSON')
def rate(key,maximum,period=3600):
    now=int(time.time())
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM limits WHERE started < ?', (now-86400,))
        old=db.execute('SELECT * FROM limits WHERE key=?',(key,)).fetchone()
        if old and now-old['started']<period:
            if old['count']>=maximum: raise HTTPException(429,'Please retry later',headers={'Retry-After':str(period)})
            db.execute('UPDATE limits SET count=count+1 WHERE key=?',(key,))
        else: db.execute('INSERT OR REPLACE INTO limits VALUES(?,?,1)',(key,now))
        db.commit()
def device(request):
    auth=request.headers.get('authorization','')
    if not auth.startswith('Bearer ') or not 30<len(auth)<150: raise HTTPException(401,'Upload token required')
    with connect() as db: row=db.execute('SELECT id FROM devices WHERE token_hash=? AND revoked=0',(digest(auth[7:]),)).fetchone()
    if not row: raise HTTPException(401,'Upload token invalid or revoked')
    rate('device:'+row['id'],120)
    return row['id']
@app.get('/api/health')
def health(): return {'ok':True,'schemaVersion':1}
@app.post('/api/enroll')
async def enroll(request:Request):
    # Invites are single-use, expire after a day, and are issued by the operator.
    # Public automated registration is deliberately not enabled without abuse controls.
    rate('enroll:'+digest(request.client.host),10)
    data=await body(request)
    if set(data)!={'invite'} or not isinstance(data['invite'],str) or len(data['invite'])>100: raise HTTPException(400,'Invalid invite')
    token=secrets.token_urlsafe(32); did=secrets.token_hex(16)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        updated=db.execute('UPDATE invites SET used=1 WHERE hash=? AND used=0 AND expires>?',(digest(data['invite']),int(time.time()))).rowcount
        if not updated: raise HTTPException(403,'Invite expired or already used')
        db.execute('INSERT INTO devices(id,token_hash,created) VALUES(?,?,?)',(did,digest(token),int(time.time())))
        db.commit()
    return {'token':token}
@app.post('/api/imports')
async def upload(request:Request):
    did=device(request)
    try: data=Upload.model_validate(await body(request))
    except (ValidationError,ValueError): raise HTTPException(422,'Invalid export fields, counters or history')
    if data.exportedAt>time.time()+86400: raise HTTPException(422,'Export is dated in the future')
    content=json.dumps(data.model_dump(exclude_none=True,exclude={'privacy','name','realm'}),sort_keys=True,separators=(',',':'))
    checksum=digest(content)
    suspicious=any((r.combatSeconds>0 and r.combatProcs*60/r.combatSeconds>600) or (r.combatSeconds==0 and r.procs>1000) for r in data.totals)
    status='quarantine' if suspicious else 'community'
    key=(data.characterId,data.collectionId)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        owner=db.execute('SELECT * FROM owners WHERE character=?',(data.characterId,)).fetchone()
        if owner and owner['device']!=did: raise HTTPException(409,'Character belongs to another upload device; contact operator to transfer')
        old=db.execute('SELECT * FROM snapshots WHERE character=? AND collection=?',key).fetchone()
        if old and data.sequence<old['sequence']: raise HTTPException(409,'Older snapshot')
        if old and data.sequence==old['sequence']:
            if old['digest']!=checksum: raise HTTPException(409,'Sequence reused with different content')
            db.execute('UPDATE owners SET privacy=?,name=?,realm=? WHERE character=? AND device=?',(data.privacy,data.name,data.realm,data.characterId,did))
            db.commit()
            return {'status':'duplicate','review':old['status']}
        if not old:
            if db.execute('SELECT COUNT(*) FROM snapshots s JOIN owners o ON o.character=s.character WHERE o.device=?',(did,)).fetchone()[0]>=200: raise HTTPException(429,'Collection limit reached')
        if old:
            incoming={(r.spellId,r.group):r for r in data.totals}
            for previous in db.execute('SELECT * FROM totals WHERE character=? AND collection=?',key):
                new=incoming.get((previous['spell'],previous['area']))
                if not new or new.procs<previous['procs'] or new.combatProcs<previous['combat'] or new.combatSeconds+0.01<previous['seconds']: raise HTTPException(409,'Counters decreased within collection')
        db.execute('INSERT INTO owners VALUES(?,?,?,?,?) ON CONFLICT(character) DO UPDATE SET privacy=excluded.privacy,name=excluded.name,realm=excluded.realm',(data.characterId,did,data.privacy,data.name,data.realm))
        db.execute('INSERT INTO snapshots VALUES(?,?,?,?,?,?,?) ON CONFLICT(character,collection) DO UPDATE SET sequence=excluded.sequence,digest=excluded.digest,status=excluded.status,exported=excluded.exported,updated=excluded.updated',(*key,data.sequence,checksum,status,data.exportedAt,int(time.time())))
        db.execute('DELETE FROM totals WHERE character=? AND collection=?',key)
        db.executemany('INSERT INTO totals VALUES(?,?,?,?,?,?,?)',[(*key,r.spellId,r.group,r.procs,r.combatProcs,r.combatSeconds) for r in data.totals])
        # Keep the supplied rolling window, not an unbounded attacker-controlled archive.
        # Full cumulative totals remain; the web app explicitly reports this limitation.
        db.execute('DELETE FROM segments WHERE character=? AND collection=?',key)
        db.executemany('INSERT INTO segments VALUES(?,?,?,?,?)',[(*key,s.id,data.sequence,json.dumps(s.model_dump())) for s in data.segments])
        db.commit()
    return {'status':'accepted','review':status,'sequence':data.sequence}
@app.post('/api/privacy')
async def privacy(request:Request):
    did=device(request);data=await body(request)
    if set(data)!={'characterId'} or not isinstance(data['characterId'],str): raise HTTPException(400,'characterId required')
    with connect() as db:
        n=db.execute('UPDATE owners SET privacy="anonymous",name=NULL,realm=NULL WHERE character=? AND device=?',(data['characterId'],did)).rowcount
    if not n: raise HTTPException(404,'Character not found')
    return {'status':'anonymous'}
@app.delete('/api/device')
def remove_device(request:Request):
    did=device(request)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        chars=[r[0] for r in db.execute('SELECT character FROM owners WHERE device=?',(did,))]
        for char in chars:
            db.execute('DELETE FROM snapshots WHERE character=?',(char,))
        db.execute('DELETE FROM owners WHERE device=?',(did,))
        db.execute('UPDATE devices SET revoked=1 WHERE id=?',(did,));db.commit()
    return {'status':'deleted'}
@app.get('/api/stats')
def stats():
    with connect() as db:
        rows=db.execute('''SELECT t.spell,t.area,SUM(t.procs) procs,SUM(t.combat) combat,SUM(t.seconds) seconds,COUNT(DISTINCT t.character) contributors FROM totals t JOIN snapshots s USING(character,collection) WHERE s.status='community' GROUP BY t.spell,t.area ORDER BY t.spell,t.area''').fetchall()
        meta=dict(db.execute("SELECT COUNT(*) collections,COUNT(DISTINCT character) contributors,MAX(updated) updated FROM snapshots WHERE status='community'").fetchone())
        names=[dict(r) for r in db.execute("SELECT DISTINCT o.name,o.realm FROM owners o JOIN snapshots s ON s.character=o.character WHERE o.privacy='named' AND s.status='community' ORDER BY o.name LIMIT 100")]
    return {'meta':meta,'rows':[{'spellId':r['spell'],'name':CATALOG[str(r['spell'])],'group':r['area'],'procs':r['procs'],'combatProcs':r['combat'],'seconds':r['seconds'],'contributors':r['contributors'],'ppm':r['combat']*60/r['seconds'] if r['seconds'] else None} for r in rows], 'contributors':names}
ROOT=Path(__file__).resolve().parents[1]/'web'
app.mount('/assets',StaticFiles(directory=ROOT/'assets',check_dir=False),name='assets')
@app.get('/')
def index(): return FileResponse(ROOT/'index.html')
