from dotenv import load_dotenv
import os
import asyncio
import json
import re
from typing import List
from pydantic import AnyUrl
from server import UserSchema
import mcp.types as types
from mcp.shared.exceptions import McpError
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.context import RequestContext
import inquirer
from inquirer.themes import GreenPassion
from google import genai
from google.genai import types as genai_types

load_dotenv()

google = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))


async def handle_sampling_message(
    context: RequestContext[ClientSession, None],
    params: types.CreateMessageRequestParams) -> types.CreateMessageResult:
    print(f"Sampling request: {params.messages}")

    texts = list()
    for message in params.messages:
        text = await handleServerMessagePrompt(message)
        if text: texts.append(text)

    return types.CreateMessageResult(
        role="user",
        model="gemini-2.5-flash",
        stopReason="endTurn",
        content=types.TextContent(
            type="text",
            text="\n".join(texts),
        )
    )


async def main():
    async with stdio_client(
        StdioServerParameters(command="uv", args=["run", "src/server.py"])
    ) as (read, write):
        async with ClientSession(read, write, sampling_callback=handle_sampling_message) as session:
            await session.initialize()

            # List available tools
            tools_session = await session.list_tools()
            #print("tools", tools_session.tools)

            # List available prompts
            prompts_session = await session.list_prompts()
            #print("prompts", prompts)

            # List available resources
            resources_session = await session.list_resources()
            #print("resources", resources)

            # List available resource templates
            resource_templates_session = await session.list_resource_templates()
            #print("resource_templates", resource_templates)

            print("You are connected")
            while True:
                options = [
                    inquirer.List(
                        'option',
                        message="What would you like to do",
                        choices=["Query", "Tools", "Resources", "Prompts", "Quit"]
                    )
                ]
                option = inquirer.prompt(options, theme=GreenPassion())['option']
                if option == None:
                    break
                match option:

                    case "Tools":
                        tools_choices = list(
                            map(lambda t: {
                                "name": getattr(getattr(t, 'annotations', None), 'title', None) or t.name,
                                "value": t.name,
                                "description": t.description
                            }, tools_session.tools)
                        )
                        toolName = [
                            inquirer.List(
                                'toolName',
                                message="Select a tool",
                                choices=[choice["name"] for choice in tools_choices]
                            )
                        ]
                        toolNameOption = inquirer.prompt(toolName, theme=GreenPassion())['toolName']
                        tool = [t for t in tools_session.tools if (getattr(getattr(t, 'annotations', None), 'title', None) or t.name) == toolNameOption][0]
                        if not tool:
                            print("Tool not found")
                        else:
                            print(f"You selected tool: {tool.name}")
                            await handleTool(session, tool)

                    case "Resources":
                        print("Available resources:")
                        resources_choices = list(
                            map(lambda r: {
                                "name": r.name,
                                "value": r.uri,
                                "description": r.description
                            }, resources_session.resources)
                        )
                        resource_templates_choices = list(
                            map(lambda r: {
                                "name": r.name,
                                "value": r.uriTemplate,
                                "description": r.description
                                }, resource_templates_session.resourceTemplates)
                        )
                        
                        resources_all = resources_choices + resource_templates_choices
                        resourceUri = [
                            inquirer.List(
                                'resourceUri',
                                message="Select a resource",
                                choices=[choice["value"] for choice in resources_all]
                            )
                        ]
                        resourceUriOption = inquirer.prompt(resourceUri, theme=GreenPassion())['resourceUri']
                        uri = [r for r in resources_session.resources if r.uri == resourceUriOption]
                        if not uri:
                            uri = [r for r in resource_templates_session.resourceTemplates if r.uriTemplate == resourceUriOption]
                        if not uri:
                            print("Resource not found")
                        else:
                            print(f"You selected resource: {uri[0].name}")
                            uri = uri[0].uri if hasattr(uri[0],"uri") else uri[0].uriTemplate
                            await handleResource(session, uri)

                    case "Prompts":
                        print("Available prompts:")
                        prompts_choices = list(
                            map(lambda p: {
                                "name": p.name,
                                "value": p.name,
                                "description": p.description
                            }, prompts_session.prompts)
                        )
                        promptName = [
                            inquirer.List(
                                'promptName',
                                message="Select a prompt",
                                choices=[choice["name"] for choice in prompts_choices]
                            )
                        ]
                        promptNameOption = inquirer.prompt(promptName, theme=GreenPassion())['promptName']
                        prompt = [p for p in prompts_session.prompts if p.name == promptNameOption][0]
                        print("prompt", prompt)
                        if not prompt:
                            print("Prompt not found")
                        else:
                            print(f"You selected prompt: {prompt.name}")
                            params = {}
                            for p in prompt.arguments:
                                param_name = p.name
                                param_question = inquirer.Text(
                                    param_name,
                                    message=f"Enter value for {param_name}:"
                                )
                                answer = inquirer.prompt([param_question], theme=GreenPassion())
                                params[param_name] = answer[param_name]

                            result = await session.get_prompt(
                                prompt.name,
                                arguments=params
                            )
                            #print(f"Prompt result: {result.messages[0].content}")
                            for message in result.messages:
                                print(await handleServerMessagePrompt(message))
                            
                    case "Query":
                        print("You selected Query")
                        await handleQuery(session, tools_session.tools)

                    case "Quit":
                        print("Exiting...")
                        return
                    

