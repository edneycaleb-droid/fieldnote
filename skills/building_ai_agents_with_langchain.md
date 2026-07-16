# Building AI Agents with LangChain

## Description
LangChain is a framework for composing LLM-powered applications from modular, interchangeable components. It provides a unified interface for models, vector stores, tools, and retrievers so you can swap providers without rewriting business logic. This skill covers current LangChain patterns: LCEL pipe composition, RAG pipelines, tool-calling agents via LangGraph, and LangSmith observability — all using the free Groq provider as the default model.

## Steps

1. **Install packages** — LangChain splits functionality across focused integration packages:
   ```bash
   uv add langchain langchain-groq langchain-openai langchain-community langgraph langsmith
   # or with pip:
   pip install langchain langchain-groq langchain-openai langchain-community langgraph langsmith
   ```
2. **Initialise a chat model** using the provider-agnostic helper:
   ```python
   from langchain.chat_models import init_chat_model
   model = init_chat_model("llama-3.3-70b-versatile", model_provider="groq")
   # or explicitly, with the integration package:
   from langchain_groq import ChatGroq
   model = ChatGroq(model="llama-3.3-70b-versatile")
   ```
3. **Build chains with LCEL** (LangChain Expression Language — pipe syntax):
   ```python
   from langchain_core.prompts import ChatPromptTemplate
   from langchain_core.output_parsers import StrOutputParser
   prompt = ChatPromptTemplate.from_template("Summarise in one sentence: {text}")
   chain  = prompt | model | StrOutputParser()
   result = chain.invoke({"text": "LangChain provides modular LLM composition..."})
   # Stream output token-by-token:
   for chunk in chain.stream({"text": "LangChain is..."}):
       print(chunk, end="", flush=True)
   ```
4. **Build a RAG pipeline** (retrieval-augmented generation):
   ```python
   from langchain_community.document_loaders import WebBaseLoader
   from langchain_community.vectorstores import Chroma
   from langchain_openai import OpenAIEmbeddings
   from langchain_text_splitters import RecursiveCharacterTextSplitter
   docs      = WebBaseLoader("https://example.com/docs").load()
   chunks    = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200).split_documents(docs)
   store     = Chroma.from_documents(chunks, OpenAIEmbeddings())
   retriever = store.as_retriever(search_kwargs={"k": 4})
   # Combine with LCEL:
   from langchain_core.runnables import RunnablePassthrough
   rag_chain = ({"context": retriever, "question": RunnablePassthrough()} | prompt | model | StrOutputParser())
   ```
5. **Define tools and build a ReAct agent** with LangGraph:
   ```python
   from langchain_core.tools import tool
   from langgraph.prebuilt import create_react_agent
   @tool
   def search(query: str) -> str:
       """Search the web for current information."""
       return f"Search results for: {query}"
   agent  = create_react_agent(model, tools=[search])
   result = agent.invoke({"messages": [("user", "What is LangGraph?")]})
   print(result["messages"][-1].content)
   ```
6. **Enable LangSmith tracing** (free tier) for debugging and evaluation:
   ```bash
   export LANGCHAIN_TRACING_V2=true
   export LANGCHAIN_API_KEY=lsv2_...   # from smith.langchain.com/settings
   ```
   All subsequent chain and agent calls are automatically traced at `smith.langchain.com` with full input/output, latency, and token-cost visibility.
7. **Use LangGraph for stateful multi-step agents** — LangGraph models agent state as a directed graph; nodes are Python functions, edges are conditions. It handles retries, branching, and human-in-the-loop checkpoints natively.

## Tools

* **LangChain** (`langchain`) — Core framework; provides `Runnable`, `Chain`, `Tool`, `Retriever`, `Memory` abstractions and LCEL composition.
* **LangChain-Groq** (`langchain-groq`) — Integration package for Groq's free-tier LLMs (llama-3.3-70b-versatile, gemma2-9b-it, mixtral-8x7b).
* **LangChain-OpenAI** (`langchain-openai`) — Integration package for OpenAI models and text-embedding-3 embeddings.
* **LangGraph** (`langgraph`) — Graph-based stateful agent orchestration; the recommended way to build production agents with LangChain.
* **LangSmith** (`langsmith`) — Observability and evaluation platform; traces every chain run, measures latency, and supports dataset-driven testing.
* **Chroma** — Free embedded vector store; easiest way to add RAG; no external service required.
* **FAISS** — Facebook's fast similarity search library; in-memory vector search, good for large static corpora.

## Concepts

* **LCEL (LangChain Expression Language)** — Pipe-based composition syntax (`prompt | model | parser`) that makes chains readable and natively supports streaming and async.
* **Runnable** — The base interface every LCEL component implements; supports `invoke`, `stream`, `batch`, `astream`, and `astream_events`.
* **RAG (Retrieval-Augmented Generation)** — Injecting retrieved documents into the prompt so the model can answer questions about private or recent data without fine-tuning.
* **Tool calling** — Structured function invocation where the model selects and calls tools based on the conversation; defined with the `@tool` decorator.
* **Model interoperability** — All LangChain model wrappers share the same `invoke` interface; switching providers requires changing one import, not rewriting chains.
* **Agent orchestration** — Using LangGraph to manage multi-step, stateful agent execution with branching logic, retry handling, and persistent checkpoints.

## Related Skills
* building_ai_agents
* running_large_models_locally

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-15 | [langchain-ai/langchain](https://github.com/langchain-ai/langchain) | github_readme |
