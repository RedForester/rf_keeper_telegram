import mimetypes
from typing import Optional


__KNOWN_EXTENSIONS = {
    'audio/mpeg': '.mp3',
    'audio/mp4': '.m4a'
}


def guess_file_extension(mime_type: str):
    return __KNOWN_EXTENSIONS.get(mime_type) or mimetypes.guess_extension(mime_type)


def guess_file_type(filename: str) -> Optional[str]:
    return mimetypes.guess_type(filename)[0]
