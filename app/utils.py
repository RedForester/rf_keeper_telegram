import mimetypes
import re
from typing import Tuple, Optional

from bs4 import BeautifulSoup, Tag


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


# pre, code and strikethrough underline are ok
CUSTOM_SUBS = {
    'bold': '<strong>{text}</strong>',
    'italic': '<em>{text}</em>',
    'text_link': '<a href="{url}" target="_blank">{text}</a>',
    'url': '<a href="{text}" target="_blank">{text}</a>',
    'spoiler': '{text}',
}


def _fix_newlines(html: str) -> str:
    """
    Move newline characters out of inline tags

    Input:  <strong>bold\n\n</strong>new line
    Output: <strong>bold</strong>\n\nnew line
    """
    soup = BeautifulSoup(html, 'html.parser')

    for children in soup.children:
        if isinstance(children, Tag) and not children.find():
            match = re.search('^(.+)(\n+)$', children.string)
            text = match and match.group(1)
            breaks = match and match.group(2)
            if text and breaks:
                children.string.replace_with(text)
                children.insert_after(breaks)

    return str(soup)


def _wrap_line(html: str) -> str:
    """
    Wrap html line with p tag
    """
    if not html:
        return '<p><br></p>'

    soup = BeautifulSoup(html, 'html.parser')
    # pre is already a block element, no need to wrap it
    if soup.find("pre"):
        return html

    return f"<p>{html}</p>"


def tg_html_to_rf_html(html: str) -> str:
    fixed_html = _fix_newlines(html)

    wrapped_html = ''.join(map(_wrap_line, fixed_html.split('\n')))

    return wrapped_html


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
