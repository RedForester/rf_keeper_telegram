def link_to_node(map_id: str, node_id: str) -> str:
    return f'https://beta.app.redforester.com/mindmap?mapid={map_id}&nodeid={node_id}'


def link_to_file(file_id: str, file_name: str) -> str:
    return f'https://beta.app.redforester.com/api/files/{file_id}?filename={file_name}'
