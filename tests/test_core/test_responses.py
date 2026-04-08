"""
Tests for responses module.
"""
import pytest
from unittest.mock import patch

from app.core.responses import (
    create_success_response,
    create_error_response,
    create_paginated_response,
    get_request_id,
)


class TestSuccessResponse:
    """Test success response creation."""
    
    def test_create_success_response_basic(self):
        """Test basic success response creation."""
        data = {"key": "value"}
        message = "Success"
        
        response = create_success_response(data=data, message=message)
        
        assert response["success"] is True
        assert response["data"] == data
        assert response["message"] == message
        assert "request_id" in response
        assert response["status_code"] == 200
    
    def test_create_success_response_with_status_code(self):
        """Test success response with custom status code."""
        data = {"key": "value"}
        message = "Created"
        status_code = 201
        
        response = create_success_response(
            data=data, 
            message=message, 
            status_code=status_code
        )
        
        assert response["status_code"] == status_code
    
    def test_create_success_response_no_data(self):
        """Test success response without data."""
        message = "Success"
        
        response = create_success_response(message=message)
        
        assert response["success"] is True
        assert response["data"] is None
        assert response["message"] == message
    
    def test_create_success_response_no_message(self):
        """Test success response without message."""
        data = {"key": "value"}
        
        response = create_success_response(data=data)
        
        assert response["success"] is True
        assert response["data"] == data
        assert response["message"] == "Success"


class TestErrorResponse:
    """Test error response creation."""
    
    def test_create_error_response_basic(self):
        """Test basic error response creation."""
        message = "Error occurred"
        code = "TEST_ERROR"
        
        response = create_error_response(message=message, code=code)
        
        assert response["success"] is False
        assert response["error"]["message"] == message
        assert response["error"]["code"] == code
        assert "request_id" in response
        assert response["status_code"] == 500
    
    def test_create_error_response_with_status_code(self):
        """Test error response with custom status code."""
        message = "Bad request"
        code = "BAD_REQUEST"
        status_code = 400
        
        response = create_error_response(
            message=message, 
            code=code, 
            status_code=status_code
        )
        
        assert response["status_code"] == status_code
    
    def test_create_error_response_with_details(self):
        """Test error response with details."""
        message = "Validation error"
        code = "VALIDATION_ERROR"
        details = {"field": "email", "issue": "invalid format"}
        
        response = create_error_response(
            message=message, 
            code=code, 
            details=details
        )
        
        assert response["error"]["details"] == details
    
    def test_create_error_response_no_code(self):
        """Test error response without code."""
        message = "Error occurred"
        
        response = create_error_response(message=message)
        
        assert response["error"]["code"] == "INTERNAL_ERROR"


class TestPaginatedResponse:
    """Test paginated response creation."""
    
    def test_create_paginated_response_basic(self):
        """Test basic paginated response creation."""
        data = [{"id": 1}, {"id": 2}, {"id": 3}]
        total = 10
        limit = 3
        offset = 0
        
        response = create_paginated_response(
            data=data,
            total=total,
            limit=limit,
            offset=offset,
        )
        
        assert response["success"] is True
        assert response["data"] == data
        assert response["pagination"]["total"] == total
        assert response["pagination"]["limit"] == limit
        assert response["pagination"]["offset"] == offset
        assert response["pagination"]["has_more"] is True
    
    def test_create_paginated_response_no_more_data(self):
        """Test paginated response when no more data available."""
        data = [{"id": 8}, {"id": 9}, {"id": 10}]
        total = 10
        limit = 3
        offset = 7
        
        response = create_paginated_response(
            data=data,
            total=total,
            limit=limit,
            offset=offset,
        )
        
        assert response["pagination"]["has_more"] is False
    
    def test_create_paginated_response_with_message(self):
        """Test paginated response with custom message."""
        data = [{"id": 1}]
        total = 1
        limit = 10
        offset = 0
        message = "Users retrieved successfully"
        
        response = create_paginated_response(
            data=data,
            total=total,
            limit=limit,
            offset=offset,
            message=message,
        )
        
        assert response["message"] == message


class TestRequestId:
    """Test request ID functionality."""
    
    @patch('app.core.responses.uuid4')
    def test_get_request_id_generates_uuid(self, mock_uuid4):
        """Test that get_request_id generates a UUID when no context."""
        mock_uuid4.return_value.hex = "test-uuid-hex"
        
        request_id = get_request_id()
        
        assert request_id == "test-uuid-hex"
        mock_uuid4.assert_called_once()
    
    def test_get_request_id_returns_string(self):
        """Test that get_request_id returns a string."""
        request_id = get_request_id()
        
        assert isinstance(request_id, str)
        assert len(request_id) > 0