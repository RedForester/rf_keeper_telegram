import asyncio
from typing import TypeVar, Coroutine, Any, List

from rf_api_client import RfApiClient
from rf_api_client.models.nodes_api_models import CreateNodePropertiesDto, CreateNodeDto, PositionType, NodeDto, \
    NodeInsertOptions, NodeTreeDto
from rf_api_client.models.tags_api_models import TaggedNodeDto
from rf_api_client.models.users_api_models import UserDto
from rf_api_client.rf_api_client import UserAuth

from app.db import UserContext


T = TypeVar('T')


def execute(future: Coroutine[Any, Any, T]) -> T:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(future)


async def login_to_rf(username: str, password: str) -> UserDto:
    async with RfApiClient(
        auth=UserAuth(username=username, password=password)
    ) as rf:
        user = await rf.users.get_current()

        if user.username == "nobody":
            raise Exception("Unauthorized")

        return user


async def create_new_node(ctx: UserContext, title: str) -> NodeDto:
    async with RfApiClient(
        auth=UserAuth(username=ctx.username, password=ctx.password)
    ) as rf:
        props = CreateNodePropertiesDto.empty()
        props.global_.title = title

        return await rf.nodes.create(CreateNodeDto(
            parent=ctx.target.node_id,
            map_id=ctx.target.map_id,
            position=(PositionType.P, "-1"),
            properties=props
        ))


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
