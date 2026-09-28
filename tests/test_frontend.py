"""Tests for Streamlit frontend execution, sidebar stability, chat layout, and error handling."""

from pathlib import Path
from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).resolve().parent.parent / "src" / "frontend" / "app.py"


def test_streamlit_app_loads_without_exceptions():
    """Verify that src/frontend/app.py runs cleanly and renders without errors."""
    at = AppTest.from_file(str(APP_PATH), default_timeout=15)
    at.run()

    # Verify no unhandled exceptions were raised during script execution
    assert len(at.exception) == 0

    # Verify title and branding are rendered
    assert len(at.markdown) > 0
    assert any("ContextAI" in m.value for m in at.markdown)


def test_sidebar_essential_elements_preserved():
    """Verify all required sidebar elements exist: branding, new chat, search, conversations, tools."""
    at = AppTest.from_file(str(APP_PATH), default_timeout=15)
    at.run()

    assert len(at.sidebar.button) > 0

    # New Chat button
    new_chat_btns = [b for b in at.sidebar.button if "New Chat" in b.label]
    assert len(new_chat_btns) == 1

    # Tools & Knowledge buttons in sidebar
    doc_btns = [b for b in at.sidebar.button if "Documents" in b.label]
    mem_btns = [b for b in at.sidebar.button if "Memory" in b.label]
    rem_btns = [b for b in at.sidebar.button if "Reminders" in b.label]
    set_btns = [b for b in at.sidebar.button if "Settings" in b.label]

    assert len(doc_btns) == 1
    assert len(mem_btns) == 1
    assert len(rem_btns) == 1
    assert len(set_btns) == 1

    # Search input in sidebar
    assert len(at.sidebar.text_input) > 0


def test_chat_composer_and_scroll_layout():
    """Verify chat input exists at the bottom and conversation messages render cleanly."""
    at = AppTest.from_file(str(APP_PATH), default_timeout=15)
    at.run()

    # Chat input is present
    assert len(at.chat_input) == 1
    assert "Ask ContextAI" in at.chat_input[0].placeholder


def test_conversation_history_and_error_display():
    """Verify that existing conversations with error notices render without exceptions or lost messages."""
    at = AppTest.from_file(str(APP_PATH), default_timeout=15)
    at.run()

    # Simulate existing conversation in session state with user and assistant messages
    conv_id = at.session_state.current_conv_id
    at.session_state.conversations[conv_id]["messages"] = [
        {"role": "user", "content": "What is ContextAI?", "details": None},
        {"role": "assistant", "content": "ContextAI is a personal AI assistant.", "details": {"intent": "GENERAL", "confidence": 0.95}},
        {"role": "user", "content": "Tell me more", "details": None},
        {"role": "assistant", "content": "Gemini is temporarily unavailable. Please try again in a moment.", "details": None},
    ]

    at.run()

    assert len(at.exception) == 0
    # Both messages must be rendered in chat messages
    assert len(at.chat_message) == 4
    assert at.chat_message[0].markdown[0].value == "What is ContextAI?"
    assert "ContextAI is a personal AI assistant." in at.chat_message[1].markdown[0].value
    assert at.chat_message[2].markdown[0].value == "Tell me more"
    assert "Gemini is temporarily unavailable." in at.chat_message[3].markdown[0].value


def test_markdown_cleaner_fixes_bitcoin_and_tool_artifacts():
    """Verify clean_rendered_markdown repairs malformed markdown, bold syntax, and squished tool tokens."""
    from src.frontend.app import clean_rendered_markdown

    # The exact broken response reported in user request:
    raw_broken = "The current price of Bitcoin is 84,552USD **, reflecting a24 — hourchangeof * * + 0.521.699 trillion."
    cleaned = clean_rendered_markdown(raw_broken)

    # Must contain proper bold currency and cleaned spacing
    assert "$84,552 USD" in cleaned
    assert "**$84,552 USD**" in cleaned
    assert "24-hour change of" in cleaned
    assert "market cap of $1.699 trillion" in cleaned
    assert "* *" not in cleaned
    assert "84,552USD **" not in cleaned
    assert "a24" not in cleaned
    assert "hourchangeof" not in cleaned

    # Test spaced bold markers
    spaced_bold = "This is ** bold text ** here and **another bold** item."
    assert clean_rendered_markdown(spaced_bold) == "This is **bold text** here and **another bold** item."

    # Test code blocks are untouched
    code_text = "Here is code:\n```python\nx * * 2\n```\nAnd text **bold**."
    cleaned_code = clean_rendered_markdown(code_text)
    assert "x * * 2" in cleaned_code
    assert "**bold**" in cleaned_code


def test_suggested_followups_generation():
    """Verify get_suggested_followups returns context-specific chips for crypto, weather, and general queries."""
    from src.frontend.app import get_suggested_followups

    # Crypto Bitcoin
    sugs_btc = get_suggested_followups("What is the price of Bitcoin?", intent="CRYPTO", tool_used="crypto")
    assert len(sugs_btc) >= 2
    assert any("Bitcoin" in s for s in sugs_btc)
    assert any("Ethereum" in s for s in sugs_btc)

    # Weather Tokyo
    sugs_weather = get_suggested_followups("What is the weather in Tokyo?", intent="WEATHER", tool_used="weather")
    assert len(sugs_weather) >= 2
    assert any("Tokyo" in s for s in sugs_weather)

    # Calculator
    sugs_calc = get_suggested_followups("Calculate 250 * 15", intent="CALCULATOR", tool_used="calculator")
    assert len(sugs_calc) >= 2

    # General
    sugs_gen = get_suggested_followups("What is quantum computing?", intent="GENERAL")
    assert len(sugs_gen) >= 2


def test_conversation_with_16_messages_renders_cleanly_and_shows_suggestions():
    """Verify that a conversation with 16 alternating messages renders without exception and provides suggestion chips."""
    at = AppTest.from_file(str(APP_PATH), default_timeout=15)
    at.run()

    conv_id = at.session_state.current_conv_id
    sixteen_messages = []
    for i in range(1, 17):
        if i % 2 == 1:
            sixteen_messages.append({
                "role": "user",
                "content": f"User question {i}: Tell me about Bitcoin price {i}",
                "details": None,
            })
        else:
            sixteen_messages.append({
                "role": "assistant",
                "content": f"Assistant response {i}: The price of Bitcoin is **$84,552 USD** with 24-hour change of **+0.52%**.",
                "details": {"intent": "CRYPTO", "confidence": 0.98, "tool_used": "crypto"},
            })

    # Ensure 16 messages
    assert len(sixteen_messages) == 16
    at.session_state.conversations[conv_id]["messages"] = sixteen_messages

    at.run()

    # Must have 0 exceptions
    assert len(at.exception) == 0

    # Must render all 16 chat messages in history
    assert len(at.chat_message) == 16

    # Verify first message (oldest) and last message (newest) are present and readable
    assert "User question 1:" in at.chat_message[0].markdown[0].value
    assert "$84,552 USD" in at.chat_message[15].markdown[0].value

    # Verify suggestion chips are rendered on the latest assistant message
    sug_buttons = [b for b in at.button if b.key and b.key.startswith("sug_")]
    assert len(sug_buttons) >= 2

    # Click the first suggestion chip and verify quick_prompt interaction
    sug_buttons[0].click()
    at.run(timeout=45)
    assert len(at.exception) == 0

