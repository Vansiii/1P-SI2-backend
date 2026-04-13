"""
Tests for authentication endpoints.
"""
import pytest
from datetime import date


class TestAuthEndpoints:
    """Test authentication endpoints."""
    
    def test_register_client_success(self, client):
        """Test successful client registration."""
        client_data = {
            "email": "newclient@test.com",
            "password": "StrongPassword123!",
            "direccion": "New Address 456",
            "ci": "11111111",
            "fecha_nacimiento": "1995-05-15"
        }
        
        response = client.post("/api/v1/auth/register/client", json=client_data)
        
        assert response.status_code == 201
        data = response.json()
        
        assert data["success"] is True
        assert data["data"]["user"]["email"] == client_data["email"]
        assert data["data"]["user"]["user_type"] == "client"
        assert "tokens" in data["data"]
        assert "access_token" in data["data"]["tokens"]
    
    def test_register_client_duplicate_email(self, client, sample_client):
        """Test client registration with duplicate email."""
        client_data = {
            "email": sample_client.email,
            "password": "StrongPassword123!",
            "direccion": "New Address 456",
            "ci": "11111111",
            "fecha_nacimiento": "1995-05-15"
        }
        
        response = client.post("/api/v1/auth/register/client", json=client_data)
        
        assert response.status_code == 409  # Conflict
        data = response.json()
        
        assert data["success"] is False
        assert "email" in data["error"]["message"].lower()
    
    def test_register_client_weak_password(self, client):
        """Test client registration with weak password."""
        client_data = {
            "email": "newclient@test.com",
            "password": "weak",
            "direccion": "New Address 456",
            "ci": "11111111",
            "fecha_nacimiento": "1995-05-15"
        }
        
        response = client.post("/api/v1/auth/register/client", json=client_data)
        
        assert response.status_code == 400
        data = response.json()
        
        assert data["success"] is False
        assert "contraseña" in data["error"]["message"].lower()
    
    def test_login_success(self, client, sample_client):
        """Test successful login."""
        login_data = {
            "email": sample_client.email,
            "password": "testpassword123"
        }
        
        response = client.post("/api/v1/auth/login", json=login_data)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["data"]["user"]["email"] == sample_client.email
        assert "tokens" in data["data"]
        assert "access_token" in data["data"]["tokens"]
    
    def test_login_invalid_credentials(self, client, sample_client):
        """Test login with invalid credentials."""
        login_data = {
            "email": sample_client.email,
            "password": "wrongpassword"
        }
        
        response = client.post("/api/v1/auth/login", json=login_data)
        
        assert response.status_code == 401
        data = response.json()
        
        assert data["success"] is False
        assert "credenciales" in data["error"]["message"].lower()
    
    def test_login_nonexistent_user(self, client):
        """Test login with nonexistent user."""
        login_data = {
            "email": "nonexistent@test.com",
            "password": "testpassword123"
        }
        
        response = client.post("/api/v1/auth/login", json=login_data)
        
        assert response.status_code == 401
        data = response.json()
        
        assert data["success"] is False
    
    def test_get_profile_authenticated(self, client, sample_client, auth_headers):
        """Test getting profile when authenticated."""
        response = client.get("/api/v1/auth/me", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["data"]["email"] == sample_client.email
        assert data["data"]["user_type"] == sample_client.user_type
    
    def test_get_profile_unauthenticated(self, client):
        """Test getting profile when not authenticated."""
        response = client.get("/api/v1/auth/me")
        
        assert response.status_code == 401
    
    def test_logout_authenticated(self, client, auth_headers):
        """Test logout when authenticated."""
        response = client.post("/api/v1/auth/logout", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "logout" in data["message"].lower()
    
    def test_logout_unauthenticated(self, client):
        """Test logout when not authenticated."""
        response = client.post("/api/v1/auth/logout")
        
        assert response.status_code == 401