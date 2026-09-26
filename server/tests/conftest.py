"""Tests run as a fresh, keyless install: real provider keys from server/.env must not leak in
(environment variables win over the .env file in pydantic-settings)."""
import os

for _name in (
    "DEXTER_DEEPSEEK_API_KEY", "DEXTER_ANTHROPIC_API_KEY", "DEXTER_OPENAI_API_KEY", "DEXTER_GROQ_API_KEY",
    "DEXTER_PROMETHEUS_MCP_URL", "DEXTER_PROMETHEUS_MCP_TOKEN",
):
    os.environ[_name] = ""
