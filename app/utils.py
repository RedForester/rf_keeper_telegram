import re
from typing import Tuple, Optional


def link_to_node(map_id: str, node_id: str) -> str:
    return f'https://beta.app.redforester.com/mindmap?mapid={map_id}&nodeid={node_id}'


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
