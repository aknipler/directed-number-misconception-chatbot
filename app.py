import streamlit as st
from anthropic import Anthropic
from utils.mongodb import (
    check_identifier, save_transcript, log_login_event,
    LOGIN_OK, LOGIN_TOO_SHORT, LOGIN_DB_ERROR,
)
import os
import uuid

def setup_session_state():
    """Initialize session state variables"""
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    if "user_identifier" not in st.session_state:
        st.session_state["user_identifier"] = ""

    if "conversation_finished" not in st.session_state:
        st.session_state["conversation_finished"] = False

    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []

    if "response_counter" not in st.session_state:
        st.session_state["response_counter"] = 0
        
    if "session_id" not in st.session_state:
        st.session_state["session_id"] = None

    if "save_failed" not in st.session_state:
        st.session_state["save_failed"] = False

    if "chatbot_prompt" not in st.session_state:
        # Load the prompt from the prompt.txt file
        prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "prompt.txt")
        try:
            with open(prompt_path, "r", encoding="utf-8") as file:
                st.session_state["chatbot_prompt"] = file.read()
        except FileNotFoundError:
            st.error("Prompt file not found. Please ensure prompt.txt exists in the prompts directory.")
            st.session_state["chatbot_prompt"] = "You are a helpful assistant."

    if "mongodb_uri" not in st.session_state:
        st.session_state["mongodb_uri"] = st.secrets.get("MONGODB_CONNECTION_STRING", "")
        
    if "mongodb_database_name" not in st.session_state:
        st.session_state["mongodb_database_name"] = st.secrets.get("MONGODB_DATABASE_NAME", "")

    # Set up AI client
    try:
        client = Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
        return client
    except KeyError:
        st.error("AI API key not found in secrets. Please check your .streamlit/secrets.toml file.")
        return None

def persist_transcript(completed=False):
    """Save the conversation so far. Returns True on success.

    Called after every turn rather than only at logout, because Streamlit has no
    disconnect hook: a student who closes the tab would otherwise lose the whole
    conversation. Failures are swallowed so a database hiccup never interrupts
    the chat -- each save sends the full history, so the next successful save
    recovers anything an earlier one missed.
    """
    if not st.session_state.get("session_id"):
        return False

    try:
        save_transcript(
            st.session_state["mongodb_uri"],
            st.session_state["mongodb_database_name"],
            "directed_number_misconception_chatbot",
            st.session_state["session_id"],
            st.session_state["user_identifier"],
            st.session_state["chat_history"],
            completed=completed,
        )
        st.session_state["save_failed"] = False
        return True
    except Exception:
        st.session_state["save_failed"] = True
        return False

def record_login_event(identifier, outcome, session_id=None):
    """Record a login attempt. Never blocks the student from logging in."""
    try:
        log_login_event(
            st.session_state.get("mongodb_uri", ""),
            st.session_state.get("mongodb_database_name", ""),
            "directed_number_misconception_chatbot",
            identifier,
            outcome,
            session_id,
        )
    except Exception:
        # A db_error outcome can't be written to the database it failed to
        # reach; that is expected and must not surface to the student.
        pass

def login_page():
    """Display the login page"""
    st.title("🔐 Login to Directed Number Misconception Chatbot")

    st.markdown("""
    Welcome to the Directed Number Misconception Chatbot!

    This chatbot simulates a 14-year-old student struggling with directed number concepts.
    You'll need to log in with a valid identifier to start chatting.
    """)

    identifier = st.text_input(
        "Enter your identifier:",
        key="identifier_input",
        value=st.session_state.get("user_identifier", ""),
        help="Enter a valid identifier to access the chatbot"
    )

    if st.button("Login", use_container_width=True):
        uri = st.session_state.get("mongodb_uri", "")
        db_name = st.session_state.get("mongodb_database_name", "")
        outcome = check_identifier(uri, db_name, identifier)

        # A new session id is minted only on success, and links the login event
        # to the transcript it produced.
        session_id = str(uuid.uuid4()) if outcome == LOGIN_OK else None
        record_login_event(identifier, outcome, session_id)

        if outcome == LOGIN_OK:
            st.session_state["user_identifier"] = identifier
            st.session_state["logged_in"] = True
            st.session_state["conversation_finished"] = False
            # Start a fresh conversation rather than inheriting whatever the
            # previous login on this browser session left behind.
            st.session_state["chat_history"] = []
            st.session_state["response_counter"] = 0
            st.session_state["session_id"] = session_id
            # Record the login straight away, so a student who logs in and
            # then abandons the study still appears in the data.
            persist_transcript()
            st.success("✅ Login successful! Redirecting to chat...")
            st.rerun()
        elif outcome == LOGIN_TOO_SHORT:
            st.warning("⚠️ Please enter an identifier with at least 3 characters.")
        elif outcome == LOGIN_DB_ERROR:
            # Deliberately distinct from "invalid identifier": this one is not
            # the student's fault and needs to be reported, not retried.
            st.error("❌ We can't reach the server right now. This is not a problem "
                     "with your identifier — please let your instructor know.")
        else:
            st.error("❌ Invalid identifier. Please check your identifier and try again.")

