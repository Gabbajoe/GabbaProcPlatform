"""Bounded segment analysis. Eligible exposure is the denominator, never raw hits."""
import json
import threading
from fastapi import APIRouter, HTTPException, Request
from .storage import connect
from .models import IDS

router = APIRouter(prefix="/api")
_analysis_slot = threading.BoundedSemaphore(1)

@router.get("/analysis")
def analysis(request: Request, spellId: int, group: str = "all", scope: str = "community", classId: int = 0):
    if not _analysis_slot.acquire(blocking=False):
        raise HTTPException(503, "Analysis busy; retry shortly", headers={"Retry-After":"2"})
    try:
        return calculate(request, spellId, group, scope, classId)
    finally:
        _analysis_slot.release()


def calculate(request, spellId, group, scope, classId):
    if spellId not in IDS or group not in {"all", "world", "party", "raid"} or scope not in {"community", "mine"}:
        raise HTTPException(400, "Invalid analysis filter")
    if classId not in {0,1,2,3,4,5,7,8,9,11}:
        raise HTTPException(400, "Invalid class")
    params = []
    where = "s.status='community'"
    if scope == "mine":
        from .accounts import session
        params.append(session(request))
        where = "EXISTS(SELECT 1 FROM owners o JOIN account_devices a ON a.device=o.device WHERE o.character=g.character AND a.account=?)"
    with connect() as db:
        records = db.execute("SELECT g.character,g.collection,g.id,g.data FROM segments g JOIN snapshots s USING(character,collection) WHERE " + where + " ORDER BY s.updated DESC,g.id DESC LIMIT 501", params).fetchall()
    limited = len(records)>500
    buckets = [{"label":label,"segments":0,"seconds":0.0,"procs":0,"zero":0} for label in ["<30s","30–60s","1–2m","2–5m","5m+"]]
    areas = {a:{"group":a,"segments":0,"seconds":0.0,"procs":0,"zero":0} for a in ["world","party","raid"]}
    points, timeline, contributors = [], [0]*12, set()
    measured, truncated, attacks, crits = 0,0,0,0
    distribution = [0]*11
    for record in records[:500]:
        s=json.loads(record['data'])
        if s['status']!='complete' or s['seconds']<=0 or (group!='all' and s['group']!=group):continue
        t=s.get('telemetry')
        if classId and (not t or t.get('classId')!=classId):continue
        effect=next((r for r in s['rows'] if r['spellId']==spellId and r['eligible']),None)
        if not effect:continue
        seconds,procs=s['seconds'],effect['procs']
        contributors.add(record['character'])
        b=0 if seconds<30 else 1 if seconds<60 else 2 if seconds<120 else 3 if seconds<300 else 4
        for row in [buckets[b],areas[s['group']]]:
            row['segments']+=1;row['seconds']+=seconds;row['procs']+=procs;row['zero']+=procs==0
        distribution[min(procs,10)]+=1
        if len(points)<1000:
            stats=t['samples'][0]['stats'] if t else {}
            points.append({'seconds':seconds,'procs':procs,'group':s['group'],'ppm':procs*60/seconds,'meleeCrit':stats.get('meleeCrit'),'mainSpeed':stats.get('mainSpeed')})
        t=s.get('telemetry')
        if t:
            measured+=1;truncated+=bool(t['truncated'])
            if not t['truncated']:
                for p in t['procTimes']:
                    if p['spellId']==spellId:timeline[min(p['atMs']//30000,11)]+=1
                for a in t['attacks']:
                    if a['kind']!='cast':attacks+=a['count'];crits+=a['count'] if a['outcome']=='crit' else 0
    for row in buckets+list(areas.values()):
        row['ppm']=row['procs']*60/row['seconds'] if row['seconds'] else None
        row['zeroPercent']=row['zero']*100/row['segments'] if row['segments'] else None
    return {'buckets':buckets,'areas':list(areas.values()),'points':points,'distribution':distribution,'timeline':timeline,
        'meta':{'scope':scope,'scanned':min(len(records),500),'limited':limited,'contributors':len(contributors),'telemetrySegments':measured,'truncatedTelemetrySegments':truncated,'observedDamageEvents':attacks,'observedCritEvents':crits,'pointLimit':1000}}
