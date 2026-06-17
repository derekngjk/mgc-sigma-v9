import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from main import app


@pytest.fixture(autouse=True, scope="session")
def mock_db_init():
    """Prevent init_db from trying to connect to a real Postgres in tests."""
    with patch("db.psycopg.connect") as mocked:
        yield mocked


@pytest.fixture
def mock_supabase(mocker):
    """Mock the supabase client and its chaining methods."""
    mock_client = MagicMock()

    # We'll use a side_effect function for table() to return different mocks per table
    tables = {}

    def get_table_mock(name=None):
        if name is None:
            name = "_default_"
        if name not in tables:
            mock_table = MagicMock()
            mock_table.upsert.return_value = mock_table
            mock_table.insert.return_value = mock_table
            mock_table.select.return_value = mock_table
            mock_table.update.return_value = mock_table
            mock_table.eq.return_value = mock_table
            mock_table.order.return_value = mock_table
            mock_table.limit.return_value = mock_table
            # Default empty data
            mock_table.execute.return_value = MagicMock(data=[])
            tables[name] = mock_table
        return tables[name]

    mock_client.table.side_effect = get_table_mock

    mocker.patch("db.get_supabase", return_value=mock_client)
    return mock_client


@pytest.fixture(scope="module")
def client() -> TestClient:
    # Set dummy env vars for tests to avoid real connection attempts if any logic escapes
    with patch.dict(
        "os.environ",
        {
            "SUPABASE_URL": "https://placeholder.supabase.co",
            "SUPABASE_KEY": "placeholder",
            "SUPABASE_DB_URL": "postgresql://user:pass@localhost:5432/db",
        },
    ):
        with TestClient(app) as c:
            yield c
