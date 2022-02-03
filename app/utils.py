import mimetypes
import re
from typing import Tuple, Optional

from bs4 import BeautifulSoup


def link_to_node(map_id: str, node_id: str) -> str:
    return f'https://beta.app.redforester.com/mindmap?mapid={map_id}&nodeid={node_id}'


def link_to_file(file_id: str, file_name: str) -> str:
    return f'https://beta.app.redforester.com/api/files/{file_id}?filename={file_name}'


map_id_re = re.compile(r'mapid=([\w-]+)')
node_id_re = re.compile(r'nodeid=([\w-]+)')


def parse_node_link(url: str) -> [Tuple[Optional[str], Optional[str]]]:
    try:
        map_id = re.search(map_id_re, url).group(1)
        node_id = re.search(node_id_re, url).group(1)

        return map_id, node_id
    except (AttributeError, IndexError, TypeError):
        return None, None


def text_to_html(text: str) -> str:
    lines = text.split('\n')
    wrapped = map(lambda line: f"<p>{line}</p>", lines)
    return ''.join(wrapped)


# todo release as package
def html_to_text(html: str, one_line: bool = False) -> str:
    soup = BeautifulSoup(html, 'html.parser')

    if not soup.find():
        return html  # plain text

    lines = [tag.text for tag in soup.find_all(recursive=False) if tag and tag.text.strip() != '']

    if one_line and len(lines):
        return lines[0]

    return "\n".join(lines)


KNOWN_EXTENSIONS = {
    'audio/mpeg': '.mp3',
    'audio/mp4': '.m4a'
}


def guess_file_extension(mime_type: str):
    return KNOWN_EXTENSIONS.get(mime_type) or mimetypes.guess_extension(mime_type)
