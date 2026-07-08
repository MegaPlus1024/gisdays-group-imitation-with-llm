"""Initial agent package for the local LLM runtime prototype.

The package intentionally avoids eager imports so offline helpers can import
submodules such as planner packet utilities without requiring optional runtime
dependencies like `httpx`.
"""
