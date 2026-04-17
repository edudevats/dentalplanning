from app.catalogo.models import Material


class TestTratamientos:
    def _create_material(self, db, tenant_id, nombre="GUANTES", costo=170, unidades=50):
        mat = Material(
            tenant_id=tenant_id,
            nombre=nombre,
            es_medible=True,
            costo_paquete=costo,
            unidades_paquete=unidades,
        )
        db.session.add(mat)
        db.session.commit()
        return mat

    def test_crear_tratamiento(self, client, auth_headers, db, tenant_and_user):
        tenant, _ = tenant_and_user
        mat = self._create_material(db, tenant.id)

        resp = client.post("/api/v1/tratamientos", json={
            "nombre": "RESINA_TEST",
            "horas_invertidas": 1.0,
            "precio_paciente": 1200,
            "comision_bancaria_pct": 5,
            "comision_especialista_tipo": "porcentaje",
            "comision_especialista_valor": 35,
            "materiales": [{"material_id": mat.id, "cantidad": 2}],
        }, headers=auth_headers)

        assert resp.status_code == 201
        data = resp.get_json()
        assert data["nombre"] == "RESINA_TEST"
        assert "calculos" in data
        assert data["calculos"]["comision_bancaria"] == 60.0
        assert data["calculos"]["comision_especialista"] == 420.0
        assert len(data["materiales"]) == 1

    def test_listar_tratamientos(self, client, auth_headers, db, tenant_and_user):
        tenant, _ = tenant_and_user
        mat = self._create_material(db, tenant.id)
        client.post("/api/v1/tratamientos", json={
            "nombre": "TX1", "precio_paciente": 1000, "materiales": [],
        }, headers=auth_headers)
        client.post("/api/v1/tratamientos", json={
            "nombre": "TX2", "precio_paciente": 2000, "materiales": [],
        }, headers=auth_headers)

        resp = client.get("/api/v1/tratamientos", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.get_json()) == 2

    def test_duplicar_tratamiento(self, client, auth_headers, db, tenant_and_user):
        tenant, _ = tenant_and_user
        mat = self._create_material(db, tenant.id)

        resp = client.post("/api/v1/tratamientos", json={
            "nombre": "ORIGINAL",
            "precio_paciente": 1000,
            "materiales": [{"material_id": mat.id, "cantidad": 1}],
        }, headers=auth_headers)
        tx_id = resp.get_json()["id"]

        resp = client.post(f"/api/v1/tratamientos/{tx_id}/duplicar", headers=auth_headers)
        assert resp.status_code == 201
        assert "copia" in resp.get_json()["nombre"]

    def test_simular_precio(self, client, auth_headers, db, tenant_and_user):
        resp = client.post("/api/v1/tratamientos", json={
            "nombre": "SIM_TEST",
            "precio_paciente": 1000,
            "materiales": [],
        }, headers=auth_headers)
        tx_id = resp.get_json()["id"]

        resp = client.post(f"/api/v1/tratamientos/{tx_id}/simular", json={
            "precio_paciente": 2000,
        }, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.get_json()["precio_paciente"] == 2000

        # Verify original not changed
        resp = client.get(f"/api/v1/tratamientos/{tx_id}", headers=auth_headers)
        assert resp.get_json()["precio_paciente"] == 1000
