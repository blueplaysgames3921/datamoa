"""
Preset profiles — used when no API key is available for the Config Agent
User selects one of these on first launch as their starting configuration
"""

from core.config.settings import AgentModelConfig, PipelineConfig

PRESETS: dict[str, dict] = {
    "high_end_local": {
        "label": "High End Local",
        "description": "Powerful GPU (16GB+ VRAM). Everything runs locally. Maximum privacy.",
        "icon": "cpu",
        "agents": AgentModelConfig(
            intake="ollama/gemma3:27b",
            parsing="ollama/llama3.3:70b",
            context="ollama/gemma3:27b",
            confidence="ollama/gemma3:12b",
            reasoning="ollama/llama3.3:70b",
            validation="ollama/gemma3:12b",
            enrichment="ollama/llama3.3:70b",
            hitl="ollama/gemma3:12b",
            write="ollama/llama3.3:70b",
            audit="ollama/gemma3:27b",
            learning="ollama/gemma3:12b",
            orchestrator="ollama/gemma3:27b",
            config_agent="ollama/gemma3:27b",
        ).model_dump(),
        "pipeline": PipelineConfig(
            confidence_green_threshold=0.90,
            confidence_amber_threshold=0.65,
        ).model_dump(),
    },

    "cloud_only": {
        "label": "Cloud Only",
        "description": "No local models. All processing via cloud APIs. Best quality.",
        "icon": "cloud",
        "agents": AgentModelConfig(
            intake="google/gemini-2.0-flash",
            parsing="groq/llama-3.3-70b-versatile",
            context="google/gemini-2.0-flash",
            confidence="google/gemini-2.0-flash",
            reasoning="anthropic/claude-opus-4-6",
            validation="google/gemini-2.0-flash",
            enrichment="perplexity/sonar",
            hitl="google/gemini-2.0-flash",
            write="anthropic/claude-haiku-4-5",
            audit="deepseek/deepseek-chat",
            learning="google/gemini-2.0-flash",
            orchestrator="google/gemini-2.5-flash",
            config_agent="google/gemini-2.5-flash",
        ).model_dump(),
        "pipeline": PipelineConfig().model_dump(),
    },

    "balanced": {
        "label": "Balanced",
        "description": "Mid-range GPU (8GB VRAM). Light tasks local, heavy tasks cloud.",
        "icon": "scales",
        "agents": AgentModelConfig(
            intake="ollama/gemma3:4b",
            parsing="groq/llama-3.3-70b-versatile",
            context="ollama/gemma3:4b",
            confidence="ollama/gemma3:4b",
            reasoning="anthropic/claude-sonnet-4-6",
            validation="ollama/gemma3:4b",
            enrichment="perplexity/sonar",
            hitl="ollama/gemma3:4b",
            write="anthropic/claude-haiku-4-5",
            audit="deepseek/deepseek-chat",
            learning="ollama/gemma3:4b",
            orchestrator="google/gemini-2.5-flash",
            config_agent="google/gemini-2.5-flash",
        ).model_dump(),
        "pipeline": PipelineConfig().model_dump(),
    },

    "privacy_first": {
        "label": "Privacy First",
        "description": "Nothing leaves your machine. Slower but fully air-gapped.",
        "icon": "shield",
        "agents": AgentModelConfig(
            intake="ollama/gemma3:4b",
            parsing="ollama/gemma3:12b",
            context="ollama/gemma3:4b",
            confidence="ollama/gemma3:4b",
            reasoning="ollama/gemma3:27b",
            validation="ollama/gemma3:4b",
            enrichment="ollama/gemma3:12b",
            hitl="ollama/gemma3:4b",
            write="ollama/gemma3:12b",
            audit="ollama/gemma3:4b",
            learning="ollama/gemma3:4b",
            orchestrator="ollama/gemma3:12b",
            config_agent="ollama/gemma3:4b",
        ).model_dump(),
        "pipeline": PipelineConfig(
            confidence_green_threshold=0.80,
            confidence_amber_threshold=0.55,
        ).model_dump(),
    },

    "budget": {
        "label": "Budget",
        "description": "Minimizes API costs. Free/cheap models where possible.",
        "icon": "dollar",
        "agents": AgentModelConfig(
            intake="ollama/gemma3:4b",
            parsing="groq/llama-3.3-70b-versatile",  # Groq free tier
            context="ollama/gemma3:4b",
            confidence="ollama/gemma3:4b",
            reasoning="groq/llama-3.3-70b-versatile",
            validation="ollama/gemma3:4b",
            enrichment="ollama/gemma3:4b",
            hitl="ollama/gemma3:4b",
            write="google/gemini-2.0-flash",
            audit="ollama/gemma3:4b",
            learning="ollama/gemma3:4b",
            orchestrator="google/gemini-2.0-flash",
            config_agent="google/gemini-2.0-flash",
        ).model_dump(),
        "pipeline": PipelineConfig(
            confidence_green_threshold=0.80,
            max_concurrent_records=3,
        ).model_dump(),
    },
}
