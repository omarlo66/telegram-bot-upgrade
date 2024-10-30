from dataclasses import dataclass, field

from telegram import File, Document, PhotoSize

from src.common.utils import format_nullable_string


@dataclass
class TelegramPhoto:
    photo_size: PhotoSize
    caption: str = None


@dataclass
class SupportResponse:
    asker_id: int
    message_id: int = None
    message: str = ''
    documents: list[Document] = field(default_factory=list)
    photos: list[TelegramPhoto] = field(default_factory=list)

    @property
    def files(self):
        return self.documents + self.photos

    @property
    def formatted_message(self):
        return (
            "رسالتك: " + format_nullable_string(self.message) + '\n' +
            "عدد الملفات المرفقة:" + str(len(self.files)) + '\n'
        )
