"""Ollama client for summary and homework generation."""
from .ollama_client import OllamaClient, check_ollama_available

__all__ = ["OllamaClient", "check_ollama_available"]
