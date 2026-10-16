import os
import tempfile
import pytest

sandbox=tempfile.TemporaryDirectory(prefix='atlas-tests-')
os.environ.update(DATA_DIR=sandbox.name,SECRET_KEY='test-only-key-32chars-never-production',ADMIN_PASSWORD='test-only-admin-password-16chars',PUBLIC_ORIGIN='http://testserver')
from backend.app import main
from fastapi.testclient import TestClient

@pytest.fixture
def client():
    main.Base.metadata.drop_all(main.engine)
    main.limits.clear()
    with TestClient(main.app) as c:
        yield c

@pytest.fixture
def admin(client):
    r=client.post('/api/admin/login',json={'username':'admin','password':os.environ['ADMIN_PASSWORD']})
    assert r.status_code==200
    client.headers['X-CSRF-Token']=r.json()['csrf']
    return client
