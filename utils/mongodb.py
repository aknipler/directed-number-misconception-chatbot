from pymongo import MongoClient
from pymongo.server_api import ServerApi
import streamlit as st
from datetime import datetime, timezone

@st.cache_resource(show_spinner=False)
def get_mongo_client(connection_string):
    """Return a shared MongoClient.

    Cached because the transcript is now saved after every turn: reconnecting on
    each save would add an Atlas handshake to every message. MongoClient is
    thread-safe and pools its own connections, so callers must not close it.
    """
    return MongoClient(connection_string, server_api=ServerApi('1'))

# Outcomes returned by check_identifier. These are recorded verbatim as the
# "outcome" field of a login_events document.
LOGIN_OK = "success"
LOGIN_TOO_SHORT = "too_short"
LOGIN_NOT_FOUND = "not_found"
LOGIN_DB_ERROR = "db_error"

def check_identifier(connection_string, database_name, identifier):
    """Validate an identifier, returning one of the LOGIN_* outcomes.

    Returns an outcome rather than a bool so a database failure is
    distinguishable from a bad identifier. Collapsing the two meant an
    unreachable cluster told students "Invalid identifier" and left no trace
    anywhere -- a whole cohort could be locked out silently.
    """
    if not identifier or len(identifier.strip()) < 3:
        return LOGIN_TOO_SHORT

    try:
        client = get_mongo_client(connection_string)
        db = client[database_name]
        result = db.valid_identifiers.find_one({"identifier": identifier})
        return LOGIN_OK if result else LOGIN_NOT_FOUND
    except Exception:
        return LOGIN_DB_ERROR


def log_login_event(connection_string, database_name, conversation_type,
                    identifier, outcome, session_id=None):
    """Append one login attempt to the login_events collection.

    Insert-only, into its own collection, so it can neither modify nor collide
    with transcript data. Failed attempts are recorded too: without them there
    is no way to tell a cohort that never showed up from one that was blocked
    at the login screen.
    """
    client = get_mongo_client(connection_string)
    client[database_name].login_events.insert_one({
        "timestamp": datetime.now(timezone.utc),
        "identifier": identifier,
        "outcome": outcome,
        "session_id": session_id,
        "conversation_type": conversation_type,
    })


def save_transcript(connection_string, database_name, conversation_type,
                    session_id, identifier, messages, completed=False):
    """Create or update the transcript document for one chat session.

    Called at login and again after every turn, so a conversation survives the
    student closing the tab. Each save rewrites the whole message list, which
    means a save that fails is repaired by the next one that succeeds.

    The document is keyed on session_id, not _id, so the filter only ever
    matches documents this function created. Transcripts written before session
    ids existed have no session_id field and can never be matched or modified.
    """
    client = get_mongo_client(connection_string)
    collection = client[database_name].transcripts

    now = datetime.now(timezone.utc)
    collection.update_one(
        {"session_id": session_id},
        {
            "$set": {
                "identifier": identifier,
                "conversation_type": conversation_type,
                "messages": messages,
                "message_count": len(messages),
                "completed": completed,
                "updated_at": now,
            },
            # Session start time, written once when the document is created.
            "$setOnInsert": {"timestamp": now},
        },
        upsert=True,
    )
    return session_id
