import os

def link_to_node(map_id: str, node_id: str) -> str:
    url_from_env = os.getenv('RF_URL')
    base_url = url_from_env if url_from_env is not None else 'https://beta.app.redforester.com'
    return f'{base_url}/mindmap?mapid={map_id}&nodeid={node_id}'


def link_to_file(file_id: str, file_name: str) -> str:
    url_from_env = os.getenv('RF_URL')
    base_url = url_from_env if url_from_env is not None else 'https://beta.app.redforester.com'
    return f'{base_url}/api/files/{file_id}?filename={file_name}'
