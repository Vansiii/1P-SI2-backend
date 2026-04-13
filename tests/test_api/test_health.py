"""
Tests for health endpoints.
"""
import pytest


class TestHealthEndpoints:
    """Test health check endpoints."""
    
    def test_basic_health_check(self, client):
        """Test basic health check endpoint."""
        response = client.get("/api/v1/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["data"]["status"] == "healthy"
        assert "timestamp" in data["data"]
        assert "version" in data["data"]
    
    def test_detailed_health_check(self, client):
        """Test detailed health check endpoint."""
        response = client.get("/api/v1/health/detailed")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "status" in data["data"]
        assert "database" in data["data"]
        assert "system" in data["data"]
        assert "timestamp" in data["data"]
    
    def test_database_health_check(self, client):
        """Test database health check endpoint."""
        response = client.get("/api/v1/health/database")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "status" in data["data"]
    
    def test_readiness_probe(self, client):
        """Test readiness probe endpoint."""
        response = client.get("/api/v1/health/readiness")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["data"]["ready"] is True
    
    def test_liveness_probe(self, client):
        """Test liveness probe endpoint."""
        response = client.get("/api/v1/health/liveness")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["data"]["alive"] is True