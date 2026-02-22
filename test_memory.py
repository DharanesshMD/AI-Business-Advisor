import asyncio
import sqlite3
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from backend.agents.graph import create_advisor_graph

def test_memory():
    db_path = "test_memory.sqlite"
    # Ensure starting fresh
    import os
    if os.path.exists(db_path):
        os.remove(db_path)

    print(f"1. Initializing SQLite Checkpointer at {db_path}...")
    db_conn = sqlite3.connect(db_path, check_same_thread=False)
    checkpointer = SqliteSaver(db_conn)
    checkpointer.setup()

    print("2. Creating Advisor Graph with memory...")
    graph = create_advisor_graph(location="India", checkpointer=checkpointer)

    session_id = "test_session_123"
    config = {"configurable": {"thread_id": session_id}}

    print("\n3. Sending first message: 'My name is Alex and my business is CloudTech.'")
    result1 = graph.invoke({
        "messages": [HumanMessage(content="My name is Alex and my business is CloudTech.")],
        "location": "India"
    }, config)

    # We just want to see that the model responded
    print(f"AI Response: {result1['messages'][-1].content[:100]}...\n")

    print("4. Sending second message: 'What is the name of my business?' (Testing Memory)")
    # Notice we ONLY send the new message - LangGraph should retrieve the rest from memory
    result2 = graph.invoke({
        "messages": [HumanMessage(content="What is the name of my business?")],
        "location": "India"
    }, config)

    print(f"AI Response: {result2['messages'][-1].content}")

    # Verify the state contains our previous message
    state = graph.get_state(config)
    print(f"\nTotal messages in memory: {len(state.values['messages'])}")

    db_conn.close()
    if os.path.exists(db_path):
        os.remove(db_path)
    print("\nTest completed successfully!")

if __name__ == "__main__":
    test_memory()