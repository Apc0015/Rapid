import pytest
import os
import sqlite3
from app.services.rag_config_service import (
    RAGConfigurationService,
    RAG_TEMPLATES,
    DEFAULT_TEMPLATE,
    CHUNK_SIZE_MIN,
    CHUNK_SIZE_MAX,
    TOP_K_MIN,
    TOP_K_MAX,
)

# Use a temporary database for testing
TEST_DB_PATH = os.path.join(os.path.dirname(__file__), "test_users.db")


@pytest.fixture(autouse=True)
def clean_db(monkeypatch):
    """Use a temporary DB and clean up after each test."""
    monkeypatch.setattr("app.services.rag_config_service.USER_DB_PATH", TEST_DB_PATH)
    yield
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


@pytest.fixture
def service():
    return RAGConfigurationService()


# ---------------------------------------------------------------------------
# Template tests
# ---------------------------------------------------------------------------


class TestTemplates:
    def test_five_templates_exist(self, service):
        templates = service.get_all_templates()
        assert len(templates) == 5

    def test_template_keys(self, service):
        templates = service.get_all_templates()
        keys = {t["key"] for t in templates}
        assert keys == {"fast_search", "balanced", "deep_analysis", "cost_optimized", "high_accuracy"}

    def test_get_template_by_name(self, service):
        tmpl = service.get_template_by_name("balanced")
        assert tmpl["chunk_size"] == 512
        assert tmpl["overlap_size"] == 64
        assert tmpl["top_k"] == 5

    def test_get_template_case_insensitive(self, service):
        tmpl = service.get_template_by_name("DEEP_ANALYSIS")
        assert tmpl["chunk_size"] == 1024

    def test_get_unknown_template_raises(self, service):
        with pytest.raises(ValueError, match="Unknown template"):
            service.get_template_by_name("nonexistent")

    def test_all_templates_have_required_fields(self, service):
        for tmpl in service.get_all_templates():
            assert "chunk_size" in tmpl
            assert "overlap_size" in tmpl
            assert "top_k" in tmpl
            assert "embedding_model" in tmpl
            assert "description" in tmpl
            assert "trade_off" in tmpl


# ---------------------------------------------------------------------------
# User config CRUD
# ---------------------------------------------------------------------------


class TestUserConfig:
    def test_default_config_is_balanced(self, service):
        cfg = service.get_user_active_config("testuser")
        assert cfg["config_type"] == "template"
        assert cfg["chunk_size"] == 512
        assert cfg["top_k"] == 5
        assert cfg["id"] is None  # Not persisted yet

    def test_apply_template(self, service):
        cfg = service.apply_template("testuser", "fast_search")
        assert cfg["chunk_size"] == 256
        assert cfg["top_k"] == 3
        assert cfg["is_active"] == 1
        assert cfg["template_name"] == "fast_search"
        assert cfg["id"] is not None

    def test_apply_template_deactivates_previous(self, service):
        service.apply_template("testuser", "fast_search")
        service.apply_template("testuser", "deep_analysis")
        cfg = service.get_user_active_config("testuser")
        assert cfg["chunk_size"] == 1024
        assert cfg["top_k"] == 8

    def test_create_custom_config(self, service):
        data = {
            "config_name": "Test Custom",
            "chunk_size": 300,
            "overlap_size": 40,
            "top_k": 7,
            "embedding_model": "text-embedding-ada-002",
        }
        cfg = service.create_custom_config("testuser", data)
        assert cfg["config_type"] == "custom"
        assert cfg["chunk_size"] == 300
        assert cfg["is_active"] == 1
        assert cfg["template_name"] is None

    def test_custom_config_deactivates_template(self, service):
        service.apply_template("testuser", "balanced")
        data = {"config_name": "My", "chunk_size": 400, "overlap_size": 50, "top_k": 4}
        service.create_custom_config("testuser", data)
        cfg = service.get_user_active_config("testuser")
        assert cfg["config_type"] == "custom"
        assert cfg["chunk_size"] == 400

    def test_list_user_custom_configs(self, service):
        service.create_custom_config("u1", {"config_name": "A", "chunk_size": 200, "overlap_size": 20, "top_k": 2})
        service.create_custom_config("u1", {"config_name": "B", "chunk_size": 300, "overlap_size": 30, "top_k": 3})
        configs = service.list_user_custom_configs("u1")
        assert len(configs) == 2

    def test_delete_custom_config(self, service):
        cfg = service.create_custom_config("u1", {"config_name": "Del", "chunk_size": 200, "overlap_size": 20, "top_k": 2})
        assert service.delete_custom_config("u1", cfg["id"]) is True
        configs = service.list_user_custom_configs("u1")
        assert len(configs) == 0

    def test_delete_nonexistent_returns_false(self, service):
        assert service.delete_custom_config("u1", 9999) is False

    def test_delete_wrong_user_returns_false(self, service):
        cfg = service.create_custom_config("u1", {"config_name": "X", "chunk_size": 200, "overlap_size": 20, "top_k": 2})
        assert service.delete_custom_config("u2", cfg["id"]) is False

    def test_user_isolation(self, service):
        service.apply_template("alice", "fast_search")
        service.apply_template("bob", "deep_analysis")
        alice_cfg = service.get_user_active_config("alice")
        bob_cfg = service.get_user_active_config("bob")
        assert alice_cfg["chunk_size"] == 256
        assert bob_cfg["chunk_size"] == 1024


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_chunk_size_too_small(self, service):
        with pytest.raises(ValueError, match="chunk_size"):
            service.create_custom_config("u", {"config_name": "X", "chunk_size": 50, "overlap_size": 10, "top_k": 5})

    def test_chunk_size_too_large(self, service):
        with pytest.raises(ValueError, match="chunk_size"):
            service.create_custom_config("u", {"config_name": "X", "chunk_size": 5000, "overlap_size": 10, "top_k": 5})

    def test_top_k_too_large(self, service):
        with pytest.raises(ValueError, match="top_k"):
            service.create_custom_config("u", {"config_name": "X", "chunk_size": 512, "overlap_size": 64, "top_k": 100})

    def test_overlap_exceeds_chunk_size(self, service):
        with pytest.raises(ValueError, match="overlap_size must be less than chunk_size"):
            service.create_custom_config("u", {"config_name": "X", "chunk_size": 128, "overlap_size": 200, "top_k": 5})


# ---------------------------------------------------------------------------
# Engine integration
# ---------------------------------------------------------------------------


class TestActiveParams:
    def test_default_params_no_user(self, service):
        cs, ov, tk, model, search_mode = service.get_active_params(None)
        assert cs == 512
        assert ov == 64
        assert tk == 5

    def test_params_after_template(self, service):
        service.apply_template("u1", "high_accuracy")
        cs, ov, tk, model, search_mode = service.get_active_params("u1")
        assert cs == 768
        assert ov == 96
        assert tk == 10

    def test_params_after_custom(self, service):
        service.create_custom_config("u1", {"config_name": "C", "chunk_size": 333, "overlap_size": 33, "top_k": 7})
        cs, ov, tk, model, search_mode = service.get_active_params("u1")
        assert cs == 333
        assert tk == 7


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
