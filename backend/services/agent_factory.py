"""Vanna agent factory — wires LLM, SQL runner, memory, and tools.

Builds a fully configured Vanna Agent with Groq LLM, secure SQLite,
ChromaDB memory, and all registered tools (SQL, visualisation, memory).
"""

import os

from vanna import Agent
from vanna.core.agent.config import AgentConfig, UiFeature, UiFeatures
from vanna.core.registry import ToolRegistry
from vanna.core.user import RequestContext, User, UserResolver
from vanna.integrations.chromadb import ChromaAgentMemory
from vanna.tools import RunSqlTool, VisualizeDataTool
from vanna.tools.agent_memory import (
    SaveQuestionToolArgsTool,
    SearchSavedCorrectToolUsesTool,
)

from backend.config.settings import settings
from backend.services.llm_service import GroqLlmService
from backend.services.sql_runner import SecureSqliteRunner


class SimpleUserResolver(UserResolver):
    """Resolve the current user from the ``vanna_email`` cookie.

    Falls back to ``guest@example.com`` when no cookie is present.
    Users with the admin email are placed in the ``admin`` group.
    """

    async def resolve_user(self, request_context: RequestContext) -> User:
        """Return a User derived from the request's vanna_email cookie."""
        user_email = request_context.get_cookie("vanna_email") or "guest@example.com"
        group = "admin" if user_email == "admin@example.com" else "user"
        return User(id=user_email, email=user_email, group_memberships=[group])


def build_agent_config() -> AgentConfig:
    """Build agent configuration with UI feature visibility per group."""
    return AgentConfig(
        stream_responses=True,
        auto_save_conversations=False,
        include_thinking_indicators=False,
        temperature=0.0,
        ui_features=UiFeatures(
            feature_group_access={
                UiFeature.UI_FEATURE_SHOW_TOOL_NAMES.value: ["admin", "user"],
                UiFeature.UI_FEATURE_SHOW_TOOL_ARGUMENTS.value: ["admin"],
                UiFeature.UI_FEATURE_SHOW_TOOL_ERROR.value: ["admin"],
                UiFeature.UI_FEATURE_SHOW_TOOL_INVOCATION_MESSAGE_IN_CHAT.value: [
                    "admin",
                    "user",
                ],
                UiFeature.UI_FEATURE_SHOW_MEMORY_DETAILED_RESULTS.value: ["admin"],
            }
        ),
    )


def create_agent() -> Agent:
    """Create and return a fully wired Vanna Agent instance."""
    database_path = settings.DATABASE_URL or os.getenv("DATABASE_URL", "clinic.db")

    tools = ToolRegistry()
    # Core data tools — pool_size and cache_size from settings for tunability
    tools.register_local_tool(
        RunSqlTool(
            sql_runner=SecureSqliteRunner(
                database_path=database_path,
                cache_size=settings.QUERY_CACHE_SIZE,
                pool_size=settings.DB_POOL_SIZE,
            )
        ),
        access_groups=["admin", "user"],
    )
    tools.register_local_tool(
        VisualizeDataTool(), access_groups=["admin", "user"]
    )
    # Memory / learning tools — let the agent save and recall successful Q→SQL patterns
    tools.register_local_tool(
        SaveQuestionToolArgsTool(), access_groups=["admin", "user"]
    )
    tools.register_local_tool(
        SearchSavedCorrectToolUsesTool(), access_groups=["admin", "user"]
    )

    return Agent(
        llm_service=GroqLlmService(),
        tool_registry=tools,
        user_resolver=SimpleUserResolver(),
        agent_memory=ChromaAgentMemory(persist_directory="./vanna_memory"),
        config=build_agent_config(),
    )


agent = create_agent()
