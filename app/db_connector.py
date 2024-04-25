import os, sys
import logging
import sqlalchemy


logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s - %(message)s",
    level=logging.DEBUG,
    datefmt="%Y-%m-%d %H:%M:%S",
)


def connect_unix_socket() -> sqlalchemy.engine.base.Engine:

    logging.info(f"Connecting to database using Unix socket")
    """Initializes a Unix socket connection pool for a Cloud SQL instance of Postgres."""
    db_user = os.environ["DB_USER"]
    db_pass = os.environ["DB_PASSWORD"]
    db_name = os.environ["DB_NAME"]
    instance_connection_name = os.environ[
        "INSTANCE_CONNECTION_NAME"
    ]  # e.g. '/cloudsql/project:region:instance'

    pool = sqlalchemy.create_engine(
        # Equivalent URL:
        # postgresql+pg8000://<db_user>:<db_pass>@/<db_name>
        #                         ?unix_sock=<INSTANCE_UNIX_SOCKET>/.s.PGSQL.5432
        # Note: Some drivers require the `unix_sock` query parameter to use a different key.
        sqlalchemy.engine.url.URL.create(
            drivername="postgresql+pg8000",
            username=db_user,
            password=db_pass,
            database=db_name,
            query={"unix_sock": f"/cloudsql/{instance_connection_name}/.s.PGSQL.5432"},
        ),
        client_encoding="utf8",
    )
    logging.info(f"Connected to database using Unix socket")
    return pool


def connect() -> sqlalchemy.engine.base.Engine:

    logging.info(f"Connecting to database using TCP")
    """Initializes a Unix socket connection pool for a Cloud SQL instance of Postgres."""
    db_user = os.environ["DB_USER"]
    db_pass = os.environ["DB_PASSWORD"]
    db_name = os.environ["DB_NAME"]

    pool = sqlalchemy.create_engine(
        # Equivalent URL:
        # postgresql+pg8000://<db_user>:<db_pass>@/<db_name>
        sqlalchemy.engine.url.URL.create(
            drivername="postgresql+pg8000",
            username=db_user,
            password=db_pass,
            database=db_name,
        ),
        client_encoding="utf8",
    )
    logging.info(f"Connected to database using TCP")
    return pool

connection = None
def get_engine():
    global connection
    if connection:
        return connection
    else:
        connection = (
            connect_unix_socket()
            if os.environ.get("INSTANCE_CONNECTION_NAME")
            else connect()
        )
        return connection



""" def get_engine():
    return (
        connect_unix_socket()
        if os.environ.get("INSTANCE_CONNECTION_NAME")
        else connect()
    )
 """