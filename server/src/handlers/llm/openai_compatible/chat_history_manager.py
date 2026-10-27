from dataclasses import dataclass
from typing import Literal, Optional

from engine_utils.text_utils import speakable_text


@dataclass
class HistoryMessage:
    role: Optional[Literal['avatar', 'human']] = None
    content: str = ''
    timestamp: Optional[str] = None


name_dict = {
    "avatar": "assistant",
    "human": "user"
}


def filter_text(text):
    return speakable_text(text)


class ChatHistory:
    def __init__(self, history_length):
        self.max_history_length = history_length
        self.message_history = []

    def add_message(self, message: HistoryMessage):
        history = self.message_history
        history.append(message)
        # thread safe
        while len(history) >= self.max_history_length:
            history.pop(0)

    def generate_next_messages(self, chat_text):
        def history_to_message(history: HistoryMessage):
            return {
                "role": name_dict[history.role],
                "content": filter_text(history.content),
            }
        messages = list(map(history_to_message, self.message_history))
        messages.append({
            "role": "user",
            "content": filter_text(chat_text),
        })
        return messages
