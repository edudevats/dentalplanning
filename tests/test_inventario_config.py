from app.configuracion.models import ConfigConsultorio


def test_config_tiene_dias_alerta_caducidad(app, db, tenant_and_user):
    tenant, _ = tenant_and_user
    cfg = ConfigConsultorio.query.filter_by(tenant_id=tenant.id).first()
    assert cfg.dias_alerta_caducidad == 30
