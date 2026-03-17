"""LLM agent that achieves goals on Android devices by reading UI hierarchy XML."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Annotated, Literal, cast

import openai
import uiautomator2 as u2
from pydantic import BaseModel, Discriminator, Field, TypeAdapter

from magic_automator.android.internal.aoa_hid import Hid, find_usb_device
from magic_automator.android.internal.humanize import natural_type, random_point
from magic_automator.android.internal.sendevent import find_touch_device, sendevent_tap


class ResourceId(BaseModel):
    """Select a UI element by its Android resource ID."""

    kind: Literal["resource_id"] = "resource_id"
    value: str = Field(description="e.g. com.whatsapp:id/send_btn")


class Text(BaseModel):
    """Select a UI element by its visible text."""

    kind: Literal["text"] = "text"
    value: str = Field(description="Exact visible text of the element")


Selector = Annotated[ResourceId | Text, Discriminator("kind")]


class Tap(BaseModel):
    """Tap a UI element. Only use selectors from the current XML hierarchy."""

    kind: Literal["tap"] = "tap"
    target: Selector


class TypeText(BaseModel):
    """Type text into a UI element."""

    kind: Literal["type_text"] = "type_text"
    target: Selector
    text: str


class PressKey(BaseModel):
    """Press a device key: back, home, enter, delete, recent."""

    kind: Literal["press_key"] = "press_key"
    key: Literal["back", "home", "enter", "delete", "recent"]


class Shell(BaseModel):
    """Run an ADB shell command. Prefer this for opening apps and changing settings."""

    kind: Literal["shell"] = "shell"
    command: str = Field(description='e.g. "am start -n com.whatsapp/.Main" or "settings put ..."')


class Swipe(BaseModel):
    """Swipe the screen in a direction, for scrolling."""

    kind: Literal["swipe"] = "swipe"
    direction: Literal["up", "down", "left", "right"]


class Wait(BaseModel):
    """Wait before the next action."""

    kind: Literal["wait"] = "wait"
    seconds: float = Field(default=1.0, description="Seconds to wait")


class Done(BaseModel):
    """The goal has been fully achieved."""

    kind: Literal["done"] = "done"
    result: str = Field(description="Summary of what was accomplished")


class Fail(BaseModel):
    """The goal is impossible (wrong app, missing permission, etc.)."""

    kind: Literal["fail"] = "fail"
    reason: str = Field(description="Why the goal cannot be achieved")


Action = Annotated[
    Tap | TypeText | PressKey | Shell | Swipe | Wait | Done | Fail,
    Discriminator("kind"),
]

action_adapter: TypeAdapter[Action] = TypeAdapter(Action)


@dataclass
class Turn:
    action: str
    extra: str = ""


def resolve_selector(device: u2.Device, selector: ResourceId | Text) -> u2.UiObject:
    match selector:
        case ResourceId(value=rid):
            return device(resourceId=rid)
        case Text(value=text):
            return device(text=text)


def extract_json(text: str) -> str:
    """Extract JSON from text that may contain thinking tags or explanation."""
    if "</think>" in text:
        _, text = text.split("</think>", 1)
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    if text.startswith("{"):
        return text
    last_brace = text.rfind("{")
    return text[last_brace:] if last_brace != -1 else text


def parse_action(text: str | None) -> Action:
    if not text:
        raise RuntimeError("LLM returned empty response")
    return action_adapter.validate_json(extract_json(text))


def execute(
    device: u2.Device,
    action: Tap | TypeText | PressKey | Shell | Swipe | Wait,
    tap: Callable[[int, int], None],
) -> tuple[str, str]:
    """Execute an action on the device. Returns (summary, extra_output)."""
    match action:
        case Tap(target=target):
            el = resolve_selector(device, target)
            px, py = random_point(el)
            tap(px, py)
            return f"tap {target} → ({px}, {py})", ""
        case TypeText(target=target, text=text):
            el = resolve_selector(device, target)
            natural_type(device.send_keys, el, text)
            return f"type {text!r} into {target}", ""
        case PressKey(key=key):
            device.press(key)
            return f"press {key}", ""
        case Shell(command=cmd):
            out = device.shell(cmd)
            stdout = out.output if hasattr(out, "output") else str(out)
            return f"shell {cmd!r}", stdout.strip()
        case Swipe(direction=d):
            device.swipe_ext(d)
            time.sleep(0.8)
            return f"swipe {d}", ""
        case Wait(seconds=s):
            time.sleep(s)
            return f"wait {s}s", ""


SYSTEM = """\
You are an Android device automation agent. You read the UI hierarchy XML and \
take one action at a time to achieve a goal.

