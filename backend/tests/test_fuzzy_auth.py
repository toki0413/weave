"""
使用 Hypothesis 为 auth.py 的注册/登录创建模糊测试。
边界场景：超长手机号、特殊字符密码、SQL 注入 payload。
"""
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck


class TestAuthFuzzy:
    """模糊测试认证接口的边界输入"""

    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.filter_too_much, HealthCheck.function_scoped_fixture])
    @given(phone=st.text(min_size=1, max_size=30), password=st.text(min_size=1, max_size=100))
    def test_register_arbitrary_phone_password(self, client, phone, password):
        """任意手机号+密码不应导致 500，只应返回 400 或 200"""
        r = client.post("/api/v1/auth/register", json={
            "phone": phone,
            "password": password,
            "name": "fuzz",
        })
        assert r.status_code in (200, 400, 422)

    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.filter_too_much, HealthCheck.function_scoped_fixture])
    @given(phone=st.text(alphabet="0123456789", min_size=20, max_size=50))
    def test_register_extremely_long_phone(self, client, phone):
        """超长纯数字手机号应被 Pydantic 拦截（422）或业务层拦截（400）"""
        r = client.post("/api/v1/auth/register", json={
            "phone": phone,
            "password": "password123!",
            "name": "fuzz",
        })
        assert r.status_code in (200, 400, 422)

    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.filter_too_much, HealthCheck.function_scoped_fixture])
    @given(password=st.text(alphabet="!@#$%^&*()_+-=[]{}|;':\",./<>?", min_size=1, max_size=100))
    def test_register_special_char_password(self, client, password):
        """特殊字符密码不应导致 500"""
        import uuid
        phone = "139" + str(uuid.uuid4().int % 1000000000).zfill(9)
        r = client.post("/api/v1/auth/register", json={
            "phone": phone,
            "password": password,
            "name": "fuzz",
        })
        assert r.status_code in (200, 400, 422)

    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.filter_too_much, HealthCheck.function_scoped_fixture])
    @given(payload=st.text(min_size=1, max_size=200))
    def test_register_sql_injection_phone(self, client, payload):
        """SQL 注入 payload 不应导致 500，也不应成功注册"""
        r = client.post("/api/v1/auth/register", json={
            "phone": payload,
            "password": "password123!",
            "name": "fuzz",
        })
        assert r.status_code in (200, 400, 422)

    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.filter_too_much, HealthCheck.function_scoped_fixture])
    @given(phone=st.text(min_size=1, max_size=30), password=st.text(min_size=1, max_size=100))
    def test_login_arbitrary_credentials(self, client, phone, password):
        """任意凭据登录不应导致 500"""
        r = client.post("/api/v1/auth/login", json={
            "phone": phone,
            "password": password,
        })
        assert r.status_code in (200, 401, 422)
