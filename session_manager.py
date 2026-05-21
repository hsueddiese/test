"""
Session manager for Claude API conversations.
Handles session expiration and "No conversation found" errors gracefully.
"""

import time
import logging
from typing import Optional
import anthropic

logger = logging.getLogger(__name__)

SESSION_EXPIRATION_ERRORS = {
    "No conversation found",
    "session not found",
    "conversation expired",
}


class SessionExpiredError(Exception):
    pass


class ConversationSession:
    def __init__(self, client: anthropic.Anthropic, model: str = "claude-sonnet-4-6"):
        self.client = client
        self.model = model
        self.messages: list[dict] = []
        self._created_at: float = time.time()

    def _is_session_expired_error(self, error: Exception) -> bool:
        error_str = str(error).lower()
        return any(msg.lower() in error_str for msg in SESSION_EXPIRATION_ERRORS)

    def send_message(self, user_message: str, max_retries: int = 1) -> str:
        self.messages.append({"role": "user", "content": user_message})

        for attempt in range(max_retries + 1):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=1024,
                    messages=self.messages,
                )
                assistant_message = response.content[0].text
                self.messages.append({"role": "assistant", "content": assistant_message})
                return assistant_message

            except anthropic.APIError as e:
                if self._is_session_expired_error(e):
                    if attempt < max_retries:
                        logger.warning("Session expired, resetting conversation history")
                        self._reset_with_last_message(user_message)
                        continue
                    raise SessionExpiredError("Session could not be recovered after reset") from e
                raise

    def _reset_with_last_message(self, last_user_message: str) -> None:
        """Clear history but keep the last user message to retry."""
        self.messages = [{"role": "user", "content": last_user_message}]
        self._created_at = time.time()


class SessionManager:
    """
    Manages a pool of conversation sessions.
    Automatically creates a new session when the current one expires.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-sonnet-4-6"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self._session: Optional[ConversationSession] = None

    @property
    def session(self) -> ConversationSession:
        if self._session is None:
            self._session = ConversationSession(self.client, self.model)
        return self._session

    def new_session(self) -> ConversationSession:
        self._session = ConversationSession(self.client, self.model)
        return self._session

    def send_message(self, message: str) -> str:
        try:
            return self.session.send_message(message, max_retries=1)
        except SessionExpiredError:
            logger.info("Creating fresh session after unrecoverable expiration")
            self.new_session()
            return self.session.send_message(message, max_retries=0)
