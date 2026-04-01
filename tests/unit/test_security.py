#!/usr/bin/env python3
"""
Unit Tests for Security Module
Test JWT, password hashing, input validation, rate limiting
"""

import pytest
from datetime import datetime, timedelta
from backend.middleware.security import (
    TokenManager,
    InputValidator,
    RateLimiter,
)

class TestTokenManager:
    """JWT Token Management Tests"""
    
    def test_create_access_token(self):
        """Test token creation"""
        data = {"sub": "test_user"}
        token = TokenManager.create_access_token(data)
        
        assert token is not None
        assert isinstance(token, str)
        assert len(token.split(".")) == 3  # Valid JWT format
    
    def test_verify_valid_token(self):
        """Test token verification"""
        data = {"sub": "test_user", "role": "admin"}
        token = TokenManager.create_access_token(data)
        
        payload = TokenManager.verify_token(token)
        
        assert payload is not None
        assert payload["sub"] == "test_user"
        assert payload["role"] == "admin"
    
    def test_verify_invalid_token(self):
        """Test invalid token verification"""
        invalid_token = "invalid.token.here"
        payload = TokenManager.verify_token(invalid_token)
        
        assert payload is None
    
    def test_token_expiration(self):
        """Test token expiration"""
        data = {"sub": "test_user"}
        expires_delta = timedelta(seconds=-1)  # Already expired
        token = TokenManager.create_access_token(data, expires_delta)
        
        payload = TokenManager.verify_token(token)
        assert payload is None  # Token should be expired

class TestInputValidator:
    """Input Validation Tests"""
    
    def test_validate_empty_question(self):
        """Test empty question validation"""
        is_valid, error = InputValidator.validate_question("")
        
        assert is_valid is False
        assert "empty" in error.lower()
    
    def test_validate_short_question(self):
        """Test short question validation"""
        is_valid, error = InputValidator.validate_question("ab")
        
        assert is_valid is False
        assert "3 characters" in error
    
    def test_validate_valid_question(self):
        """Test valid question"""
        is_valid, error = InputValidator.validate_question("How many patients do we have?")
        
        assert is_valid is True
        assert error == ""
    
    def test_validate_dangerous_patterns(self):
        """Test dangerous pattern detection"""
        dangerous_questions = [
            "DROP TABLE patients",
            "DELETE FROM doctors WHERE id=1",
            "TRUNCATE appointments",
        ]
        
        for question in dangerous_questions:
            is_valid, error = InputValidator.validate_question(question)
            assert is_valid is False
            assert "harmful" in error.lower()
    
    def test_sanitize_response(self):
        """Test response sanitization"""
        long_response = "x" * 20000
        sanitized = InputValidator.sanitize_response(long_response)
        
        assert len(sanitized) <= 10000

class TestRateLimiter:
    """Rate Limiting Tests"""
    
    def test_rate_limiter_allows_requests(self):
        """Test rate limiter allows requests"""
        limiter = RateLimiter()
        identifier = "user_1"
        
        # Should allow multiple requests under limit
        for _ in range(10):
            assert limiter.is_allowed(identifier) is True
    
    def test_rate_limiter_blocks_excess(self):
        """Test rate limiter blocks excess requests"""
        limiter = RateLimiter()
        identifier = "user_1"
        
        # Max out the limit
        for _ in range(30):  # Default limit is 30/min
            limiter.is_allowed(identifier)
        
        # Next request should be blocked
        assert limiter.is_allowed(identifier) is False
    
    def test_get_remaining_requests(self):
        """Test remaining requests counter"""
        limiter = RateLimiter()
        identifier = "user_1"
        
        assert limiter.get_remaining(identifier) == 30
        
        limiter.is_allowed(identifier)
        assert limiter.get_remaining(identifier) == 29
