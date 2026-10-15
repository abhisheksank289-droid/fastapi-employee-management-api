import os
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv


ENV_FILE = Path(__file__).resolve().parent / ".env"


def get_db_connection():
    """Connect to the employee_management database."""
    load_dotenv(dotenv_path=ENV_FILE)

    required_settings = ("DB_HOST", "DB_USER", "DB_NAME")
    missing_settings = [
        setting for setting in required_settings
        if not os.getenv(setting)
    ]

    # An empty database password is allowed.
    if "DB_PASSWORD" not in os.environ:
        missing_settings.append("DB_PASSWORD")

    if missing_settings:
        missing_names = ", ".join(missing_settings)
        raise ValueError(
            f"Missing database settings in {ENV_FILE.name}: {missing_names}"
        )

    try:
        port = int(os.getenv("DB_PORT", "3306"))
    except ValueError as error:
        raise ValueError(
            "DB_PORT must be a whole number, such as 3306."
        ) from error

    try:
        connection = mysql.connector.connect(
            host=os.environ["DB_HOST"],
            port=port,
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            database=os.environ["DB_NAME"],
        )
        return connection

    except mysql.connector.Error as error:
        raise ConnectionError(
            "Could not connect to MySQL. Check the server and .env settings."
        ) from error


if __name__ == "__main__":
    connection = None

    try:
        connection = get_db_connection()
        print("Database connection successful!")

    except (ConnectionError, ValueError) as error:
        print(f"Database connection test failed: {error}")

    finally:
        if connection is not None:
            connection.close()