# Live Run Forking with Pydantic Deep Agents for Autonomous AI Development

## Description
Live run forking enables autonomous agents to explore multiple approaches to a problem in parallel, stream results, and merge the best outcome. Pydantic Deep Agents is an open-source, self-hosted terminal AI assistant and Python framework that enables developers to create autonomous AI agents with features like live run forking, tool-calling, sandboxed execution, and persistent memory.

## Steps
1. **Define the Problem or Task**: Clearly articulate the task or problem the autonomous agent needs to solve.
2. **Install Pydantic-Deep**: Install pydantic-deep using the provided installation script or pip: `pip install pydantic-deep`.
3. **Configure the Model and Provider**: Configure the model and provider using environment variables or the TUI: `export ANTHROPIC_API_KEY=sk-ant-...` or `/model` in the TUI.
4. **Configure Live Run Forking**: Set up the agent to fork its run into multiple parallel branches, specifying the number of branches and the merge strategy.
5. **Execute the Task**: Run the task, allowing the agent to explore different approaches in parallel.
6. **Stream and Evaluate Results**: Monitor the outcomes from each branch, assessing their quality or success.
7. **Use the TUI**: Use the TUI to interact with the AI assistant, including live run forking and merging: `pydantic-deep`.
8. **Create Custom Agents**: Utilize the Python framework to create custom autonomous AI agents with features like tool-calling, sandboxed execution, and persistent memory: `from pydantic_deep import create_deep_agent`.
9. **Merge the Best Branch**: Adopt the most successful branch's outcome, integrating it into the parent run.
10. **Monitor Outcomes**: Continuously monitor the outcomes from each branch, assessing their quality or success.

## Tools
* **Pydantic Deep Agents**: A Python framework for building autonomous agents with live run forking capabilities.
* **Docker**: For sandboxed execution and workflow management.
* **Playwright**: For browser automation and web interaction.
* **pydantic**: A Python library for building robust, scalable data models.
* **pydantic-ai**: A Python library for building AI models.
* **LiteParse**: A document parsing library for PDFs, DOCX, XLSX, PPTX, and more.

## Concepts
* **Autonomous AI Agents**: Systems capable of independent decision-making and action.
* **Live Run Forking**: The ability to split a run into parallel branches for exploration and merging.
* **Parallel Execution**: Running multiple tasks simultaneously to improve efficiency.
* **Merge Strategies**: Methods for combining the results of parallel branches.
* **Tool-calling**: The ability of an autonomous agent to call external tools and services.
* **Sandboxed Execution**: The execution of tasks in a secure, isolated environment.
* **Persistent Memory**: The ability of an autonomous agent to retain memory and learn from experience.

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-24 | [vstorm-co/pydantic-deepagents](https://github.com/vstorm-co/pydantic-deepagents) | github_readme |
