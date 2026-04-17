import pytest
from app import create_app
from app.extensions import db as _db
from app.auth.models import Tenant, User
from app.configuracion.models import ConfigConsultorio
from app.ajustes.models import DistribucionConfig


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def tenant_and_user(db):
    tenant = Tenant(name="Test Clinic", slug="test-clinic")
    db.session.add(tenant)
    db.session.flush()

    user = User(
        tenant_id=tenant.id,
        email="admin@test.com",
        name="Admin Test",
        role="admin",
    )
    user.set_password("password123")
    db.session.add(user)

    config = ConfigConsultorio(
        tenant_id=tenant.id,
        gastos_fijos=50000,
        horas_lunes=8, horas_martes=8, horas_miercoles=8,
        horas_jueves=8, horas_viernes=8, horas_sabado=6, horas_domingo=0,
        numero_unidades=2,
    )
    db.session.add(config)

    dist = DistribucionConfig(tenant_id=tenant.id)
    db.session.add(dist)

    db.session.commit()
    return tenant, user


@pytest.fixture
def auth_headers(client, tenant_and_user):
    _, user = tenant_and_user
    resp = client.post("/api/v1/auth/login", json={
        "email": "admin@test.com",
        "password": "password123",
    })
    token = resp.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
