"""ContextAI - Premium Dark AI Assistant Frontend.

A refined, minimal dark AI chat interface inspired by modern AI assistant products.
Communicates strictly via REST API with the FastAPI backend.
"""

import base64
import os
import re
import uuid
from datetime import datetime, time
from pathlib import Path
from typing import Any
import requests
import streamlit as st

# ============================================================================
# Page Configuration & Styling
# ============================================================================

st.set_page_config(
    page_title="ContextAI",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

BACKEND_URL = os.getenv("BACKEND_API_URL", "http://localhost:8000").rstrip("/")
CURRENT_USER_ID = "default_user"

# Load logo image as base64 for inline embedding
_ASSETS_DIR = Path(__file__).resolve().parent / "assets"


def _load_logo_b64(filename: str) -> str:
    """Load a PNG logo from assets and return a data URI."""
    path = _ASSETS_DIR / filename
    if path.exists():
        data = path.read_bytes()
        b64 = base64.b64encode(data).decode()
        return f"data:image/png;base64,{b64}"
    return ""


LOGO_SIDEBAR_URI = _load_logo_b64("logo_sidebar.png")
LOGO_HERO_URI = _load_logo_b64("logo_hero.png")


# ============================================================================
# Response Text & Markdown Normalization
# ============================================================================

def clean_rendered_markdown(text: str) -> str:
    """Normalize and repair markdown/spacing artifacts in LLM & tool outputs.

    Fixes broken bold markers (e.g. '* *' -> '**'), squished word tokens
    (e.g. 'a24' -> 'a 24', 'hourchangeof' -> 'hour change of'), currency values
    (e.g. '84,552USD **' -> '**$84,552 USD**'), and unbalanced asterisks.
    Preserves existing code blocks, headings, lists, and links.
    """
    if not text:
        return ""

    # Split by fenced code blocks to avoid altering intentional code/syntax
    parts = text.split("```")
    for i in range(0, len(parts), 2):
        chunk = parts[i]

        # 1. Fix detached asterisks: "* *" or "*   *" -> "**"
        chunk = re.sub(r"\*\s+\*", "**", chunk)

        # 2. Fix squished word/number artifacts from fast tool serialization
        chunk = re.sub(r"\ba(\d{1,3})\b", r"a \1", chunk)
        chunk = re.sub(r"\bhourchangeof\b", "hour change of", chunk, flags=re.IGNORECASE)
        chunk = re.sub(r"\bhourchange\b", "hour change", chunk, flags=re.IGNORECASE)
        chunk = re.sub(r"\bmarketcap\b", "market cap", chunk, flags=re.IGNORECASE)
        chunk = re.sub(r"\bpriceof\b", "price of", chunk, flags=re.IGNORECASE)
        chunk = re.sub(r"\bchangeof\b", "change of", chunk, flags=re.IGNORECASE)
        chunk = re.sub(r"24\s*—\s*hour", "24-hour", chunk, flags=re.IGNORECASE)

        # Fix collapsed percentage and market cap if squished: e.g. "0.521.699 trillion"
        chunk = re.sub(
            r"(\b\d+\.\d{2})(\d+\.\d+\s*(?:trillion|billion|million))\b",
            r"\1% and market cap of $\2",
            chunk,
            flags=re.IGNORECASE,
        )

        # 3. Currency values: e.g. "84,552USD" or "$84,552 USD"
        # Match number + USD when not preceded by $
        chunk = re.sub(r"(?<![\$\d,])(\d[\d,.]*)\s*(?:USD|usd)\b", r"$\1 USD", chunk)

        # Fix misplaced bold closing after currency like "is $84,552 USD **" -> "is **$84,552 USD**"
        chunk = re.sub(r"(?<!\*)(\$[\d,.]+(?:\s*USD)?)\s*\*\*", r"**\1**", chunk)

        # 4. Spaced bold markers: strip inner spaces inside bold spans
        chunk = re.sub(r"\*\*([^*\n]+)\*\*", lambda m: f"**{m.group(1).strip()}**", chunk)

        # 5. Clean stray bold asterisks followed by symbols like "** + 0.52"
        chunk = re.sub(r"(?<=\w)\s+\*\*(?=\s*[\+\-\d])", " ", chunk)
        chunk = re.sub(r"\*\*\s+(?=[\+\-\d])", "", chunk)
        chunk = re.sub(r"(?<=[a-zA-Z])(?=[\+\-\d])", " ", chunk)
        chunk = re.sub(r"([\+\-])\s+(\d)", r"\1\2", chunk)

        # 6. Balance odd count of double asterisks
        bolds = re.findall(r"\*\*", chunk)
        if len(bolds) % 2 != 0:
            if chunk.rstrip().endswith("**"):
                chunk = re.sub(r"\s*\*\*\s*$", "", chunk)
            else:
                chunk = re.sub(r"\*\*(?=[\s,.;:!?]|$)", "", chunk, count=1)
                if len(re.findall(r"\*\*", chunk)) % 2 != 0:
                    chunk = re.sub(r"\*\*", "", chunk, count=1)

        # Clean duplicate dollar signs
        chunk = re.sub(r"\$\$+", "$", chunk)

        # Normalize multiple spaces while preserving newlines
        chunk = re.sub(r"[ \t]+", " ", chunk)
        parts[i] = chunk

    return "```".join(parts)


def get_suggested_followups(
    user_query: str,
    intent: str = "GENERAL",
    tool_used: str | None = None,
    response_text: str = "",
) -> list[str]:
    """Generate 2-3 concise, context-aware follow-up suggestion prompts.

    Deterministic and lightweight to avoid unnecessary latency or LLM costs.
    """
    q_lower = user_query.lower()
    t_lower = (tool_used or "").lower()
    i_upper = intent.upper()

    # 1. Crypto suggestions
    if "crypto" in t_lower or i_upper == "CRYPTO" or any(c in q_lower for c in ["bitcoin", "btc", "eth", "crypto", "solana"]):
        if "eth" in q_lower or "ethereum" in q_lower:
            return [
                "How has Ethereum changed in 24 hours?",
                "What's Bitcoin's current price?",
                "Compare Ethereum and Solana",
            ]
        elif "sol" in q_lower or "solana" in q_lower:
            return [
                "How has Solana changed in 24 hours?",
                "What's Bitcoin's current price?",
                "Compare Solana and Ethereum",
            ]
        else:
            return [
                "How has Bitcoin changed in 24 hours?",
                "What's Ethereum's current price?",
                "Compare Bitcoin and Ethereum",
            ]

    # 2. Weather suggestions
    if "weather" in t_lower or i_upper == "WEATHER" or "weather" in q_lower or "temperature" in q_lower:
        # Extract potential city
        words = [w.strip("?,.!") for w in user_query.split()]
        city = None
        for i, w in enumerate(words):
            if w.lower() in ("in", "for", "at") and i + 1 < len(words):
                city = words[i + 1].title()
                break
        if city:
            return [
                f"What is the forecast for tomorrow in {city}?",
                f"Is it raining in {city} right now?",
                f"Compare the weather between {city} and London",
            ]
        return [
            "What is the forecast for tomorrow?",
            "What's the weather in Tokyo right now?",
            "What should I wear today?",
        ]

    # 3. Calculator suggestions
    if "calculator" in t_lower or i_upper == "CALCULATOR" or any(op in q_lower for op in ["calculate", "+", "*", "/", "sum"]):
        return [
            "Convert this result to a percentage",
            "What is this amount divided by 12?",
            "Calculate 15% tip on this amount",
        ]

    # 4. Document / RAG suggestions
    if "rag" in t_lower or i_upper == "RAG" or any(w in q_lower for w in ["document", "pdf", "file", "page"]):
        return [
            "Summarize the key points from this document",
            "What other topics are covered in this document?",
            "List any statistics or data points mentioned",
        ]

    # 5. Web Search suggestions
    if "search" in t_lower or i_upper == "SEARCH" or "search" in q_lower:
        return [
            "Tell me more about recent developments on this",
            "What are the main pros and cons?",
            "Give me a bullet-point summary",
        ]

    # 6. Reminders suggestions
    if i_upper == "REMINDER" or "remind" in q_lower:
        return [
            "Show all my pending reminders",
            "Remind me tomorrow at 9 AM",
            "How do I mark a reminder as completed?",
        ]

    # 7. General conversational follow-ups
    return [
        "Can you explain this in simpler terms?",
        "Give me a practical real-world example",
        "What are the key takeaways?",
    ]


# ============================================================================
# Premium Dark CSS - Modern ChatGPT-Style Layout & Sizing
# ============================================================================
st.markdown(
    f"""
    <style>
    /* ================================================================
       FONT & BASE TYPOGRAPHY
       Clean, modern system font stack across entire application
       ================================================================ */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, .stApp, *, *::before, *::after {{
        font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
        letter-spacing: -0.01em;
    }}

    code, pre, pre code, kbd, samp {{
        font-family: 'JetBrains Mono', 'Fira Code', Menlo, Consolas, monospace !important;
    }}

    html, body {{
        margin: 0 !important;
        padding: 0 !important;
        height: 100% !important;
        overflow: hidden !important;
        background-color: #080A0F !important;
        color: #F5F7FF !important;
        font-size: 16px;
        line-height: 1.6;
    }}

    /* ================================================================
       ATMOSPHERIC BACKGROUND - Subtle, premium dark theme
       ================================================================ */
    .stApp {{
        background:
            radial-gradient(ellipse 55% 40% at 50% 0%, rgba(67, 56, 202, 0.05) 0%, transparent 70%),
            radial-gradient(ellipse 45% 35% at 85% 15%, rgba(99, 102, 241, 0.03) 0%, transparent 60%),
            #080A0F !important;
    }}

    /* ================================================================
       HEADER & RECOVERABILITY CONTROLS
       ================================================================ */
    header[data-testid="stHeader"] {{
        background: transparent !important;
        background-color: transparent !important;
        height: 3rem !important;
        z-index: 90 !important;
        pointer-events: none !important;
    }}
    header[data-testid="stHeader"] * {{
        pointer-events: auto !important;
    }}

    [data-testid="stToolbar"] {{
        background: transparent !important;
        background-color: transparent !important;
    }}

    .stDeployButton,
    [data-testid="stAppDeployButton"],
    [data-testid="stToolbarActions"],
    #MainMenu,
    footer {{
        display: none !important;
    }}

    /* Sidebar toggle button (expand & collapse) */
    [data-testid="stExpandSidebarButton"],
    [data-testid="collapsedControl"] {{
        display: flex !important;
        visibility: visible !important;
        align-items: center !important;
        justify-content: center !important;
        position: fixed !important;
        top: 0.65rem !important;
        left: 0.75rem !important;
        z-index: 9999 !important;
        background-color: #0D1117 !important;
        border: 1px solid #252C3A !important;
        border-radius: 8px !important;
        color: #A7AFBF !important;
        width: 36px !important;
        height: 36px !important;
        cursor: pointer !important;
        transition: all 0.15s ease-in-out !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4) !important;
    }}
    [data-testid="stExpandSidebarButton"]:hover,
    [data-testid="collapsedControl"]:hover {{
        background-color: #121722 !important;
        border-color: #6366f1 !important;
        color: #F5F7FF !important;
    }}
    [data-testid="stExpandSidebarButton"] svg,
    [data-testid="collapsedControl"] svg {{
        fill: currentColor !important;
    }}

    [data-testid="stSidebarCollapseButton"] {{
        color: #6B7280 !important;
        border-radius: 6px !important;
        transition: all 0.15s ease-in-out !important;
    }}
    [data-testid="stSidebarCollapseButton"]:hover {{
        background-color: #121722 !important;
        color: #F5F7FF !important;
    }}

    /* ================================================================
       SIDEBAR - 290px Fixed Navigation Column with 20-24px padding
       ================================================================ */
    section[data-testid="stSidebar"] {{
        width: 295px !important;
        min-width: 295px !important;
        background-color: #0D1117 !important;
        border-right: 1px solid #1E2533 !important;
        transition: transform 0.25s ease-in-out, width 0.25s ease-in-out !important;
    }}
    [data-testid="stSidebar"] > div:first-child,
    [data-testid="stSidebarContent"] {{
        padding: 1.5rem 1.35rem 2rem 1.35rem !important;
    }}
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{
        gap: 0.35rem;
    }}

    /* Brand header */
    .brand-container {{
        display: flex;
        align-items: center;
        gap: 0.75rem;
        padding: 0.25rem 0 1.25rem 0;
    }}
    .brand-logo-wrapper {{
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
    }}
    .brand-logo-wrapper img {{
        width: 32px;
        height: 32px;
        object-fit: contain;
        border-radius: 6px;
    }}
    .brand-title {{
        font-size: 21px;
        font-weight: 700;
        letter-spacing: -0.03em;
        color: #F5F7FF;
    }}
    .brand-badge {{
        font-size: 11.5px;
        font-weight: 600;
        background-color: #141A26;
        border: 1px solid #232D3F;
        color: #94A3B8;
        padding: 0.15rem 0.5rem;
        border-radius: 9999px;
        margin-left: auto;
    }}

    /* Sidebar Section Headings */
    .sidebar-label {{
        font-size: 12.5px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #64748B;
        padding: 0.75rem 0.25rem 0.4rem 0.25rem;
    }}

    /* Spacers & Visual Gap */
    .sidebar-spacer {{
        height: 14px;
    }}
    .sidebar-gap {{
        height: 48px;
    }}
    .sidebar-section-divider {{
        height: 1px;
        background: #1E2533;
        margin: 0.5rem 0 1rem 0;
    }}

    /* Primary New Chat CTA Button */
    .st-key-btn_new_chat button,
    [data-testid="stSidebar"] .st-key-btn_new_chat button {{
        height: 48px !important;
        min-height: 48px !important;
        background: linear-gradient(135deg, #2563EB 0%, #4F46E5 50%, #7C3AED 100%) !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        color: #FFFFFF !important;
        font-weight: 600 !important;
        font-size: 15.5px !important;
        border-radius: 10px !important;
        padding: 0 1rem !important;
        box-shadow: 0 4px 14px rgba(79, 70, 229, 0.3) !important;
        transition: all 0.2s ease-in-out !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        width: 100% !important;
    }}
    .st-key-btn_new_chat button:hover,
    [data-testid="stSidebar"] .st-key-btn_new_chat button:hover {{
        background: linear-gradient(135deg, #1D4ED8 0%, #4338CA 50%, #6D28D9 100%) !important;
        box-shadow: 0 6px 20px rgba(99, 102, 241, 0.45) !important;
        transform: translateY(-1px);
    }}

    /* Conversation row */
    [data-testid="stSidebar"] div[data-testid="stHorizontalBlock"] {{
        align-items: center !important;
        gap: 4px !important;
        margin-bottom: 2px !important;
    }}

    /* Recent Conversation title buttons */
    [data-testid="stSidebar"] div[data-testid="stColumn"]:first-child button {{
        height: 42px !important;
        min-height: 42px !important;
        max-height: 42px !important;
        padding: 0 0.85rem !important;
        font-size: 15px !important;
        font-weight: 400 !important;
        border-radius: 8px !important;
        border: 1px solid transparent !important;
        background-color: transparent !important;
        color: #94A3B8 !important;
        text-align: left !important;
        justify-content: flex-start !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        transition: all 0.15s ease-in-out !important;
    }}
    [data-testid="stSidebar"] div[data-testid="stColumn"]:first-child button:hover {{
        background-color: #121722 !important;
        border-color: #1E2533 !important;
        color: #F5F7FF !important;
    }}
    [data-testid="stSidebar"] div[data-testid="stColumn"]:first-child button[kind="primary"] {{
        background-color: #121722 !important;
        border-color: #1E2533 !important;
        border-left: 3px solid #6366f1 !important;
        color: #F5F7FF !important;
        font-weight: 500 !important;
    }}

    /* Sidebar Popover action button */
    [data-testid="stSidebar"] [data-testid="stPopover"] {{
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        height: 42px !important;
    }}
    [data-testid="stSidebar"] [data-testid="stPopover"] > div {{
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        height: 100% !important;
    }}
    [data-testid="stSidebar"] [data-testid="stPopover"] button {{
        height: 38px !important;
        min-height: 38px !important;
        max-height: 38px !important;
        width: 32px !important;
        min-width: 32px !important;
        padding: 0 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        border-radius: 8px !important;
        border: 1px solid transparent !important;
        background-color: transparent !important;
        color: #64748B !important;
        font-size: 18px !important;
        transition: all 0.15s ease-in-out !important;
    }}
    [data-testid="stSidebar"] [data-testid="stPopover"] button:hover {{
        background-color: #121722 !important;
        border-color: #1E2533 !important;
        color: #F5F7FF !important;
    }}
    [data-testid="stSidebar"] [data-testid="stPopover"] button svg {{
        display: none !important;
    }}

    /* Tools & Knowledge sidebar buttons - Neutral, dark charcoal */
    [data-testid="stSidebar"] div.stButton button:not([key="btn_new_chat"]) {{
        height: 42px !important;
        min-height: 42px !important;
        background-color: #121722 !important;
        border: 1px solid #1E2533 !important;
        border-radius: 8px !important;
        color: #D1D5DB !important;
        font-size: 15px !important;
        font-weight: 400 !important;
        padding: 0 1rem !important;
        justify-content: flex-start !important;
        text-align: left !important;
        transition: all 0.15s ease-in-out !important;
    }}
    [data-testid="stSidebar"] div.stButton button:not([key="btn_new_chat"]):hover {{
        background-color: #161D2B !important;
        border-color: #2D3748 !important;
        color: #FFFFFF !important;
    }}

    /* ================================================================
       MAIN CHAT AREA - Spacious, Centered (850-900px max-width)
       ================================================================ */
    [data-testid="stAppViewContainer"] {{
        height: 100% !important;
        overflow: hidden !important;
    }}

    [data-testid="stMain"] {{
        height: 100% !important;
        max-height: 100% !important;
        overflow-y: auto !important;
        overflow-x: hidden !important;
        overscroll-behavior-y: contain !important;
        scroll-behavior: auto !important;
        -webkit-overflow-scrolling: touch !important;
    }}

    .block-container {{
        padding-top: 2rem !important;
        padding-bottom: 10.5rem !important;
        max-width: 880px !important;
        margin: 0 auto !important;
    }}

    /* ================================================================
       REMOVE ALL MESSAGE AVATARS - Clean ChatGPT layout
       ================================================================ */
    [data-testid="stChatMessageAvatar"],
    [data-testid="chatAvatarIcon-user"],
    [data-testid="chatAvatarIcon-assistant"],
    [data-testid="stChatMessage"] svg[data-testid="stChatMessageAvatar"] {{
        display: none !important;
        width: 0 !important;
        height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
    }}

    [data-testid="stChatMessage"] {{
        background-color: transparent !important;
        border: none !important;
        padding: 0 !important;
    }}

    /* User Message Bubble - Right-aligned, subtle charcoal */
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {{
        display: flex !important;
        flex-direction: row-reverse !important;
        justify-content: flex-start !important;
        margin-top: 1.25rem !important;
        margin-bottom: 1.5rem !important;
    }}
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stChatMessageContent"] {{
        background-color: #171D29 !important;
        border: 1px solid #252C3A !important;
        border-radius: 18px 18px 4px 18px !important;
        padding: 0.85rem 1.25rem !important;
        color: #F5F7FF !important;
        font-size: 16px !important;
        line-height: 1.6 !important;
        max-width: 78% !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25) !important;
        word-break: break-word !important;
        overflow-wrap: break-word !important;
        min-width: 0 !important;
    }}

    /* Assistant Message - Clean flush layout, NO cards, NO dashboard boxes */
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {{
        display: flex !important;
        flex-direction: row !important;
        justify-content: flex-start !important;
        margin-top: 0.5rem !important;
        margin-bottom: 2rem !important;
    }}
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) [data-testid="stChatMessageContent"] {{
        background-color: transparent !important;
        border: none !important;
        padding: 0.2rem 0 !important;
        color: #E2E8F0 !important;
        font-size: 16px !important;
        line-height: 1.65 !important;
        max-width: 100% !important;
        word-break: break-word !important;
        overflow-wrap: break-word !important;
        min-width: 0 !important;
    }}

    /* Message typography */
    [data-testid="stChatMessage"] p,
    [data-testid="stChatMessage"] span,
    [data-testid="stChatMessage"] div,
    [data-testid="stChatMessage"] li {{
        font-size: 16px !important;
        line-height: 1.65 !important;
        color: #E2E8F0 !important;
    }}
    [data-testid="stChatMessage"] strong,
    [data-testid="stChatMessage"] b {{
        font-weight: 600 !important;
        color: #FFFFFF !important;
    }}
    [data-testid="stChatMessage"] h1,
    [data-testid="stChatMessage"] h2,
    [data-testid="stChatMessage"] h3,
    [data-testid="stChatMessage"] h4 {{
        color: #F5F7FF !important;
        font-weight: 600 !important;
        margin-top: 1.25rem !important;
        margin-bottom: 0.5rem !important;
    }}
    [data-testid="stChatMessage"] a {{
        color: #818CF8 !important;
        text-decoration: underline !important;
    }}

    /* Code blocks */
    pre {{
        background-color: #0D1117 !important;
        border: 1px solid #1E2533 !important;
        border-radius: 10px !important;
        padding: 1rem 1.1rem !important;
        overflow-x: auto !important;
        max-width: 100% !important;
        white-space: pre !important;
        margin: 0.85rem 0 !important;
    }}
    code {{
        font-size: 14.5px !important;
    }}
    pre code {{
        white-space: pre !important;
    }}

    /* Markdown tables */
    table {{
        display: block !important;
        overflow-x: auto !important;
        max-width: 100% !important;
        border-collapse: collapse !important;
        margin: 0.85rem 0 !important;
    }}

    /* ================================================================
       AGENT DETAILS - Compact, subtle (14px)
       ================================================================ */
    [data-testid="stChatMessage"] [data-testid="stExpander"] {{
        background-color: #0E131C !important;
        border: 1px solid #1E2533 !important;
        border-radius: 8px !important;
        margin-top: 0.85rem !important;
        margin-bottom: 0.5rem !important;
    }}
    [data-testid="stChatMessage"] [data-testid="stExpander"] summary {{
        font-size: 14px !important;
        color: #94A3B8 !important;
        padding: 0.4rem 0.8rem !important;
    }}
    .agent-details-tag {{
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        padding: 0.25rem 0.65rem;
        font-size: 13.5px !important;
        color: #94A3B8;
        background-color: #141A26;
        border: 1px solid #232D3F;
        border-radius: 6px;
        margin-right: 0.35rem;
        margin-top: 0.25rem;
    }}

    /* ================================================================
       SUGGESTED QUESTIONS - Dark neutral rounded chips (14-15px)
       ================================================================ */
    .sug-header {{
        font-size: 13px !important;
        font-weight: 500 !important;
        color: #64748B !important;
        letter-spacing: 0.04em;
        margin-top: 1rem !important;
        margin-bottom: 0.5rem !important;
    }}
    div[data-testid="stChatMessage"] div[data-testid="stColumn"] button[key^="sug_"] {{
        background-color: #121722 !important;
        border: 1px solid #252C3A !important;
        border-radius: 9999px !important;
        padding: 0.5rem 1.1rem !important;
        font-size: 14.5px !important;
        font-weight: 400 !important;
        color: #D1D5DB !important;
        line-height: 1.4 !important;
        min-height: 38px !important;
        height: auto !important;
        white-space: normal !important;
        word-break: break-word !important;
        text-align: left !important;
        justify-content: flex-start !important;
        transition: all 0.15s ease-in-out !important;
    }}
    div[data-testid="stChatMessage"] div[data-testid="stColumn"] button[key^="sug_"]:hover {{
        background-color: #1A2230 !important;
        border-color: #3B4559 !important;
        color: #FFFFFF !important;
        transform: translateY(-1px);
    }}

    /* ================================================================
       CHAT COMPOSER - Modern AI Input (58-64px high, centered 880px)
       ================================================================ */
    [data-testid="stBottom"],
    [data-testid="stBottom"] > div,
    [data-testid="stBottomBlockContainer"],
    [data-testid="stBottomBlockContainer"] > div {{
        background: transparent !important;
        background-color: transparent !important;
        pointer-events: none !important;
        z-index: 80 !important;
    }}

    [data-testid="stBottomBlockContainer"] {{
        padding-bottom: 1.75rem !important;
        max-width: 880px !important;
        margin: 0 auto !important;
    }}

    [data-testid="stChatInput"],
    [data-testid="stChatInput"] * {{
        pointer-events: auto !important;
    }}

    [data-testid="stChatInput"] {{
        background-color: #121722 !important;
        border: 1px solid #252C3A !important;
        border-radius: 18px !important;
        box-shadow: 0 6px 28px rgba(0, 0, 0, 0.5) !important;
        padding: 0.5rem 0.85rem !important;
        min-height: 58px !important;
        max-width: 880px !important;
        margin: 0 auto !important;
        transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
    }}
    [data-testid="stChatInput"]:focus-within {{
        border-color: #4F46E5 !important;
        box-shadow: 0 6px 32px rgba(79, 70, 229, 0.18) !important;
    }}
    [data-testid="stChatInput"] textarea {{
        color: #F5F7FF !important;
        font-size: 16px !important;
        line-height: 1.5 !important;
    }}
    [data-testid="stChatInput"] textarea::placeholder {{
        color: #64748B !important;
        font-size: 16px !important;
    }}

    /* ================================================================
       HERO / EMPTY STATE
       ================================================================ */
    .hero-container {{
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        text-align: center;
        padding: 4rem 1rem 2.5rem 1rem;
    }}
    .hero-avatar {{
        width: 64px;
        height: 64px;
        margin-bottom: 1.5rem;
        display: flex;
        align-items: center;
        justify-content: center;
        filter: drop-shadow(0 4px 20px rgba(99, 102, 241, 0.3));
    }}
    .hero-avatar img {{
        width: 64px;
        height: 64px;
        object-fit: contain;
    }}
    .hero-title {{
        font-size: 2.2rem;
        font-weight: 600;
        letter-spacing: -0.03em;
        color: #F5F7FF;
        margin-bottom: 0.6rem;
        line-height: 1.25;
    }}
    .hero-subtitle {{
        font-size: 16px;
        color: #94A3B8;
        max-width: 540px;
        line-height: 1.6;
        margin-bottom: 2.5rem;
    }}

    /* Starter prompt cards */
    .stApp div[data-testid="stHorizontalBlock"] button[key^="start_"],
    .stApp div[data-testid="stColumn"] button[key^="start_"] {{
        min-height: 64px !important;
        height: 64px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: flex-start !important;
        padding: 0.85rem 1.2rem !important;
        border-radius: 12px !important;
        border: 1px solid #1E2533 !important;
        background-color: #121722 !important;
        color: #D1D5DB !important;
        font-size: 15px !important;
        line-height: 1.4 !important;
        text-align: left !important;
        transition: all 0.2s ease-in-out !important;
    }}
    .stApp div[data-testid="stHorizontalBlock"] button[key^="start_"]:hover,
    .stApp div[data-testid="stColumn"] button[key^="start_"]:hover {{
        border-color: #4F46E5 !important;
        background-color: #161D2B !important;
        color: #F5F7FF !important;
        transform: translateY(-1px);
    }}

    /* ================================================================
       ERROR & NOTICE CONTAINERS
       ================================================================ */
    .error-container {{
        background-color: #121722;
        border: 1px solid #252C3A;
        border-left: 3px solid #ef4444;
        border-radius: 8px;
        padding: 0.85rem 1.1rem;
        margin: 0.75rem 0;
    }}
    .error-container .error-title {{
        font-size: 15px;
        font-weight: 500;
        color: #F5F7FF;
        margin-bottom: 0.25rem;
    }}
    .error-container .error-detail {{
        font-size: 13.5px;
        color: #94A3B8;
        word-break: break-word;
    }}

    /* ================================================================
       MOBILE & RESPONSIVE DRAWER
       ================================================================ */
    @media (max-width: 768px) {{
        section[data-testid="stSidebar"] {{
            z-index: 10000 !important;
            box-shadow: 4px 0 32px rgba(0, 0, 0, 0.75) !important;
        }}
        [data-testid="stExpandSidebarButton"],
        [data-testid="collapsedControl"] {{
            top: 0.5rem !important;
            left: 0.5rem !important;
        }}
        .block-container {{
            padding-left: 1rem !important;
            padding-right: 1rem !important;
            padding-top: 3.5rem !important;
            padding-bottom: 8rem !important;
            max-width: 100% !important;
        }}
        .hero-title {{
            font-size: 1.7rem !important;
        }}
        .hero-subtitle {{
            font-size: 14.5px !important;
            margin-bottom: 1.5rem !important;
        }}
        [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stChatMessageContent"] {{
            max-width: 88% !important;
            padding: 0.75rem 1rem !important;
        }}
        [data-testid="stChatInput"] {{
            border-radius: 14px !important;
            padding: 0.35rem 0.5rem !important;
        }}
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================================
# API Service Helpers
# ============================================================================

def check_backend_health() -> bool:
    """Check if the FastAPI backend is running and healthy."""
    try:
        resp = requests.get(f"{BACKEND_URL}/health", timeout=3)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def send_chat_message(message: str, user_id: str = CURRENT_USER_ID) -> dict[str, Any] | None:
    """Send user query to backend /api/v1/chat endpoint."""
    try:
        payload = {"message": message, "user_id": user_id}
        resp = requests.post(f"{BACKEND_URL}/api/v1/chat", json=payload, timeout=60)
        if resp.status_code == 200:
            return resp.json()
        # Parse error detail from structured response if available
        try:
            error_data = resp.json()
            detail = error_data.get("detail", resp.text)
        except Exception:
            detail = resp.text
        return {"_error": True, "_status": resp.status_code, "_detail": str(detail)}
    except requests.RequestException as err:
        return {"_error": True, "_status": 0, "_detail": f"Unable to connect to ContextAI backend. {err}"}


def upload_pdf_document(uploaded_file) -> dict[str, Any] | None:
    """Send uploaded PDF to /api/v1/documents/upload."""
    try:
        files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
        resp = requests.post(f"{BACKEND_URL}/api/v1/documents/upload", files=files, timeout=60)
        if resp.status_code == 200:
            return resp.json()
        st.error(f"Upload failed ({resp.status_code}): {resp.text}")
        return None
    except requests.RequestException as err:
        st.error(f"Document upload error: {err}")
        return None


def fetch_document_count() -> int:
    """Fetch count of indexed document chunks from backend."""
    try:
        resp = requests.get(f"{BACKEND_URL}/api/v1/documents", timeout=5)
        if resp.status_code == 200:
            return resp.json().get("total_chunks", 0)
        return 0
    except requests.RequestException:
        return 0


def clear_memory(user_id: str = CURRENT_USER_ID) -> bool:
    """Request backend to clear conversation history."""
    try:
        resp = requests.post(
            f"{BACKEND_URL}/api/v1/memory/clear",
            json={"user_id": user_id},
            timeout=10,
        )
        return resp.status_code == 200
    except requests.RequestException:
        return False


def fetch_reminders(user_id: str = CURRENT_USER_ID, status: str | None = None) -> list[dict[str, Any]]:
    """Retrieve list of reminders from backend."""
    try:
        params: dict[str, str] = {"user_id": user_id}
        if status:
            params["status"] = status
        resp = requests.get(f"{BACKEND_URL}/api/v1/reminders", params=params, timeout=5)
        if resp.status_code == 200:
            return resp.json().get("reminders", [])
        return []
    except requests.RequestException:
        return []


def create_reminder(reminder_text: str, scheduled_time: str, user_id: str = CURRENT_USER_ID) -> bool:
    """Create a new reminder via backend API."""
    try:
        payload = {
            "reminder_text": reminder_text,
            "scheduled_time": scheduled_time,
            "user_id": user_id,
        }
        resp = requests.post(f"{BACKEND_URL}/api/v1/reminders", json=payload, timeout=10)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def complete_reminder(reminder_id: int, user_id: str = CURRENT_USER_ID) -> bool:
    """Mark a reminder completed via backend API."""
    try:
        resp = requests.patch(
            f"{BACKEND_URL}/api/v1/reminders/{reminder_id}/complete",
            params={"user_id": user_id},
            timeout=5,
        )
        return resp.status_code == 200
    except requests.RequestException:
        return False


def delete_reminder(reminder_id: int, user_id: str = CURRENT_USER_ID) -> bool:
    """Delete a reminder via backend API."""
    try:
        resp = requests.delete(
            f"{BACKEND_URL}/api/v1/reminders/{reminder_id}",
            params={"user_id": user_id},
            timeout=5,
        )
        return resp.status_code == 200
    except requests.RequestException:
        return False


# ============================================================================
# Session State Management
# ============================================================================

def init_new_conversation() -> str:
    """Initialize a fresh conversation and register in session state."""
    new_id = f"chat_{uuid.uuid4().hex[:8]}"
    if "conversations" not in st.session_state:
        st.session_state.conversations = {}

    st.session_state.conversations[new_id] = {
        "id": new_id,
        "title": "New conversation",
        "created_at": datetime.now().strftime("%b %d, %H:%M"),
        "messages": [],
    }
    return new_id


if "conversations" not in st.session_state or not st.session_state.conversations:
    first_id = init_new_conversation()
    st.session_state.current_conv_id = first_id

if "current_conv_id" not in st.session_state or st.session_state.current_conv_id not in st.session_state.conversations:
    st.session_state.current_conv_id = list(st.session_state.conversations.keys())[0]

current_chat = st.session_state.conversations[st.session_state.current_conv_id]


# ============================================================================
# Modals / Panels (using native @st.dialog)
# ============================================================================

@st.dialog("📄 Documents & Knowledge Base", width="large")
def show_documents_dialog() -> None:
    """Modal dialog for PDF upload, RAG indexing status, and management."""
    st.caption("Upload local PDF files to expand ContextAI's semantic document retrieval knowledge base.")

    pdf_upload = st.file_uploader("Select a PDF document", type=["pdf"])
    if pdf_upload is not None:
        if st.button("Index PDF into Knowledge Base", type="primary", use_container_width=True):
            with st.spinner("Extracting text with PyMuPDF and embedding into ChromaDB..."):
                res = upload_pdf_document(pdf_upload)
                if res and res.get("success"):
                    st.success(
                        f"Indexed **{res.get('document_name')}** successfully: "
                        f"{res.get('total_pages')} pages, {res.get('total_chunks')} chunks."
                    )
                else:
                    st.error("Failed to index PDF document.")

    st.markdown("---")
    chunk_count = fetch_document_count()
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Total Indexed Chunks", chunk_count)
    with col2:
        st.metric("Vector Collection", "document_rag")

    st.info("💡 You can ask questions about your uploaded documents in any chat session. The agent will cite page numbers.")


@st.dialog("🧠 Persistent Memory Management", width="large")
def show_memory_dialog() -> None:
    """Modal dialog for inspecting and clearing conversation memory."""
    st.caption("ContextAI continuously manages two persistent memory layers for your user session.")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Short-Term Conversation History**")
        st.caption("Maintained in SQLite. Retains recent messages chronologically for conversation continuity.")
    with col2:
        st.markdown("**Semantic Long-Term Memory**")
        st.caption("Maintained in ChromaDB. Automatically detects and indexes personal preferences, facts, and notes.")

    st.markdown("---")
    st.markdown("#### Clear History")
    st.caption("Reset your SQLite conversation history while preserving indexed document RAG collections.")

    if st.button("Clear Conversation History", type="primary"):
        if clear_memory(CURRENT_USER_ID):
            st.toast("Conversation memory cleared.", icon="🧹")
            st.success("Your conversation memory has been cleared successfully.")
        else:
            st.error("Failed to clear conversation memory.")


@st.dialog("⏰ Reminders", width="large")
def show_reminders_dialog() -> None:
    """Modal dialog for viewing and scheduling reminders."""
    tab_active, tab_new, tab_completed = st.tabs(["Active Reminders", "New Reminder", "Completed"])

    with tab_active:
        pending_list = fetch_reminders(CURRENT_USER_ID, status="pending")
        if pending_list:
            for r in pending_list:
                col_text, col_actions = st.columns([0.78, 0.22])
                with col_text:
                    st.markdown(f"**{r['reminder_text']}**")
                    st.caption(f"📅 Due: {r['scheduled_time']}")
                with col_actions:
                    col_done, col_del = st.columns(2)
                    with col_done:
                        if st.button("✓", key=f"dlg_done_{r['id']}", help="Mark completed"):
                            complete_reminder(r["id"], CURRENT_USER_ID)
                            st.rerun()
                    with col_del:
                        if st.button("🗑️", key=f"dlg_del_{r['id']}", help="Delete reminder"):
                            delete_reminder(r["id"], CURRENT_USER_ID)
                            st.rerun()
                st.markdown("---")
        else:
            st.info("You have no pending reminders.")

    with tab_new:
        note = st.text_input("What would you like to be reminded of?", placeholder="e.g. Call dentist, submit report...")
        col_d, col_t = st.columns(2)
        with col_d:
            due_date = st.date_input("Scheduled Date", min_value=datetime.today().date())
        with col_t:
            due_time = st.time_input("Scheduled Time", value=time(hour=12, minute=0))

        if st.button("Schedule Reminder", type="primary", use_container_width=True):
            if note.strip():
                formatted_sched = f"{due_date.isoformat()} {due_time.strftime('%H:%M')}"
                if create_reminder(note.strip(), formatted_sched, CURRENT_USER_ID):
                    st.toast("Reminder scheduled!", icon="⏰")
                    st.rerun()
                else:
                    st.error("Could not schedule reminder.")
            else:
                st.warning("Please provide reminder text.")

    with tab_completed:
        comp_list = fetch_reminders(CURRENT_USER_ID, status="completed")
        if comp_list:
            for r in comp_list:
                col_c1, col_c2 = st.columns([0.85, 0.15])
                with col_c1:
                    st.markdown(f"~~{r['reminder_text']}~~")
                    st.caption(f"Completed • Was due: {r['scheduled_time']}")
                with col_c2:
                    if st.button("🗑️", key=f"dlg_delcomp_{r['id']}", help="Delete"):
                        delete_reminder(r["id"], CURRENT_USER_ID)
                        st.rerun()
        else:
            st.caption("No completed reminders recorded.")


@st.dialog("⚙️ Settings & System Information", width="medium")
def show_settings_dialog() -> None:
    """Modal dialog for settings, API configuration, and backend telemetry."""
    st.markdown("### System Configuration")
    st.markdown(f"**Backend Endpoint:** `{BACKEND_URL}`")
    is_online = check_backend_health()
    if is_online:
        st.success("● Connected to FastAPI reasoning engine")
    else:
        st.error("● Backend offline or unreachable")

    st.markdown("---")
    st.markdown("### Reasoning Stack")
    st.markdown("- **Framework:** FastAPI + LangGraph Orchestration")
    st.markdown("- **Intent Classifier:** TF-IDF + Logistic Regression")
    st.markdown("- **LLM Provider:** Gemini via LiteLLM")
    st.markdown("- **Memory:** SQLite Short-Term + ChromaDB Semantic Long-Term")
    st.markdown("- **Tools:** OpenWeather, CoinGecko, Calculator AST, Tavily Search, PyMuPDF RAG")


# ============================================================================
# Sidebar
# ============================================================================

with st.sidebar:
    # ContextAI Branding with uploaded brain logo
    logo_img_tag = f'<img src="{LOGO_SIDEBAR_URI}" alt="ContextAI" />' if LOGO_SIDEBAR_URI else "🧠"
    st.markdown(
        f"""
        <div class="brand-container">
            <div class="brand-logo-wrapper">{logo_img_tag}</div>
            <div class="brand-title">ContextAI</div>
            <div class="brand-badge">Agent</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Primary New Chat CTA button with blue-purple gradient
    if st.button("＋ New Chat", key="btn_new_chat", use_container_width=True, type="primary"):
        new_id = init_new_conversation()
        st.session_state.current_conv_id = new_id
        st.rerun()

    # Spacer before search
    st.markdown('<div class="sidebar-spacer-lg"></div>', unsafe_allow_html=True)

    # Search conversations
    search_query = st.text_input("Search chats", placeholder="Search chats...", label_visibility="collapsed")

    # Spacer before conversations section
    st.markdown('<div class="sidebar-spacer"></div>', unsafe_allow_html=True)

    # Conversation History List
    st.markdown('<div class="sidebar-label">Recent Conversations</div>', unsafe_allow_html=True)

    sorted_convs = list(st.session_state.conversations.values())
    if search_query.strip():
        sorted_convs = [
            c for c in sorted_convs if search_query.lower() in c.get("title", "").lower()
        ]

    for c in reversed(sorted_convs):
        c_id = c["id"]
        is_active = c_id == st.session_state.current_conv_id
        btn_type = "primary" if is_active else "secondary"
        btn_label = c.get('title', 'New conversation')

        # Conversation row: title on left, subtle ⋯ on right
        col_conv, col_menu = st.columns([0.84, 0.16], gap="small", vertical_alignment="center")
        with col_conv:
            if st.button(btn_label, key=f"select_{c_id}", use_container_width=True, type=btn_type):
                st.session_state.current_conv_id = c_id
                st.rerun()

        with col_menu:
            with st.popover("⋮", use_container_width=True, help="Conversation actions"):
                st.caption(f"Manage: {c.get('title', 'Chat')}")
                new_title = st.text_input("Rename", value=c.get("title", ""), key=f"ren_{c_id}")
                if st.button("Save", key=f"save_ren_{c_id}", use_container_width=True):
                    if new_title.strip():
                        c["title"] = new_title.strip()
                        st.rerun()
                if st.button("Delete", key=f"del_conv_{c_id}", type="primary", use_container_width=True):
                    del st.session_state.conversations[c_id]
                    if not st.session_state.conversations:
                        init_new_conversation()
                    st.session_state.current_conv_id = list(st.session_state.conversations.keys())[0]
                    st.rerun()

    # Clear visual gap of 48px between end of Recent Conversations and Tools & Knowledge
    st.markdown('<div class="sidebar-gap"></div>', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-section-divider"></div>', unsafe_allow_html=True)

    # Bottom Navigation - Clean, neutral buttons (no colorful icons/emojis)
    st.markdown('<div class="sidebar-label">Tools & Knowledge</div>', unsafe_allow_html=True)
    if st.button("Documents & RAG", use_container_width=True):
        show_documents_dialog()

    if st.button("Memory", use_container_width=True):
        show_memory_dialog()

    if st.button("Reminders", use_container_width=True):
        show_reminders_dialog()

    if st.button("Settings", use_container_width=True):
        show_settings_dialog()


# ============================================================================
# Main Conversation View
# ============================================================================

messages = current_chat.get("messages", [])

# Render Active Reminders Banner if any due
due_list = [r for r in fetch_reminders(CURRENT_USER_ID, status="pending") if r.get("scheduled_time", "") <= datetime.now().strftime("%Y-%m-%d %H:%M")]
for due in due_list:
    st.info(f"⏰ **Reminder Due:** {due['reminder_text']} *(Due: {due['scheduled_time']})*")

# Empty State Hero View if no messages yet
if not messages:
    hero_img_tag = f'<img src="{LOGO_HERO_URI}" alt="ContextAI" />' if LOGO_HERO_URI else "🧠"
    st.markdown(
        f"""
        <div class="hero-container">
            <div class="hero-avatar">{hero_img_tag}</div>
            <div class="hero-title">How can I help you today?</div>
            <div class="hero-subtitle">
                ContextAI is equipped with short-term & semantic memory, live tools for calculations, weather, crypto, web search, and document RAG.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Suggestion Cards Grid
    col1, col2 = st.columns(2, gap="medium")
    with col1:
        if st.button("🌦️ What is the weather in Tokyo?", use_container_width=True, key="start_1"):
            st.session_state.quick_prompt = "What is the weather in Tokyo?"
            st.rerun()
        if st.button("📈 What is the price of Bitcoin?", use_container_width=True, key="start_2"):
            st.session_state.quick_prompt = "What is the price of Bitcoin?"
            st.rerun()

    with col2:
        if st.button("🧮 Calculate (250 * 15) / 2", use_container_width=True, key="start_3"):
            st.session_state.quick_prompt = "Calculate (250 * 15) / 2"
            st.rerun()
        if st.button("🔍 Search the web for Python 3.13 features", use_container_width=True, key="start_4"):
            st.session_state.quick_prompt = "Search the web for Python 3.13 features"
            st.rerun()

# Render Conversation Messages
total_msgs = len(messages)
for idx, msg in enumerate(messages):
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            cleaned_content = clean_rendered_markdown(msg["content"])
            st.markdown(cleaned_content)
        else:
            st.markdown(msg["content"])

        # Subtle, optional "Agent details" for assistant replies
        details = msg.get("details")
        if details and (details.get("intent") or details.get("tool_used")):
            with st.expander("Agent details", expanded=False):
                intent = details.get("intent", "GENERAL")
                conf = details.get("confidence", 0.0)
                tool = details.get("tool_used") or "None"
                sources = details.get("sources")

                tags_html = f"""
                <div>
                    <span class="agent-details-tag">Intent: <b>{intent}</b></span>
                    <span class="agent-details-tag">Confidence: <b>{conf:.2f}</b></span>
                    <span class="agent-details-tag">Tool: <b>{tool}</b></span>
                </div>
                """
                st.markdown(tags_html, unsafe_allow_html=True)

                if sources:
                    st.markdown("<div style='margin-top: 0.5rem; font-size: 13.5px; color: #A7AFBF;'><b>Document Sources:</b></div>", unsafe_allow_html=True)
                    for s in sources:
                        doc_name = s.get("document", "Document")
                        p_num = s.get("page", 1)
                        st.markdown(f"- 📄 `{doc_name}` — **Page {p_num}**")

        # Suggested follow-up questions only under the latest assistant response
        if msg["role"] == "assistant" and idx == total_msgs - 1:
            last_user_query = ""
            for prev_m in reversed(messages[:idx]):
                if prev_m.get("role") == "user":
                    last_user_query = prev_m.get("content", "")
                    break

            intent_val = details.get("intent", "GENERAL") if details else "GENERAL"
            tool_val = details.get("tool_used") if details else None
            suggestions = get_suggested_followups(
                user_query=last_user_query,
                intent=intent_val,
                tool_used=tool_val,
                response_text=msg.get("content", ""),
            )

            if suggestions:
                st.markdown('<div class="sug-header">Suggested questions</div>', unsafe_allow_html=True)
                sug_cols = st.columns(len(suggestions))
                for s_i, sug_text in enumerate(suggestions):
                    with sug_cols[s_i]:
                        if st.button(sug_text, key=f"sug_{s_i}", use_container_width=True):
                            st.session_state.quick_prompt = sug_text
                            st.rerun()


# ============================================================================
# Message Composer & Interaction
# ============================================================================

# Handle prompt submitted either via chat_input or a starter pill
input_prompt = st.chat_input("Ask ContextAI a question, search, calculate, or query documents...")
if "quick_prompt" in st.session_state and st.session_state.quick_prompt:
    input_prompt = st.session_state.quick_prompt
    st.session_state.quick_prompt = None

if input_prompt:
    clean_prompt = input_prompt.strip()
    if clean_prompt:
        # Automatically derive conversation title from the first prompt
        if not messages or current_chat.get("title") == "New conversation":
            preview = clean_prompt[:28] + ("..." if len(clean_prompt) > 28 else "")
            current_chat["title"] = preview

        # 1. Append user message
        user_msg = {"role": "user", "content": clean_prompt, "details": None}
        messages.append(user_msg)

        # Immediate user message render
        with st.chat_message("user"):
            st.markdown(clean_prompt)

        # 2. Invoke backend reasoning agent with thinking animation
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                response_data = send_chat_message(clean_prompt, user_id=CURRENT_USER_ID)

            if response_data and response_data.get("_error"):
                error_detail = response_data.get("_detail", "Unknown error")
                error_status = response_data.get("_status", 0)

                # Format clean, polished user message for transient 503 / Gemini errors
                if error_status == 503 or "temporarily unavailable" in error_detail.lower():
                    user_facing_msg = "Gemini is temporarily unavailable. Please try again in a moment."
                else:
                    user_facing_msg = "Something went wrong while processing that request. Please try again."

                st.markdown(user_facing_msg)
                with st.expander("Error details", expanded=False):
                    st.markdown(
                        f'<div class="error-container">'
                        f'<div class="error-title">Service Notice ({error_status if error_status else "Offline"})</div>'
                        f'<div class="error-detail">{error_detail}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                messages.append({
                    "role": "assistant",
                    "content": user_facing_msg,
                    "details": None,
                })

            elif response_data:
                raw_reply = response_data.get("response", "I could not generate a response.")
                reply_text = clean_rendered_markdown(raw_reply)
                details = {
                    "intent": response_data.get("intent", "GENERAL"),
                    "confidence": float(response_data.get("confidence", 0.0)),
                    "tool_used": response_data.get("tool_used"),
                    "sources": response_data.get("sources"),
                }

                st.markdown(reply_text)

                if details.get("intent") or details.get("tool_used"):
                    with st.expander("Agent details", expanded=False):
                        tags_html = f"""
                        <div>
                            <span class="agent-details-tag">Intent: <b>{details['intent']}</b></span>
                            <span class="agent-details-tag">Confidence: <b>{details['confidence']:.2f}</b></span>
                            <span class="agent-details-tag">Tool: <b>{details['tool_used'] or 'None'}</b></span>
                        </div>
                        """
                        st.markdown(tags_html, unsafe_allow_html=True)
                        if details.get("sources"):
                            for s in details["sources"]:
                                st.markdown(f"- 📄 `{s.get('document', 'Document')}` — **Page {s.get('page', 1)}**")

                messages.append({
                    "role": "assistant",
                    "content": reply_text,
                    "details": details,
                })
                st.rerun()
            else:
                fallback_err = "I am currently unable to reach the ContextAI reasoning engine. Please ensure the FastAPI backend is running."
                st.markdown(fallback_err)
                messages.append({
                    "role": "assistant",
                    "content": fallback_err,
                    "details": None,
                })
