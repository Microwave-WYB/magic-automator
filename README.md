# magic-automator

Android automation that works where others don't. Contains utilities to bypass apps that block click events sent from `adb`, using USB HID and kernel sendevent instead. Also includes an LLM-driven agent that reads the UI and figures things out.

## Install

We recommend [uv](https://docs.astral.sh/uv/) for managing your project:

```bash
uv init my-project && cd my-project
uv add magic-automator --git https://github.com/Microwave-WYB/magic-automator
```

Or with pip:

```bash
pip install git+https://github.com/Microwave-WYB/magic-automator
```

## Tap methods

Three ways to tap, depending on your setup:

```python
import uiautomator2 as u2
from magic_automator import android
device = u2.connect("your_serial")

# Kernel sendevent - works on rooted devices and emulators
android.sendevent_tap(device, 540, 1994)

# Tap a UI element at a random point within its bounds
x, y = android.random_point(device(resourceId="com.app:id/button"))
android.sendevent_tap(device, x, y)

# Persistent HID connection (avoids re-registering on every tap)
with android.Hid(device) as hid:
    hid.tap(540, 1994)
    hid.tap(200, 800)

    # Low-level control
    hid.down(540, 960)
    hid.move_to(540, 400)
    hid.up(540, 400)

# One-shot HID (register, tap, unregister)
android.hid_tap(device, 540, 1994)
```

## Human-like interaction

Randomized taps and natural typing to reduce fingerprinting:

```python
from magic_automator.android import random_point, natural_type

el = device(resourceId="com.app:id/button")

# Pick a random point within element bounds (Gaussian, biased toward center)
x, y = random_point(el)
hid.tap(x, y)

# Type text character-by-character with random delays
natural_type(device.send_keys, el, "hello world")
```

## LLM

### Find elements

```python
from magic_automator.android.llm import get_element

el = get_element(device, client, "gpt-4o", "the submit button")
```

### Plan B

Give an LLM a goal and it figures out how to achieve it by reading the UI hierarchy XML. We recommend chaining multiple small `plan_b` calls with focused goals rather than one large call that does everything - smaller steps are more predictable and easier to debug:

```python
import openai
import uiautomator2 as u2
from magic_automator.android.llm import plan_b

device = u2.connect("your_serial")
client = openai.OpenAI()
model = "gpt-4o"

# Step 1: open FooChat and start the login flow
plan_b.rub_the_magic_lamp(
    "Open FooChat and enter phone number +1234567890, "
    "then tap Next and stop at the verification code screen",
    device, client, model,
)

# Wait for the SMS to arrive
time.sleep(10)

# Step 2: read the verification code from SMS
code = plan_b.consult_the_ancient_oracle(
    "Open the Messages app, find the latest SMS from FooChat, "
    "and return only the 6-digit verification code",
    device, client, model,
    max_turns=10, history_size=5,
)

# Step 3: enter the code and finish login
plan_b.call_a_guy(
    f"Go back to FooChat and enter verification code {code}",
    device, client, model,
    max_turns=5, history_size=5,
)
```

All function names in `plan_b` are aliases for the exact same function. There is no difference between `pray_for_a_miracle` and `hire_an_intern`. Pick whichever matches your level of desperation.

> [!WARNING]
> Every call to `plan_b` sends your UI hierarchy to an LLM, potentially many times. As the name suggests, this is plan B - it will `sacrifice_tokens_to_the_beast` and `offer_blood_and_tokens` in pursuit of your goal. It may `open_pandoras_box`, `sell_your_soul`, or `make_a_deal_with_the_devil`. Side effects are real and irreversible - if you ask it to send a message, it *will* send that message.
>
> Using an LLM to tap a button you already know the resource ID of will `burn_the_amazon_rainforest` and `melt_the_polar_ice_caps`, because it `convert_electricity_directly_into_logic`. Use the direct tap methods for simple tasks - `plan_b` is for when you genuinely don't know what's on screen.
>
> As some names suggest (`wish_upon_a_falling_star`, `pray_for_a_miracle`), this is a wish, not a guarantee. Even if you `summon_alan_turing`, he may hallucinate.

## API reference

### Tap methods

| Function | Mechanism | Requires root | Requires USB |
|---|---|---|---|
| `android.sendevent_tap(device, x, y)` | Kernel input events | Yes | No |
| `android.Hid(device)` | AOA2 USB HID (persistent) | No | Yes |
| `android.hid_tap(device, x, y)` | AOA2 USB HID (one-shot register/tap/unregister) | No | Yes |

### Human-like interaction

| Function | Description |
|---|---|
| `random_point(element)` | Pick random (x, y) within element bounds |
| `natural_type(send_keys_fn, element, text)` | Type character-by-character with delays |

### LLM

| Function | Description |
|---|---|
| `plan_b.run_agent(goal, device, client, model)` | Full LLM-driven automation agent |
| `get_element(device, client, model, description)` | Find UI element by natural language |
