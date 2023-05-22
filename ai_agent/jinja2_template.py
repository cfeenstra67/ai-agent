import dataclasses as dc
from typing import Any, Dict, Optional

import jinja2

from ai_agent.modular_agent import Template


jinja_env = jinja2.Environment(
    loader=jinja2.PackageLoader("ai_agent"),
    autoescape=jinja2.select_autoescape(),
    enable_async=True
)


@dc.dataclass(frozen=True)
class JinjaTemplate(Template):
    """
    """
    template: str
    env: Optional[jinja2.Environment] = None

    async def render(self, scope: Dict[str, Any]) -> str:
        env = self.env or jinja_env
        template = env.get_template(self.template)
        return await template.render_async(scope)


@dc.dataclass(frozen=True)
class JinjaString(Template):
    """
    """
    template: str
    env: Optional[jinja2.Environment] = None

    async def render(self, scope: Dict[str, Any]) -> str:
        env = self.env or jinja_env
        template = env.from_string(self.template)
        return await template.render_async(scope)    
