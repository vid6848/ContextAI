"""Tests for ReminderManager and reminders API endpoints."""

import io
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient
import pymupdf
from src.backend.main import app
from src.backend.reminders.reminder_manager import ReminderManager

client = TestClient(app)


# ============================================================================
# Unit Tests for ReminderManager
# ============================================================================

def test_reminder_creation_and_retrieval(tmp_path):
    """Verify creating and retrieving reminders in SQLite."""
    db_file = str(tmp_path / "rem_test.db")
    mgr = ReminderManager(db_path=db_file)

    rem = mgr.create_reminder(
        user_id="alice",
        reminder_text="Submit project report",
        scheduled_time="2026-09-30 17:00",
    )

    assert rem["id"] > 0
    assert rem["reminder_text"] == "Submit project report"
    assert rem["scheduled_time"] == "2026-09-30 17:00"
    assert rem["status"] == "pending"

    # Fetch reminders
    reminders = mgr.get_reminders(user_id="alice")
    assert len(reminders) == 1
    assert reminders[0]["id"] == rem["id"]


def test_reminder_validation_errors(tmp_path):
    """Verify validation errors on empty reminder fields."""
    db_file = str(tmp_path / "val_test.db")
    mgr = ReminderManager(db_path=db_file)

    with pytest.raises(ValueError, match="Reminder text cannot be empty"):
        mgr.create_reminder(user_id="alice", reminder_text="", scheduled_time="2026-09-30")

    with pytest.raises(ValueError, match="User ID cannot be empty"):
        mgr.create_reminder(user_id="", reminder_text="Call mom", scheduled_time="2026-09-30")

    with pytest.raises(ValueError, match="Scheduled time cannot be empty"):
        mgr.create_reminder(user_id="alice", reminder_text="Call mom", scheduled_time="")


def test_reminder_completion_and_deletion(tmp_path):
    """Verify marking reminder completed and deleting reminder."""
    db_file = str(tmp_path / "comp_test.db")
    mgr = ReminderManager(db_path=db_file)

    r1 = mgr.create_reminder(user_id="bob", reminder_text="Buy milk", scheduled_time="2026-09-28 10:00")
    r2 = mgr.create_reminder(user_id="bob", reminder_text="Gym workout", scheduled_time="2026-09-28 18:00")

    # Mark r1 completed
    assert mgr.complete_reminder(reminder_id=r1["id"], user_id="bob")
    pending = mgr.get_reminders(user_id="bob", status="pending")
    assert len(pending) == 1
    assert pending[0]["id"] == r2["id"]

    completed = mgr.get_reminders(user_id="bob", status="completed")
    assert len(completed) == 1
    assert completed[0]["id"] == r1["id"]

    # Delete r2
    assert mgr.delete_reminder(reminder_id=r2["id"], user_id="bob")
    assert len(mgr.get_reminders(user_id="bob")) == 1

    # Non-existent reminder
    assert not mgr.complete_reminder(reminder_id=9999, user_id="bob")
    assert not mgr.delete_reminder(reminder_id=9999, user_id="bob")


# ============================================================================
# API Endpoint Tests
# ============================================================================

def test_api_create_and_get_reminders():
    """Verify /api/v1/reminders POST and GET endpoints."""
    create_payload = {
        "reminder_text": "Meeting with advisor",
        "scheduled_time": "2026-10-01 14:00",
        "user_id": "test_user",
    }
    resp = client.post("/api/v1/reminders", json=create_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"]
    rem_id = data["reminder"]["id"]

    # Get reminders
    get_resp = client.get("/api/v1/reminders?user_id=test_user")
    assert get_resp.status_code == 200
    reminders = get_resp.json()["reminders"]
    assert len(reminders) >= 1
    assert any(r["id"] == rem_id for r in reminders)


def test_api_complete_and_delete_reminder():
    """Verify /complete and DELETE endpoints for reminders."""
    create_payload = {
        "reminder_text": "Dentist appointment",
        "scheduled_time": "2026-10-05 09:30",
        "user_id": "api_user",
    }
    resp = client.post("/api/v1/reminders", json=create_payload)
    rem_id = resp.json()["reminder"]["id"]

    # Complete reminder
    patch_resp = client.patch(f"/api/v1/reminders/{rem_id}/complete?user_id=api_user")
    assert patch_resp.status_code == 200
    assert patch_resp.json()["success"]

    # Delete reminder
    del_resp = client.delete(f"/api/v1/reminders/{rem_id}?user_id=api_user")
    assert del_resp.status_code == 200
    assert del_resp.json()["success"]

    # Verify not found on second delete
    del_resp2 = client.delete(f"/api/v1/reminders/{rem_id}?user_id=api_user")
    assert del_resp2.status_code == 404


def test_api_clear_memory():
    """Verify /api/v1/memory/clear endpoint."""
    resp = client.post("/api/v1/memory/clear", json={"user_id": "mem_user"})
    assert resp.status_code == 200
    assert resp.json()["success"]


def test_api_documents_upload_and_status():
    """Verify /api/v1/documents/upload and /api/v1/documents endpoints."""
    # Create sample in-memory PDF
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "ContextAI sample document content for API testing.")
    pdf_bytes = doc.write()
    doc.close()

    # Upload PDF
    files = {"file": ("api_test.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    upload_resp = client.post("/api/v1/documents/upload", files=files)
    assert upload_resp.status_code == 200
    upload_data = upload_resp.json()
    assert upload_data["success"]
    assert upload_data["document_name"] == "api_test.pdf"
    assert upload_data["total_pages"] == 1
    assert upload_data["total_chunks"] >= 1

    # Check status endpoint
    status_resp = client.get("/api/v1/documents")
    assert status_resp.status_code == 200
    assert status_resp.json()["total_chunks"] >= 1


def test_api_documents_upload_invalid_file():
    """Verify /api/v1/documents/upload rejects non-PDF files."""
    files = {"file": ("test.txt", io.BytesIO(b"hello world"), "text/plain")}
    resp = client.post("/api/v1/documents/upload", files=files)
    assert resp.status_code == 400
    assert "Only PDF files are supported" in resp.json()["detail"]
