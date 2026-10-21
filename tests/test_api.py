from fastapi.testclient import TestClient
from backend.main import app
from backend.core import geojson,MODELS

def test_health():
    with TestClient(app) as c:
        r=c.get('/api/health');assert r.status_code==200;assert set(r.json()['models'])==set(MODELS)
def test_model_validation():
    with TestClient(app) as c:
        r=c.post('/api/analyze',data={'model':'fake'},files={'file':('a.png',b'bad','image/png')});assert r.status_code==422
def test_geojson_no_fake_gps():
    d={'id':1,'polygon':[[1,2],[3,4],[5,6]]}
    assert geojson([d])['features'][0]['geometry'] is None
    assert geojson([d],-12,-77)['features'][0]['geometry']['coordinates']==[-77,-12]
