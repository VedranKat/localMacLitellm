# Local LiteLLM gateway summary

We set up a local gateway so agents and tools can call OpenRouter or other providers using limited, revocable virtual keys. Real provider credentials stay out of agent prompts and client configuration. The coding agent's own backend remains unchanged.

LiteLLM and its dedicated PostgreSQL database run natively under a locked macOS account. Protected files separate secrets from ordinary users; a dedicated port avoids development database clashes.

One **LiteLLM Gateway** background item manages both. Normal commands start/stop the service; the dashboard manages models, keys and spending limits. Keys are handed to agents explicitly.

Logs rotate at startup and hourly; detailed usage records have 30-day retention. One manual, verified backup replaces the previous snapshot. Host and dashboard administrators retain privileged access.