async def handleQuery(session: ClientSession, toolsSession: List[types.Tool]) -> None:
    query = inquirer.Text(
        'query',
        message="Enter your query"
    )
    queryPrompt = inquirer.prompt([query], theme=GreenPassion())['query']
    
    tools, tool_type = [], None
    for tool in toolsSession:
        if '$defs' in tool.inputSchema: #if inputs has a pydantic schema
            mySchema = list(tool.inputSchema['$defs'].keys())[0]
            myProperties = dict()
            myProperties[tool.inputSchema['required'][0]] = {
                    "type": tool.inputSchema['$defs'][mySchema].get('type', "object"),
                    "properties": tool.inputSchema['$defs'][mySchema]['properties'],
                    "required": tool.inputSchema['$defs'][mySchema].get('required', [])
                }
            print("myProperties", myProperties)
            tool_type = genai_types.Tool(
                        function_declarations=[
                            {
                                "name": tool.name,
                                "description": tool.description or "",
                                "parameters": {
                                    "type": tool.inputSchema['$defs'][mySchema].get('type', "object"),
                                    "properties": myProperties,
                                    "required": tool.inputSchema['required']
                                }
                            }
                        ]
                    )                 
        else: #no pydantic schema
            tool_type = genai_types.Tool(
                        function_declarations=[
                            {
                                "name": tool.name,
                                "description": tool.description or "",
                                "parameters": {
                                    "type": tool.inputSchema['type'],
                                    "properties": tool.inputSchema['properties'],
                                    "required": tool.inputSchema.get('required', [])
                                }
                            }
                        ]
                    )
        tools.append(tool_type)
    print("tools", tools)

    response = google.models.generate_content(
        model='models/gemini-2.5-flash',
        contents=queryPrompt,
        config=genai_types.GenerateContentConfig(
            tools=tools,
        ),
    )
    
    if response.candidates[0].content.parts[0].function_call:
        tool_call = response.candidates[0].content.parts[0].function_call
        result = await session.call_tool(
                    tool_call.name,
                    arguments={**tool_call.args}
                )
        print(f"{tool_call.name} Tool result: {result.content[0].text}")
    else:
        print(f"No function call:{response.text}")


async def handleTool(session: ClientSession, tool: types.Tool) -> None:
    args, arguments = {}, {}
    if '$defs' in tool.inputSchema: #if inputs has a pydantic schema
        theSchema = list(tool.inputSchema['$defs'].keys())[0]
        for key, val in tool.inputSchema['$defs'][theSchema]['properties'].items():
            param_name, param_type = key, None
            if 'anyOf' in val: #optional params
                param_type = [v['type'] for v in val.get('anyOf')]
            else: #required params
                param_type = val.get('type')
            param_question = inquirer.Text(
                param_name,
                message=f"Enter value for {param_name} ({param_type}):"
            )
            answer = inquirer.prompt([param_question], theme=GreenPassion())
            args[param_name] = answer[param_name]
        arguments = {"user": UserSchema(**args).model_dump()}

    result = await session.call_tool(
        tool.name,
        arguments=arguments
    )
    print("Tool result:", result.content[0].text)


async def handleResource(session: ClientSession, uri: AnyUrl | str) -> None:
    finalUri = str(uri)
    if "{" in finalUri and "}" in finalUri:
        paramMatches = re.findall(r"{([^}]+)}", finalUri)
        for param in paramMatches:
            param_question = inquirer.Text(
                param,
                message=f"Enter value for {param}:"
            )
            answer = inquirer.prompt([param_question], theme=GreenPassion())
            finalUri = finalUri.replace(f"{{{param}}}", str(answer[param]))
    try:
        result = await session.read_resource(finalUri)
    except McpError as err:
        error_dict = {
            "error": {
                "code": err.error.code,
                "message": err.error.message,
                "data": err.error.data
            }
        }
        print(f"Resource error: {json.dumps(error_dict['error']['message'], indent=2, separators=(',', ': '))}")
        return
    print(json.dumps(json.loads(result.contents[0].text), indent=2, separators=(',', ': ')))


async def handleServerMessagePrompt(message: types.GetPromptResult) -> None:
    if message.content.type != "text": return
    #print(message.content.text)
    run = [
        inquirer.Confirm("run", message="Would you like to run the above prompt", default=True),
    ]
    runAnswer =inquirer.prompt(run, theme=GreenPassion())['run']
    if not runAnswer: return

    response = google.models.generate_content(
        model='models/gemini-2.5-flash',
        contents=message.content.text
    )

    return response.text


if __name__ == "__main__":
    asyncio.run(main())