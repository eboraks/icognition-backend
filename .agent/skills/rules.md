1. always ask the user to run npm commands in the terminal, the AI coding agent doesn't have permissions to run npm commands
2. always place import statements at the top of the file
3. When running python scripts, always use the local virtual environment .venv/bin/python
4. When possible use out of the box libraries like LangGraph as much as possible
5. Never add raw SQL string interpolation — always use SQLAlchemy parameterized 
   queries or text() with bound parameters
6. All new document processing steps must be parallelized with asyncio.gather 
   where they don't have data dependencies
7. Global service singletons (get_*_service()) are preferred over instantiating 
   services per-request to avoid repeated initialization overhead
8. DB prompts must be fetched once per session, not once per graph node execution.
   Cache them at request start and pass them into the graph builder.
9. When adding a new LangGraph node, always add a run_name to the config for 
   Langfuse tracing
10. New Vue components that appear in both the web app and extension must go 
    into shared/ and be imported in both places
