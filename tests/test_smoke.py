from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    r = client.get('/api/health')
    assert r.status_code == 200
    assert r.json()['status'] == 'ok'

def test_home():
    r = client.get('/')
    assert r.status_code == 200
    assert 'Qtalk' in r.text

def test_otp_login_and_phone_search():
    a = client.post('/api/auth/send-otp', json={'phone': '+91 9787609729'}).json()
    va = client.post('/api/auth/verify-otp', json={'phone': '+91 9787609729', 'otp': a['dev_otp'], 'name': 'Elangovan'}).json()
    b = client.post('/api/auth/send-otp', json={'phone': '9585373416'}).json()
    vb = client.post('/api/auth/verify-otp', json={'phone': '9585373416', 'otp': b['dev_otp'], 'name': 'Palraj'}).json()
    client.headers.update({'Authorization': 'Bearer ' + vb['token']})
    for q in ['Elangovan', '9787609729', '+91 9787609729', '97876-09729']:
        r = client.get('/api/users/search', params={'q': q})
        assert r.status_code == 200
        assert any(x['phone'] == '9787609729' for x in r.json())
