import re

from bs4 import BeautifulSoup, Tag


# pre, code and strikethrough underline are ok
from utils.file_guess import guess_file_type

CUSTOM_SUBS = {
    'bold': '<strong>{text}</strong>',
    'italic': '<em>{text}</em>',
    'text_link': '<a href="{url}" target="_blank">{text}</a>',
    'mention': '<a href="{url}" target="_blank">{text}</a>',
    # todo customize text_mention without breaking text_link
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
    if soup.find('pre'):
        return html

    return f'<p>{html}</p>'


ZWSP_STRING = re.compile('^\u200b+$')


def _replace_zwsp_preview(html: str) -> str:
    """
    A common Telegram trick to add the image to the text message is to wrap ZWSP characters with the link to the image.
    This function tries to find this type of link, extract it and append image tag to the bottom.
    """
    soup = BeautifulSoup(html, 'html.parser')

    zwsp_preview = soup.find('a', string=ZWSP_STRING)
    if not zwsp_preview:
        return html

    zwsp_preview.extract()

    href = zwsp_preview.attrs.get('href', '')
    file_type = guess_file_type(href)
    if file_type and file_type.startswith('image/'):
        preview = soup.new_tag('img', src=href)  # todo download image and set width and height attrs
        p = soup.new_tag('p')
        p.append(preview)
        soup.append(p)

    return str(soup)


def tg_html_to_rf_html(html: str) -> str:
    fixed_html = _fix_newlines(html)

    wrapped_html = ''.join(map(_wrap_line, fixed_html.split('\n')))

    without_zwsp_link_html = _replace_zwsp_preview(wrapped_html)

    # todo create preview for links to pages with og meta tags

    return without_zwsp_link_html


# todo release as package
def html_to_text(html: str, one_line: bool = False) -> str:
    soup = BeautifulSoup(html, 'html.parser')

    if not soup.find():
        return html  # plain text

    lines = [tag.text for tag in soup.find_all(recursive=False) if tag and tag.text.strip() != '']

    if one_line and len(lines):
        return lines[0]

    return '\n'.join(lines)
