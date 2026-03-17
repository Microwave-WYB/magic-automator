"""One-shot LLM helpers for Android UI interaction."""

from __future__ import annotations

from typing import Annotated, Literal

import openai
import uiautomator2 as u2
from pydantic import BaseModel, Discriminator, TypeAdapter


class ResourceId(BaseModel):
    kind: Literal["resource_id"] = "resource_id"
    value: str


class Text(BaseModel):
    kind: Literal["text"] = "text"
    value: str


Selector = Annotated[ResourceId | Text, Discriminator("kind")]

selector_adapter: TypeAdapter[Selector] = TypeAdapter(Selector)

GET_ELEMENT_SYSTEM = """\
You are given an Android UI hierarchy XML and a description of an element. \
Return the selector that best matches the description.

Respond with exactly one JSON object:
- {"kind": "resource_id", "value": "com.app:id/button"} — if the element has a resource ID
- {"kind": "text", "value": "Submit"} — if the element is best identified by its text

Output ONLY valid JSON, no markdown, no explanation.\
"""


def get_element(
    device: u2.Device,
    client: openai.OpenAI,
    model: str,
    description: str,
) -> u2.UiObject:
    """Ask an LLM to find a UI element matching a natural-language description."""
    xml = device.dump_hierarchy()
    response = client.chat.completions.create(
        model=model,
        max_tokens=256,
        messages=[
            {"role": "system", "content": GET_ELEMENT_SYSTEM},
            {"role": "user", "content": f"Find: {description}\n\n{xml}"},
        ],
    )
    raw = response.choices[0].message.content or ""
    selector = selector_adapter.validate_json(raw)
    match selector:
        case ResourceId(value=rid):
            return device(resourceId=rid)
        case Text(value=text):
            return device(text=text)
