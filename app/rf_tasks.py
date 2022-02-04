import asyncio
from datetime import datetime
from typing import TypeVar, Coroutine, Any, List, Optional

from rf_api_client import RfApiClient
from rf_api_client.models.files_api_models import UploadFileResponseDto
from rf_api_client.models.node_types_api_models import NodePropertyType
from rf_api_client.models.nodes_api_models import CreateNodePropertiesDto, CreateNodeDto, PositionType, NodeDto, \
    NodeInsertOptions, NodeTreeDto, NodeUpdateDto, PropertiesUpdateDto, UserPropertyCreateDto, FileInfoDto, \
    FilePropertyValue
from rf_api_client.models.tags_api_models import TaggedNodeDto
from rf_api_client.models.users_api_models import UserDto
from rf_api_client.rf_api_client import UserAuth

from app.db import UserContext


T = TypeVar('T')


def execute(future: Coroutine[Any, Any, T]) -> T:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(future)


class UploadFileData(UploadFileResponseDto):
    base_url: str
    file_name: str
    timestamp: datetime


async def upload_file_to_rf(ctx: UserContext, file: bytes, file_name: str) -> UploadFileData:
    async with RfApiClient(
            auth=UserAuth(username=ctx.username, password=ctx.password)
    ) as rf:
        resp = await rf.files.upload_file_bytes(file)
        return UploadFileData(
            user_id=resp.user_id,
            file_id=resp.file_id,
            base_url=str(rf.context.base_url),
            file_name=file_name,
            timestamp=datetime.now().astimezone(),
        )


async def login_to_rf(username: str, password: str) -> UserDto:
    async with RfApiClient(
        auth=UserAuth(username=username, password=password)
    ) as rf:
        user = await rf.users.get_current()

        if user.username == "nobody":
            raise Exception("Unauthorized")

        return user


async def create_new_node(ctx: UserContext, title: str, files: Optional[List[FileInfoDto]] = None) -> NodeDto:
    async with RfApiClient(
        auth=UserAuth(username=ctx.username, password=ctx.password)
    ) as rf:
        props = CreateNodePropertiesDto.empty()
        props.global_.title = title

        node = await rf.nodes.create(CreateNodeDto(
            parent=ctx.target.node_id,
            map_id=ctx.target.map_id,
            position=(PositionType.P, "-1"),
            properties=props
        ))

        if files:
            # RedForester can not create node with user property.
            node = await rf.nodes.update_by_id(node.id, NodeUpdateDto(
                properties=PropertiesUpdateDto(
                    add=[UserPropertyCreateDto(
                        group="byUser",
                        key="Files",
                        type_id=NodePropertyType.FILE,
                        visible=True,
                        value=FilePropertyValue.to_string(files),
                    )]
                )
            ))

        return node


async def get_node(ctx: UserContext, node_id: str) -> NodeDto:
    async with RfApiClient(
            auth=UserAuth(username=ctx.username, password=ctx.password)
    ) as rf:
        return await rf.nodes.get_by_id(node_id)


async def get_favorite_nodes(ctx: UserContext) -> List[TaggedNodeDto]:
    async with RfApiClient(
        auth=UserAuth(username=ctx.username, password=ctx.password)
    ) as rf:
        current = await rf.users.get_current()
        favorite_tag = current.tags[0]

        return await rf.tags.get_nodes(favorite_tag.id)


async def move_node(ctx: UserContext, node_id: str, new_parent_id: str) -> NodeTreeDto:
    async with RfApiClient(
            auth=UserAuth(username=ctx.username, password=ctx.password)
    ) as rf:
        resp = await rf.nodes.insert_to(
            node_id=node_id,
            new_parent_id=new_parent_id,
            options=NodeInsertOptions(move=True, for_branch=True)
        )

        return resp.root
