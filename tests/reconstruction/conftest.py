"""
Pytest configuration and fixtures for reconstruction tests.
"""
import pytest
from pathlib import Path
import tempfile
import shutil


@pytest.fixture(scope="session")
def test_data_dir(tmp_path_factory):
    """Create a temporary directory for test data."""
    temp_dir = tmp_path_factory.mktemp("reconstruction_test_data")
    yield temp_dir
    # Cleanup happens automatically


@pytest.fixture
def sample_fixtures_dir():
    """Path to version-controlled sample data fixtures."""
    # This would point to actual test fixtures in the project
    fixtures_path = Path(__file__).parent.parent / "fixtures"
    if not fixtures_path.exists():
        fixtures_path.mkdir(parents=True, exist_ok=True)
    return fixtures_path


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "performance: marks tests as performance tests"
    )