"""Tests for session expiration handling."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
import anthropic

from session_manager import ConversationSession, SessionManager, SessionExpiredError


def make_mock_response(text: str):
    response = MagicMock()
    response.content = [MagicMock(text=text)]
    return response


def make_expired_session_error():
    return anthropic.APIError(
        message="No conversation found",
        request=MagicMock(),
        body={"error": {"message": "No conversation found"}},
    )


class TestConversationSession:
    def setup_method(self):
        self.client = MagicMock()
        self.session = ConversationSession(self.client, model="claude-sonnet-4-6")

    def test_send_message_success(self):
        self.client.messages.create.return_value = make_mock_response("Hello!")
        result = self.session.send_message("Hi")
        assert result == "Hello!"
        assert len(self.session.messages) == 2

    def test_session_expired_retries_with_reset(self):
        self.client.messages.create.side_effect = [
            make_expired_session_error(),
            make_mock_response("Recovered response"),
        ]
        result = self.session.send_message("Hi", max_retries=1)
        assert result == "Recovered response"
        assert self.client.messages.create.call_count == 2

    def test_session_expired_no_retry_raises(self):
        self.client.messages.create.side_effect = make_expired_session_error()
        with pytest.raises(SessionExpiredError):
            self.session.send_message("Hi", max_retries=0)

    def test_messages_accumulate_across_turns(self):
        self.client.messages.create.side_effect = [
            make_mock_response("First"),
            make_mock_response("Second"),
        ]
        self.session.send_message("Turn 1")
        self.session.send_message("Turn 2")
        assert len(self.session.messages) == 4

    def test_reset_clears_history_keeps_last_message(self):
        self.session.messages = [
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "old reply"},
        ]
        self.session._reset_with_last_message("new message")
        assert self.session.messages == [{"role": "user", "content": "new message"}]


class TestSessionManager:
    def setup_method(self):
        with patch("session_manager.anthropic.Anthropic"):
            self.manager = SessionManager(api_key="test-key")
        self.manager.client = MagicMock()

    def test_send_message_creates_session_on_demand(self):
        self.manager.client.messages.create.return_value = make_mock_response("OK")
        assert self.manager._session is None
        result = self.manager.send_message("Hello")
        assert result == "OK"
        assert self.manager._session is not None

    def test_creates_new_session_on_unrecoverable_expiration(self):
        self.manager.client.messages.create.side_effect = [
            make_expired_session_error(),
            make_expired_session_error(),
            make_mock_response("Fresh session reply"),
        ]
        result = self.manager.send_message("Hello")
        assert result == "Fresh session reply"

    def test_new_session_resets_state(self):
        first = self.manager.session
        second = self.manager.new_session()
        assert first is not second
        assert self.manager._session is second
