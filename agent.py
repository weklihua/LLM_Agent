import json
import os, time
from dotenv import load_dotenv
from openai import OpenAI
from googleapiclient.discovery import build
from py_expression.core import Exp
import streamlit as st
import requests

load_dotenv()
client = OpenAI()
GOOGLE_CSE_ID = os.environ["GOOGLE_CSE_ID"]
GOOGLE_API_KEY = os.environ["GOOGLE_API_KEY"]
VISUALCROSSING_API_KEY = os.environ["VISUALCROSSING_API_KEY"]
    
# Google search engine
def search(search_term):
    search_result = ""
    service = build("customsearch", "v1", developerKey=os.environ.get("GOOGLE_API_KEY"))
    res = service.cse().list(q=search_term, cx=os.environ.get("GOOGLE_CSE_ID"), num = 10).execute()
    for result in res['items']:
        search_result = search_result + result['snippet']
    return search_result

#Calculator
def calculator(expr):
    exp = Exp()
    operand = exp.parse(expr)
    return operand.eval({})

# Current weather
def weather_current(location, unit="metric"):
    api_key = os.environ.get("VISUALCROSSING_API_KEY")
    url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{location}/today?unitGroup={unit}&key={api_key}&include=current"
    try:
        resp = requests.get(url)
        data = resp.json()
        current = data.get("currentConditions", {})
        return (f"Current weather in {location}: {current.get('conditions','N/A')}, "f"Temp: {current.get('temp','N/A')}°{ 'C' if unit=='metric' else 'F' }, "f"Humidity: {current.get('humidity','N/A')}%")
    except Exception as e:
        return f"Error fetching current weather: {e}"
    
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Use Google Custom Search to get snippets about current events and facts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_term": {
                        "type": "string",
                        "description": "A concise, well-formed web search query."
                    }
                },
                "required": ["search_term"]
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate a math expression and return the numeric result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expr": {
                        "type": "string",
                        "description": "A math expression, e.g. '(2+3)*4'."
                    }
                },
                "required": ["expr"]
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "weather_current",
            "description": "Get the current weather for a given location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City, ZIP, or lat,long, e.g., 'San Diego, CA'"}
                },
                "required": ["location"]
            },
        },
    },
]

System_prompt = """
Answer the following questions and obey the following commands as best you can.

You have access to the following tools:

Search: Search: useful for when you need to answer questions about current events. You should ask targeted questions.
Calculator: Useful for when you need to answer questions about math. Use python code, eg: 2 + 2
Response To Human: When you need to respond to the human you are talking to.
Current weather: useful when you need to answer questions about current weather of a certain location.

You will receive a message from the human, then you should start a loop and do one of two things

Option 1: You use a tool to answer the question.
For this, you should use the following format:
Thought: you should always think about what to do
Action: the action to take, should be one of [Search, Calculator]
Action Input: "the input to the action, to be sent to the tool"

After this, the human will respond with an observation, and you will continue.

Option 2: You respond to the human.
For this, you should use the following format:
Action: Response To Human
Action Input: "your response to the human, summarizing what you did and what you learned"

Begin!
"""
# --- Streamlit ---
st.set_page_config(page_title="Tool Agent", page_icon="🧰")
st.title("🧰 Tool Agent")

delay = st.sidebar.number_input("Delay between steps (sec)", 0.0, 60.0, 2.0, 0.5)
st.sidebar.write(f"GOOGLE_CSE_ID: {'✅' if GOOGLE_CSE_ID else '❌'}")
st.sidebar.write(f"GOOGLE_API_KEY: {'✅' if GOOGLE_API_KEY else '❌'}")

log_area = st.empty()  # where we stream log text
final_area = st.empty()

def Stream_agent(prompt):
    messages = [
        { "role": "system", "content": System_prompt },
        { "role": "user", "content": prompt },
    ]

    logs = []
    while True:
        # ask the model WITH tools enabled
        response = client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            tools=TOOLS,                # <- enable function calling
            tool_choice="auto",         # <- let model decide
            temperature=0,
            top_p=1,
        )

        msg = response.choices[0].message
        content = msg.content or ""
        tool_calls = getattr(msg, "tool_calls", None)

        # log the assistant message (truncated)
        logs.append(f"--- MODEL ---\n{content[:1000] + ('…' if len(content) > 1000 else '')}" + (f"\n(tool_calls: {', '.join(tc.function.name for tc in tool_calls)})" if tool_calls else ""))
        log_area.code("\n\n".join(logs))

        if tool_calls:
            # append the assistant message that requested tools
            messages.append({"role": "assistant", "content": content, "tool_calls": [tc.model_dump() for tc in tool_calls]})
            # execute each tool and return results
            for tc in tool_calls:
                fn = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    args = {}

                if fn == "search":
                    out = search(args.get("search_term", ""))
                elif fn == "calculator":
                    out = calculator(args.get("expr", ""))
                elif fn == "weather_current":
                    out = weather_current(args.get("location",""))
                else:
                    out = f"(Unknown tool: {fn})"

                logs.append(f"--- TOOL {fn} OUTPUT ---\n{str(out)[:1000] + ('…' if len(str(out)) > 1000 else '')}")
                log_area.code("\n\n".join(logs))

                # feed tool result back
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": fn,
                    "content": str(out),
                })

            time.sleep(delay)
            continue  # let the model observe tool outputs and respond

        # no tool calls => final answer
        final_area.success(f"Response: {content}")
        break

with st.form("chat_form", clear_on_submit=True):
    user_q = st.text_input("Your prompt", key="user_q")
    submitted = st.form_submit_button("Run")

if submitted and user_q.strip():
    Stream_agent(user_q)  
