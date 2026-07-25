"""Registro/Factory de agentes.

Permite dar de alta agentes por nombre (decorador `@register_agent`) y construir
instancias desde configuración, sin que el supervisor conozca las clases
concretas. Es la pieza que hace el sistema "abierto a extensión".
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Type

from .base_agent import BaseAgent
from .exceptions import RegistryError


class AgentRegistry:
    """Contenedor global de tipos de agente registrados."""

    _registry: Dict[str, Type[BaseAgent]] = {}

    @classmethod
    def register(cls, name: str, agent_cls: Type[BaseAgent]) -> None:
        if not issubclass(agent_cls, BaseAgent):
            raise RegistryError(f"{agent_cls!r} no hereda de BaseAgent")
        if name in cls._registry and cls._registry[name] is not agent_cls:
            raise RegistryError(f"Nombre de agente duplicado: {name!r}")
        cls._registry[name] = agent_cls

    @classmethod
    def get(cls, name: str) -> Type[BaseAgent]:
        try:
            return cls._registry[name]
        except KeyError:
            raise RegistryError(
                f"Agente no registrado: {name!r}. Disponibles: {cls.available()}"
            ) from None

    @classmethod
    def create(cls, name: str, config: Optional[Dict[str, Any]] = None) -> BaseAgent:
        """Instancia un agente registrado."""
        agent_cls = cls.get(name)
        return agent_cls(name=name, config=config or {})

    @classmethod
    def available(cls) -> List[str]:
        return sorted(cls._registry)

    @classmethod
    def clear(cls) -> None:  # útil en tests
        cls._registry.clear()


def register_agent(name: str):
    """Decorador de clase para registrar un agente bajo un nombre."""

    def decorator(agent_cls: Type[BaseAgent]) -> Type[BaseAgent]:
        AgentRegistry.register(name, agent_cls)
        agent_cls.registry_name = name  # type: ignore[attr-defined]
        return agent_cls

    return decorator