# Goal
{goal}

# Response format
Respond with exactly one JSON object. Schema:

{schema}

# Rules
- Output ONLY valid JSON, no markdown, no explanation
- Use tap/type_text for all UI interaction — these use bypass-safe input methods
- Use shell only for non-UI tasks: launching apps, changing settings, checking state
- Only use selectors (resource_id, text) from the current XML hierarchy — never guess\
"""


def step(
    device: u2.Device,
    client: openai.OpenAI,
    model: str,
    system: str,
    tap: Callable[[int, int], None],
    history: list[Turn],
    turn: int,
    max_turns: int,
    history_size: int,
) -> Done | Fail | Turn:
    """Run a single agent turn. Returns Done/Fail to stop, or a Turn to continue."""
    xml = device.dump_hierarchy()

    history_text = "\n".join(
        f"- {h.action}" + (f" → {h.extra}" if h.extra else "") for h in history[-history_size:]
    )
    prompt = f"Turn {turn}/{max_turns}.\n\n"
    if history_text:
        prompt += f"Recent actions:\n{history_text}\n\n"
    prompt += f"Current UI hierarchy:\n{xml}"

    response = client.chat.completions.create(
        model=model,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    raw = response.choices[0].message.content
    try:
        action = parse_action(raw)
    except Exception as e:
        return Turn(action=f"parse error: {e}")

    match action:
        case Done() | Fail():
            return action
        case _:
            try:
                desc, extra = execute(device, action, tap)
            except Exception as e:
                desc = f"{action.kind} FAILED: {e}"
                extra = ""
            time.sleep(0.5)
            return Turn(action=desc, extra=extra)


def run_agent(
    goal: str,
    device: u2.Device,
    client: openai.OpenAI,
    model: str,
    max_turns: int = 20,
    history_size: int = 10,
) -> str:
    """
    LLM-driven agent that achieves a goal on an Android device.

    Returns the Done summary on success. Raises RuntimeError on failure or exhaustion.
    """
    schema = json.dumps(action_adapter.json_schema(), indent=2)
    system = SYSTEM.format(goal=goal, schema=schema)

    # Pick best tap method: USB HID > sendevent > uiautomator2 click
    hid = Hid(device) if find_usb_device(cast(str, device.serial)) else None
    tap = (
        hid.tap
        if hid
        else partial(sendevent_tap, device)
        if find_touch_device(device)
        else device.click
    )

    try:
        history: list[Turn] = []
        for turn in range(1, max_turns + 1):
            result = step(
                device,
                client,
                model,
                system,
                tap,
                history,
                turn,
                max_turns,
                history_size,
            )
            match result:
                case Done(result=summary):
                    return summary
                case Fail(reason=reason):
                    raise RuntimeError(f"Agent failed: {reason}")
                case Turn():
                    history.append(result)
        raise RuntimeError(f"Exhausted {max_turns} turns without completing goal")
    finally:
        if hid:
            hid.close()


gaze_into_the_abyss_and_speak_your_desire = run_agent
wish_upon_a_falling_star = run_agent
consult_the_ancient_oracle = run_agent
pray_for_a_miracle = run_agent
sacrifice_tokens_to_the_beast = run_agent
offer_blood_and_tokens = run_agent
boil_oceans = run_agent
melt_the_polar_ice_caps = run_agent
burn_the_amazon_rainforest = run_agent
convert_electricity_directly_into_logic = run_agent
contract_with_kyubey = run_agent
wish_to_shenron = run_agent
wish_to_genie = run_agent
rub_the_magic_lamp = run_agent
beg_the_robot_cat = run_agent
ask_the_magic_conch = run_agent
i_have_a_dream = run_agent
whatever_it_takes = run_agent
summon_alan_turing = run_agent
summon_linus_torvalds = run_agent
summon_stefan_savage = run_agent
summon_geoff_voelker = run_agent
summon_aaron_schulman = run_agent
summon_deepak_kumar = run_agent
place_your_bets = run_agent
pull_the_lever = run_agent
feed_the_slot_machine = run_agent
bet_the_house = run_agent
go_all_in = run_agent
let_it_ride = run_agent
commission_a_specialist = run_agent
outsource_the_problem = run_agent
delegate_downward = run_agent
file_a_support_ticket = run_agent
hire_an_intern = run_agent
open_pandoras_box = run_agent
sell_your_soul = run_agent
make_a_deal_with_the_devil = run_agent
call_a_guy = run_agent
