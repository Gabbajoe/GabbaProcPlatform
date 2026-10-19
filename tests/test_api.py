import copy,json,time,uuid
import pytest
from fastapi.testclient import TestClient
from server.app import app
from server.storage import invite,connect
@pytest.fixture
def api(tmp_path,monkeypatch):
    monkeypatch.setenv('GABBAPROC_DB',str(tmp_path/'db.sqlite3'))
    with TestClient(app) as c:
        token=c.post('/api/enroll',json={'invite':invite()}).json()['token']
        c.headers['Authorization']='Bearer '+token
        yield c
@pytest.fixture
def sample():
    return {'schemaVersion':1,'addonVersion':'0.1.0','characterId':str(uuid.uuid4()),'collectionId':str(uuid.uuid4()),'sequence':1,'exportedAt':int(time.time()),'privacy':'anonymous','historyTruncated':False,'totals':[{'spellId':20007,'group':'world','procs':2,'combatProcs':2,'combatSeconds':120.0}],'segments':[{'id':1,'group':'world','seconds':120.0,'status':'complete','rows':[{'spellId':20007,'procs':2,'eligible':True}]}]}
def test_import_dedup_update_and_weighted_rate(api,sample):
    assert api.post('/api/imports',json=sample).json()['status']=='accepted'
    assert api.post('/api/imports',json=sample).json()['status']=='duplicate'
    data=api.get('/api/stats').json();assert data['rows'][0]['ppm']==1
    sample['sequence']=2;sample['totals'][0]['combatSeconds']=240.0
    assert api.post('/api/imports',json=sample).status_code==200
    assert api.get('/api/stats').json()['rows'][0]['ppm']==0.5
    sample['sequence']=1;assert api.post('/api/imports',json=sample).status_code==409
@pytest.mark.parametrize('mutate',[
 lambda x:x.update(privacy='anonymous',name='Private'),
 lambda x:x.update(unexpected='evil'),
 lambda x:x['totals'][0].update(procs=-1),
 lambda x:x['totals'][0].update(spellId=999999),
 lambda x:x['totals'][0].update(combatSeconds=0.0),
 lambda x:x['totals'].append(x['totals'][0]),
 lambda x:x['segments'][0]['rows'][0].update(procs=3),
 lambda x:x.update(privacy='named',name='<script>',realm='Realm'),
 lambda x:x['totals'][0].update(procs=True),
])
def test_invalid_payloads(api,sample,mutate):
    mutate(sample);assert api.post('/api/imports',json=sample).status_code==422
    assert api.get('/api/stats').json()['meta']['collections']==0

def test_identity_and_privacy(api,sample):
    sample.update(privacy='named',name='Tester',realm='Test Realm')
    assert api.post('/api/imports',json=sample).status_code==200
    assert api.get('/api/stats').json()['contributors']==[{'name':'Tester','realm':'Test Realm'}]
    public=api.get('/api/stats').text
    assert sample['characterId'] not in public and sample['collectionId'] not in public
    assert api.post('/api/privacy',json={'characterId':sample['characterId']}).status_code==200
    assert api.get('/api/stats').json()['contributors']==[]
    other=api.post('/api/enroll',json={'invite':invite()}).json()['token']
    assert api.post('/api/imports',json=sample,headers={'Authorization':'Bearer '+other}).status_code==409
    assert api.delete('/api/device').status_code==200
    assert api.get('/api/stats').json()['meta']['collections']==0
    assert api.post('/api/imports',json=sample).status_code==401

def test_invites_single_use_and_unknown(api):
    code=invite();assert api.post('/api/enroll',json={'invite':code}).status_code==200
    assert api.post('/api/enroll',json={'invite':code}).status_code==403

def test_quarantine_and_counter_regression(api,sample):
    sample['segments']=[];sample['totals'][0].update(procs=500,combatProcs=500,combatSeconds=1.0)
    assert api.post('/api/imports',json=sample).json()['review']=='quarantine'
    assert api.get('/api/stats').json()['rows']==[]
    sample['sequence']=2;sample['totals'][0]['procs']=499
    assert api.post('/api/imports',json=sample).status_code==422
    sample['totals'][0]['combatProcs']=499
    assert api.post('/api/imports',json=sample).status_code==409

def test_body_limits_and_duplicate_keys(api):
    assert api.post('/api/imports',content=b'a'*(2*1024*1024+1),headers={'Content-Type':'application/json'}).status_code==413
    assert api.post('/api/imports',content='{"a":1,"a":2}',headers={'Content-Type':'application/json'}).status_code==400
    assert api.post('/api/imports',content='{"a":NaN}',headers={'Content-Type':'application/json'}).status_code==400
    assert api.post('/api/imports',content='print(123)').status_code==415
