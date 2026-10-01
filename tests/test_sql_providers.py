import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from backend.connections.providers.mysql import MySQLProvider, MariaDBProvider
from backend.connections.providers.sqlite import SQLiteProvider
from backend.connections.base import InvalidCredentials, Unreachable

# ── SQLite Provider Tests ─────────────────────────────────────

def test_sqlite_provider_connect_and_test():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        # Initialize small test DB
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("CREATE TABLE users (id INT, name TEXT);")
            conn.execute("INSERT INTO users VALUES (1, 'Alice');")
            conn.commit()
        finally:
            conn.close()

        provider = SQLiteProvider()
        conn_data = provider.connect({"path": db_path, "read_only": True})
        assert conn_data["account_identifier"] == Path(db_path).name
        assert "SQLite" in conn_data["display_name"]

        # Test connection
        res = provider.test_connection(
            decrypted_credentials=conn_data["credentials"],
            metadata_safe=conn_data["metadata_safe"],
        )
        assert res["ok"] is True
        assert "SQLite" in res["version"]

        # Client query
        client = provider.get_client(
            decrypted_credentials=conn_data["credentials"],
            metadata_safe=conn_data["metadata_safe"],
        )
        rows = client.query("SELECT * FROM users;")
        assert len(rows) == 1
        assert rows[0]["name"] == "Alice"
    finally:
        Path(db_path).unlink(missing_ok=True)

def test_sqlite_provider_nonexistent_file():
    provider = SQLiteProvider()
    with pytest.raises(Unreachable):
        provider.connect({"path": "C:\\nonexistent\\invalid.db"})


# ── MySQL / MariaDB Provider Tests ────────────────────────────

@patch("backend.connections.providers.mysql.validate_db_host")
def test_mysql_provider_connect(mock_ssrf):
    provider = MySQLProvider()
    conn_data = provider.connect({
        "host": "localhost",
        "port": 3306,
        "database": "sales_db",
        "user": "root",
        "password": "secretpassword",
    })
    assert conn_data["account_identifier"] == "root@localhost:3306/sales_db"
    assert conn_data["display_name"] == "MySQL (sales_db)"
    assert conn_data["credentials"]["database"] == "sales_db"

@patch("backend.connections.providers.mysql.validate_db_host")
def test_mariadb_provider_metadata(mock_ssrf):
    provider = MariaDBProvider()
    meta = provider.get_metadata()
    assert meta.id == "mariadb"
    assert meta.name == "MariaDB"
    assert meta.available is True

@patch("pymysql.connect")
@patch("backend.connections.providers.mysql.validate_db_host")
def test_mysql_provider_test_connection_success(mock_ssrf, mock_connect):
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {"version": "8.0.35-mysql"}
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_connect.return_value = mock_conn

    provider = MySQLProvider()
    res = provider.test_connection(
        decrypted_credentials={
            "host": "localhost",
            "port": 3306,
            "user": "app",
            "password": "pwd",
            "database": "app_db",
        },
        metadata_safe={},
    )
    assert res["ok"] is True
    assert res["version"] == "8.0.35-mysql"

@patch("pymysql.connect")
@patch("backend.connections.providers.mysql.validate_db_host")
def test_mysql_provider_test_connection_auth_failure(mock_ssrf, mock_connect):
    mock_connect.side_effect = Exception("(1045, 'Access denied for user')")

    provider = MySQLProvider()
    with pytest.raises(InvalidCredentials) as exc:
        provider.test_connection(
            decrypted_credentials={
                "host": "localhost",
                "port": 3306,
                "user": "app",
                "password": "wrong_password",
                "database": "app_db",
            },
            metadata_safe={},
        )
    assert "Access Denied" in str(exc.value)
