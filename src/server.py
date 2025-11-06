import asyncio
from typing import Any, Dict, Optional
import json
import re
from pathlib import Path
from pydantic import BaseModel
import mcp.types as types
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

server = FastMCP(name="test_video",instructions="mcp server for user CRUD operations")

DATA_PATH = f"{Path(__file__).resolve().parent.parent}/data/users.json"

################################ SCHEMAS ################################
class UserSchema(BaseModel):
    name: str
    email: str
    address: Optional[str] = None
    phone: Optional[str] = None

################################ TOOL, RESOURCES, PROMPTS ################################

@server.resource(
    uri="users://all",
    name="Users",
    mime_type="application/json",
    description="Get all users data from the database"
)
async def get_all_users_resource() -> Dict[str, Any]:
    """Get all users data from the database"""
    try:
        if not Path(DATA_PATH).exists():
            return {"content": [{"type": "text", "text": "No users found"}]}

        with open(DATA_PATH, 'r') as f:
            users = json.load(f)

        return {"content": [{"text": users}]}
    except Exception:
        return {"content": [{"type": "text", "text": "Failed to retrieve users"}]}


@server.resource(
    uri="users://{userId}/profile",
    name="User Details",
    mime_type="application/json",
    description="Get a user's details from the database"
)
async def get_user_details_resource(userId: int) -> Dict[str, Any]:
    """Get a user's details from the database"""
    try:
        if not Path(DATA_PATH).exists():
            return {"content": [{"type": "text", "text": "User not found"}]}

        with open(DATA_PATH, 'r') as f:
            users = json.load(f)

        user = next((user for user in users if user['id'] == userId), None)
        if user is None:
            return {"content": [{"type": "text", "text": "User not found"}]}

        return {"content": [{"text": user}]}
    except Exception:
        return {"content": [{"type": "text", "text": "Failed to retrieve user details"}]}


@server.tool(annotations={
    "title": "Create User",
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": True,
})
async def create_user_tool(user: UserSchema) -> Dict[str, Any]:
    """Create a new user in the database and return the if succesful entry or not"""
    try:
        params = user.dict()  # Convert Pydantic model to dictionary
        id = await createUser(params)
        return {"content": [{"type": "text", "text": f"User {id} created successfully"}]}
    except Exception:
        return {"content": [{"type": "text", "text": "Failed to save user"}]}


@server.tool(annotations={
    "title": "Create Random User",
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": True,
})
async def create_random_user_tool(ctx: Context[ServerSession, None]) -> Dict[str, Any]:
    """Create a random user with fake data"""
    result = await ctx.session.create_message(
        messages=[
            types.SamplingMessage(
                role="user",
                content=types.TextContent(
                    type="text",
                    text=(
                        "Generate fake user data. The user should have a realistic name, email, address, "
                        "and phone number. Return this data as a JSON object with no other text or formatter "
                        "so it can be used with JSON.parse."
                    ),
                ),
            )
        ],
        max_tokens=1024,
    )

    # Normalize content extraction (SDKs can return different shapes)
    content = getattr(result, "content", None)
    if isinstance(content, list) and content:
        content = content[0]

    if content is None and isinstance(result, dict):
        cont = result.get("content")
        if isinstance(cont, list) and cont:
            content = cont[0]
        else:
            content = cont

    # Extract text blob
    text_blob = None
    if isinstance(content, dict):
        text_blob = content.get("text")
    else:
        text_blob = getattr(content, "text", None)

    if not text_blob or not isinstance(text_blob, str):
        return {"content": [{"type": "text", "text": "Failed to generate user data"}]}

    raw = text_blob.strip()
    # Remove possible fenced codeblocks
    raw = raw.removeprefix("```json").removeprefix("```js").removeprefix("```").removesuffix("```").strip()

    # Find first JSON object in the text
    m = re.search(r"\{[\s\S]*\}", raw)
    json_text = m.group(0) if m else raw

    try:
        fake_user = json.loads(json_text)
    except Exception:
        return {"content": [{"type": "text", "text": "Failed to generate user data"}]}

    params = {
        "name": fake_user.get("name"),
        "email": fake_user.get("email"),
        "address": fake_user.get("address", ""),
        "phone": fake_user.get("phone", "")
    }
    #fake_user_pydantic = UserSchema(**params).dict()

    if not params["name"] or not params["email"]:
        return {"content": [{"type": "text", "text": "Generated user data missing required fields"}]}

    # createUser accepts a dict-like params
    id = await createUser(params)
    return {"content": [{"type": "text", "text": f"User {id} created successfully"}]}


@server.prompt(
    name="generate-fake-user",
    description="Generate a fake user based on a given name"
)
async def create_user_prompt(name: str) -> types.GetPromptResult:
    """Generate a fake user based on a given name"""
    return types.GetPromptResult(
        description="Generate a fake user based on a given name",
        messages=[
            types.PromptMessage(
                role="user",
                content=types.TextContent(type="text", text=f"Generate a fake user with the name {name}. The user should have a realistic email, address, and phone number."),
            )
        ],
    )


################################ UTILS ################################
async def createUser(params: Dict[str, Any]) -> int:
    """Create a new user in the database and return the if succesful entry or not"""
    try:
        if not Path(DATA_PATH).exists():
            with open(DATA_PATH, 'w') as f:
                json.dump([], f)

        with open(DATA_PATH, 'r') as f:
            users = json.load(f)

        new_id = max([user['id'] for user in users], default=0) + 1
        new_user = {
            "id": new_id,
            "name": params["name"],
            "email": params["email"],
            "address": params.get("address", ""),
            "phone": params.get("phone", "")
        }
        users.append(new_user)

        with open(DATA_PATH, 'w') as f:
            json.dump(users, f, indent=4)

        return new_id
    except Exception as e:
        raise e

################################ RUN SERVER ################################

def main():
    server.run(transport='stdio')

if __name__ == "__main__":
    main()