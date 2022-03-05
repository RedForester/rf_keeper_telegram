from typing import Optional

from pathvalidate import sanitize_filename
from rf_api_client.models.nodes_api_models import FileInfoDto

from db import UserContext
from api import UploadFileData, upload_file
from exceptions import AppException
from utils.file_guess import guess_file_extension
from utils.html import tg_html_to_rf_html, CUSTOM_SUBS
from utils.rf_links import link_to_file


class UnsupportedContentException(AppException):
    pass


class ContentHandler:
    SUPPORTED_TYPES = ['text', 'photo', 'audio', 'voice', 'video', 'video_note', 'document']
    ALL_TYPES = [*SUPPORTED_TYPES, 'location', 'venue', 'contact', 'sticker', 'animation']

    def __init__(self, bot):
        self._bot = bot

    @staticmethod
    def is_supported(message):
        return message.content_type in ContentHandler.SUPPORTED_TYPES

    async def _upload_file(self, ctx: UserContext, file_id: str, file_name: str) -> UploadFileData:
        file_info = await self._bot.get_file(file_id)
        file_content = await self._bot.download_file(file_info.file_path)

        return await upload_file(ctx, file_content, file_name)

    @staticmethod
    def _process_media(upload_info: UploadFileData, caption: Optional[str]):
        return (
            tg_html_to_rf_html(caption) if caption else '',
            [FileInfoDto(
                name=upload_info.file_name,
                filepath=upload_info.file_id,
                last_modified_timestamp=upload_info.timestamp,
                last_modified_user=upload_info.user_id
            )]
        )

    @staticmethod
    def _process_forwarded(message, content: str) -> str:
        source_url = None

        if message.forward_from:
            user = message.forward_from
            source_title = f'{user.first_name} {user.last_name}' if user.last_name else user.first_name
            if user.username:
                source_url = f'https://t.me/{user.username}'

        elif message.forward_from_chat:
            channel = message.forward_from_chat
            source_title = channel.title
            if channel.username:
                source_url = f'https://t.me/{channel.username}'
                if message.forward_from_message_id:
                    source_url += f'/{message.forward_from_message_id}'

        else:
            return content

        source = f'<a href="{source_url}" target="_blank">{source_title}</a>' if source_url else source_title
        return f'<p>Forwarded from {source}:</p>' + content

    async def handle(self, ctx: UserContext, message):
        # html formatting customization
        message.custom_subs = CUSTOM_SUBS

        if message.text:
            content = tg_html_to_rf_html(message.html_text)
            files = None

        elif message.photo:
            photo = message.photo[-1]  # best quality photo

            file_name = f'image.jpg'  # always jpeg
            upload_info = await self._upload_file(ctx, photo.file_id, file_name)
            content, files = self._process_media(upload_info, message.html_caption)

            url = link_to_file(upload_info.file_id, file_name)
            content = f'<p><img src="{url}" height="{photo.height}" width="{photo.width}"></p>' + content

        elif message.audio:
            file_extension = guess_file_extension(message.audio.mime_type)
            file_name = sanitize_filename(
                f'{message.audio.title or "Unknown"} - {message.audio.performer or "Unknown"}{file_extension}')
            content, files = self._process_media(await self._upload_file(ctx, message.audio.file_id, file_name), message.html_caption)

        elif message.voice:
            # always .oga?
            file_extension = guess_file_extension(message.voice.mime_type)
            file_name = sanitize_filename(
                f'{message.voice.title or "Unknown"} - {message.voice.performer or "Unknown"}{file_extension}')
            content, files = self._process_media(await self._upload_file(ctx, message.voice.file_id, file_name), message.html_caption)

        elif message.video:
            file_extension = guess_file_extension(message.video.mime_type)
            file_name = f'video{file_extension}'
            content, files = self._process_media(await self._upload_file(ctx, message.video.file_id, file_name), message.html_caption)

        elif message.video_note:
            file_name = 'video_note.mp4'  # video_note has no mime type
            content, files = self._process_media(await self._upload_file(ctx, message.video_note.file_id, file_name), message.html_caption)

        elif message.document:
            file_name = sanitize_filename(message.document.file_name or 'unknown')
            content, files = self._process_media(await self._upload_file(ctx, message.document.file_id, file_name), message.html_caption)

        else:
            raise UnsupportedContentException()

        content = self._process_forwarded(message, content)

        return content, files
