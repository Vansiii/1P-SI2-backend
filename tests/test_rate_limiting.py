"""
Tests para verificar el sistema de rate limiting.

Estos tests demuestran:
1. Whitelist de IPs funciona correctamente
2. Límites para admins son más altos
3. Rate limiting se aplica correctamente
"""

import pytest
from fastapi import Request
from unittest.mock import Mock

from app.config import get_settings
from app.utils.rate_limit import (
    get_remote_address_with_whitelist,
    get_rate_limit_key_with_user_type,
    create_admin_rate_limit,
)


def test_whitelist_bypass():
    """Test que IPs en whitelist retornan clave especial."""
    # Mock request con IP en whitelist
    request = Mock(spec=Request)
    
    # Simular IP en whitelist (127.0.0.1 está en .env.example)
    with pytest.MonkeyPatch.context() as m:
        m.setenv("RATE_LIMIT_WHITELIST_IPS", "127.0.0.1,192.168.1.100")
        
        # Mock get_remote_address para retornar IP en whitelist
        from app.utils import rate_limit
        original_get_remote = rate_limit.get_remote_address
        rate_limit.get_remote_address = lambda r: "127.0.0.1"
        
        result = get_remote_address_with_whitelist(request)
        
        # Restaurar función original
        rate_limit.get_remote_address = original_get_remote
        
        assert result == "whitelist", "IP en whitelist debe retornar 'whitelist'"


def test_non_whitelist_returns_ip():
    """Test que IPs no en whitelist retornan la IP normal."""
    request = Mock(spec=Request)
    
    with pytest.MonkeyPatch.context() as m:
        m.setenv("RATE_LIMIT_WHITELIST_IPS", "127.0.0.1")
        
        from app.utils import rate_limit
        original_get_remote = rate_limit.get_remote_address
        rate_limit.get_remote_address = lambda r: "203.0.113.42"
        
        result = get_remote_address_with_whitelist(request)
        
        rate_limit.get_remote_address = original_get_remote
        
        assert result == "203.0.113.42", "IP no en whitelist debe retornar la IP"


def test_admin_multiplier():
    """Test que el multiplicador de admin funciona correctamente."""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("RATE_LIMIT_ADMIN_MULTIPLIER", "3")
        
        # Test con diferentes límites
        assert create_admin_rate_limit("5/minute") == "15/minute"
        assert create_admin_rate_limit("10/hour") == "30/hour"
        assert create_admin_rate_limit("3/day") == "9/day"


def test_admin_multiplier_invalid_format():
    """Test que límites con formato inválido se retornan sin cambios."""
    result = create_admin_rate_limit("invalid")
    assert result == "invalid", "Formato inválido debe retornarse sin cambios"
    
    result = create_admin_rate_limit("5")
    assert result == "5", "Formato sin período debe retornarse sin cambios"


def test_admin_user_gets_special_key():
    """Test que usuarios admin obtienen clave especial para rate limiting."""
    request = Mock(spec=Request)
    
    # Mock usuario admin
    user = Mock()
    user.user_type = "admin"
    request.state.user = user
    
    with pytest.MonkeyPatch.context() as m:
        m.setenv("RATE_LIMIT_WHITELIST_IPS", "")
        
        from app.utils import rate_limit
        original_get_remote = rate_limit.get_remote_address
        rate_limit.get_remote_address = lambda r: "203.0.113.42"
        
        result = get_rate_limit_key_with_user_type(request)
        
        rate_limit.get_remote_address = original_get_remote
        
        assert result == "203.0.113.42:admin", "Admin debe tener clave especial"


def test_non_admin_user_gets_normal_key():
    """Test que usuarios no-admin obtienen clave normal."""
    request = Mock(spec=Request)
    
    # Mock usuario no-admin
    user = Mock()
    user.user_type = "client"
    request.state.user = user
    
    with pytest.MonkeyPatch.context() as m:
        m.setenv("RATE_LIMIT_WHITELIST_IPS", "")
        
        from app.utils import rate_limit
        original_get_remote = rate_limit.get_remote_address
        rate_limit.get_remote_address = lambda r: "203.0.113.42"
        
        result = get_rate_limit_key_with_user_type(request)
        
        rate_limit.get_remote_address = original_get_remote
        
        assert result == "203.0.113.42", "No-admin debe tener clave normal (solo IP)"


def test_unauthenticated_user_gets_ip_key():
    """Test que usuarios no autenticados obtienen solo IP."""
    request = Mock(spec=Request)
    request.state.user = None
    
    with pytest.MonkeyPatch.context() as m:
        m.setenv("RATE_LIMIT_WHITELIST_IPS", "")
        
        from app.utils import rate_limit
        original_get_remote = rate_limit.get_remote_address
        rate_limit.get_remote_address = lambda r: "203.0.113.42"
        
        result = get_rate_limit_key_with_user_type(request)
        
        rate_limit.get_remote_address = original_get_remote
        
        assert result == "203.0.113.42", "Usuario no autenticado debe tener solo IP"


if __name__ == "__main__":
    # Ejecutar tests manualmente
    print("Ejecutando tests de rate limiting...")
    
    print("\n1. Test whitelist bypass...")
    try:
        test_whitelist_bypass()
        print("   ✅ PASS")
    except AssertionError as e:
        print(f"   ❌ FAIL: {e}")
    
    print("\n2. Test non-whitelist returns IP...")
    try:
        test_non_whitelist_returns_ip()
        print("   ✅ PASS")
    except AssertionError as e:
        print(f"   ❌ FAIL: {e}")
    
    print("\n3. Test admin multiplier...")
    try:
        test_admin_multiplier()
        print("   ✅ PASS")
    except AssertionError as e:
        print(f"   ❌ FAIL: {e}")
    
    print("\n4. Test admin multiplier invalid format...")
    try:
        test_admin_multiplier_invalid_format()
        print("   ✅ PASS")
    except AssertionError as e:
        print(f"   ❌ FAIL: {e}")
    
    print("\n5. Test admin user gets special key...")
    try:
        test_admin_user_gets_special_key()
        print("   ✅ PASS")
    except AssertionError as e:
        print(f"   ❌ FAIL: {e}")
    
    print("\n6. Test non-admin user gets normal key...")
    try:
        test_non_admin_user_gets_normal_key()
        print("   ✅ PASS")
    except AssertionError as e:
        print(f"   ❌ FAIL: {e}")
    
    print("\n7. Test unauthenticated user gets IP key...")
    try:
        test_unauthenticated_user_gets_ip_key()
        print("   ✅ PASS")
    except AssertionError as e:
        print(f"   ❌ FAIL: {e}")
    
    print("\n✅ Tests completados")
