import asyncio
from typing import TypeVar, Coroutine, Any

from rf_api_client import RfApiClient
from rf_api_client.models.nodes_api_models import CreateNodePropertiesDto, CreateNodeDto, PositionType, NodeDto
from rf_api_client.models.users_api_models import UserDto
from rf_api_client.rf_api_client import UserAuth

from app.user_context import UserContext


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
