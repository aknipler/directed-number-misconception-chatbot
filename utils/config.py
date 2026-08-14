"""Central access to app configuration, sourced from .streamlit/secrets.toml.

Every entry point - the Streamlit app pages and the standalone scripts/
utilities - should read configuration through here, rather than some code
reading os.environ/.env and other code reading st.secrets directly. This
project keeps a single source of configuration (secrets.toml); there is no
.env file to keep in sync with it.
"""

import streamlit as st


def get_secret(key: str) -> str:
    """Read a single value from .streamlit/secrets.toml, with a clear error if missing."""
    try:
        return st.secrets[key]
    except KeyError:
        raise KeyError(
            f"'{key}' not found in .streamlit/secrets.toml. Add it there - "
            "this project reads all configuration from secrets.toml, not from .env/os.environ."
        ) from None


def get_mongo_settings() -> tuple[str, str]:
    """Return (connection_string, database_name) for MongoDB."""
    return get_secret("MONGODB_CONNECTION_STRING"), get_secret("MONGODB_DATABASE_NAME")