def chat_page(client):
    """Display the chat interface"""
    st.title("Directed Number Misconception Chatbot")

    # Display user info
    st.markdown(f"**Logged in as:** {st.session_state['user_identifier']}")

    # Logout button
    col1, col2, col3 = st.columns([1, 1, 1])
    with col3:
        if st.button("Logout", key="logout"):
            # Mark the conversation finished before clearing it. Logging out must
            # happen even if the save fails, otherwise the button appears dead.
            if st.session_state.chat_history:
                persist_transcript(completed=True)
            st.session_state["conversation_finished"] = True
            st.session_state["logged_in"] = False
            st.session_state["chat_history"] = []
            st.session_state["response_counter"] = 0
            st.rerun()

    st.caption("Your conversation is saved automatically as you chat. "
               "Click Logout when you have finished.")

    if st.session_state.get("save_failed"):
        st.warning("⚠️ Couldn't reach the database on the last save. "
                   "Keep chatting — it will retry automatically.")

    st.markdown("---")

    # Display chat history
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Chat input
    MAX_RESPONSES = 50
    if prompt := st.chat_input(
        "Ask Tegan about directed numbers...",
        disabled=st.session_state.response_counter >= MAX_RESPONSES
    ):
        # Add user message to history
        st.session_state.chat_history.append({"role": "user", "content": prompt})

        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)

        # Generate AI response
        if st.session_state.response_counter < MAX_RESPONSES:
            with st.chat_message("assistant"):
                try:
                    # Thinking is on by default on Sonnet 5 and would both delay the
                    # first token and eat into max_tokens. Tegan gives short, casual
                    # answers, so it is disabled deliberately.
                    with client.messages.stream(
                        model="claude-sonnet-5",
                        system=st.session_state["chatbot_prompt"],
                        messages=st.session_state.chat_history,
                        max_tokens=2048,
                        thinking={"type": "disabled"},
                        output_config={"effort": "low"},
                    ) as stream:
                        # write_stream renders each chunk and returns the joined text;
                        # st.write returns None, which would store a null transcript
                        # entry and break the next request.
                        response = st.write_stream(stream.text_stream)

                    # Add AI response to history
                    st.session_state.chat_history.append({"role": "assistant", "content": response})
                    st.session_state.response_counter += 1
                    persist_transcript()

                except Exception as e:
                    st.error(f"Error generating response: {str(e)}")
                    # Add error message to history
                    error_msg = "Sorry, I encountered an error. Please try again."
                    st.session_state.chat_history.append({"role": "assistant", "content": error_msg})
                    # Save anyway: the student's question is worth keeping.
                    persist_transcript()
        else:
            with st.chat_message("assistant"):
                st.markdown("I've reached the maximum number of responses for this session. Thanks for chatting!")
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": "I've reached the maximum number of responses for this session. Thanks for chatting!"
            })
            persist_transcript()

def main():
    """Main application function"""
    st.set_page_config(
        page_title="Directed Number Misconceptions Chatbot",
        page_icon="🤖",
        layout="wide"
    )

    # Initialize session state and get client
    client = setup_session_state()

    if not client:
        st.error("Failed to initialize AI client. Please check your configuration.")
        return

    # Route to appropriate page
    if not st.session_state.get("logged_in", False):
        login_page()
    else:
        chat_page(client)

if __name__ == "__main__":
    main()
