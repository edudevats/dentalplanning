class TestAuth:
    def test_register(self, client):
        resp = client.post("/api/v1/auth/register", json={
            "tenant_name": "Mi Consultorio",
            "tenant_slug": "mi-consultorio",
            "email": "doc@test.com",
            "password": "secret123",
            "name": "Dr. Test",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert "access_token" in data
        assert data["tenant"]["slug"] == "mi-consultorio"
        assert data["user"]["role"] == "admin"

    def test_register_duplicate_slug(self, client):
        client.post("/api/v1/auth/register", json={
            "tenant_name": "Clinic AA", "tenant_slug": "dup",
            "email": "a@test.com", "password": "secret123", "name": "Dr AA",
        })
        resp = client.post("/api/v1/auth/register", json={
            "tenant_name": "Clinic BB", "tenant_slug": "dup",
            "email": "b@test.com", "password": "secret123", "name": "Dr BB",
        })
        assert resp.status_code == 409

    def test_login(self, client, tenant_and_user):
        resp = client.post("/api/v1/auth/login", json={
            "email": "admin@test.com",
            "password": "password123",
        })
        assert resp.status_code == 200
        assert "access_token" in resp.get_json()

    def test_login_wrong_password(self, client, tenant_and_user):
        resp = client.post("/api/v1/auth/login", json={
            "email": "admin@test.com",
            "password": "wrong",
        })
        assert resp.status_code == 401

    def test_me(self, client, auth_headers):
        resp = client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.get_json()["email"] == "admin@test.com"

    def test_invite_user(self, client, auth_headers):
        resp = client.post("/api/v1/auth/invite", json={
            "email": "editor@test.com",
            "name": "Editor",
            "role": "editor",
            "password": "secret123",
        }, headers=auth_headers)
        assert resp.status_code == 201
        assert resp.get_json()["user"]["role"] == "editor"

    def test_protected_without_token(self, client):
        resp = client.get("/api/v1/materiales")
        assert resp.status_code == 401
