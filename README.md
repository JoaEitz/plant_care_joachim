[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![GitHub stars](https://img.shields.io/github/stars/AK-O/plant_care?style=social)](https://github.com/AK-O/plant_care/stargazers)

# Plant Care Integration (Home Assistant)

A Home Assistant custom integration that helps you **track and automate plant care** by exposing **watering and fertilizing schedules** and optional **environment health monitoring** as Home Assistant entities — **one device per plant**.

The integration does not send notifications itself. Instead, it provides clear, actionable **states and sensors** that you can use in automations, dashboards, and scripts.

* ✅ One config entry = one plant (one HA device)
* ✅ Interval-based watering & fertilizing with due / overdue tracking
* ✅ Optional temperature, humidity, and soil moisture monitoring
* ✅ Fully entity-driven and automation-friendly (HA-native)
* ❌ No built-in notifications — use the automation examples below.

---


## Table of Contents

* [Features](https://chatgpt.com/c/69582127-1f64-8326-97df-99677fc2b078#features)
* [Installation](https://chatgpt.com/c/69582127-1f64-8326-97df-99677fc2b078#installation)
* [Configuration](https://chatgpt.com/c/69582127-1f64-8326-97df-99677fc2b078#configuration)
* [Entities](https://chatgpt.com/c/69582127-1f64-8326-97df-99677fc2b078#entities)
* [How It Works](https://chatgpt.com/c/69582127-1f64-8326-97df-99677fc2b078#how-it-works)
* [Automations (YAML Examples)](https://chatgpt.com/c/69582127-1f64-8326-97df-99677fc2b078#automations-yaml-examples)
* [Update Behavior](https://chatgpt.com/c/69582127-1f64-8326-97df-99677fc2b078#update-behavior)
* [FAQ](https://chatgpt.com/c/69582127-1f64-8326-97df-99677fc2b078#faq)

---

## Features

### Task Tracking

Per plant:

* Watering schedule (interval-based)
* Fertilizing schedule (interval-based)
* “Mark done” buttons
* Due / overdue status (binary sensors + attributes)

### Environment Monitoring (Optional)

Per plant (if you assign external sensors):

* Temperature / humidity / soil moisture monitoring
* Out-of-range binary sensors (`device_class: problem`)
* Deviation sensors (how far outside the target range)

### AI Plant Health Analysis (Optional)

Per plant, Plant Care can analyze a current JPEG, PNG, or WebP image together with:

* plant name, optional species, and assigned Home Assistant area
* current temperature, humidity, soil moisture, illuminance, and conductivity values
* compact recorder history with min/max/average, change, trend, sample count, and daily averages
* watering and fertilizing history and due state
* a compact summary of recent AI analyses

Analysis runs only when you press the plant's **Analyze Plant Health** button or call
`plant_care.analyze_plant`. It is never polled or scheduled automatically.

---

## Installation

> This integration is intended to be installed like any other custom Home Assistant integration.

### Option A: HACS (recommended)

<small>*HACS is a third party community store and is not included in Home Assistant out of the box.*</small>

1. Add this repository to HACS as a **custom repository** (type: Integration)
2. Install **Plant Care Integration**
3. Restart Home Assistant


### Option B: Manual

1. Copy the integration folder into:
   `config/custom_components/plant_care/`
2. Restart Home Assistant

---

## Configuration

### Add a Plant

1. Go to **Settings → Devices & services**
2. Click **Add Integration**
3. Search for **Plant Care Integration**
4. Enter a **Plant Name** (e.g. `Monstera Deliciosa`)

This creates:

* **One device per plant**
* A stable `<plant_id>` derived from the name using slugify (e.g. `monstera_deliciosa`)

Renaming the plant later changes friendly names, but  **entity IDs remain stable** .

### Configure Options

All configuration is done via entities and options:

* Intervals and targets are exposed as **Number entities**
* Optional external sensors can be assigned in the plant device **options**

### Configure AI Health Analysis

Open the plant's integration entry under **Settings → Devices & services → Plant Care → Configure**.
Each plant entry has its own AI settings:

1. Enable **AI health analysis**.
2. Select `openai` and enter an OpenAI API key.
3. Keep the default `gpt-4o-mini` model or enter another OpenAI model that accepts image input and structured output.
4. Choose a default `camera` or `image` entity, or enter a local media ID such as
   `media-source://media_source/local/plants/peace-lily.jpg`.
5. Optionally change the 14-day history window and the number of previous analyses (default 3).

If a plant was created through `plant_care.create_plant` with `image_media_content_id`, that local
media image is saved as its default analysis source. Existing copied plant images in
`/config/www/plants/` are also detected as a backward-compatible fallback.

The OpenAI API key is stored in the plant's Home Assistant config-entry options. It is never logged.
The request uses OpenAI's Responses API with response storage disabled.

---

## Entities

Each plant device exposes the following entities.

### Quick Reference (All Entities)

#### Numbers (Settings)

* `number.<plant_id>_watering_interval_days` (0…60)
* `number.<plant_id>_fertilizing_interval_days` (0…365)
* `number.<plant_id>_moisture_min` / `number.<plant_id>_moisture_max` (0…100)
* `number.<plant_id>_humidity_min` / `number.<plant_id>_humidity_max` (0…100)
* `number.<plant_id>_temp_min` / `number.<plant_id>_temp_max` (-10…50, step 0.5)
* `number.<plant_id>_light_min` / `number.<plant_id>_light_max` (0…100000, informational)

#### Buttons (Actions)

* `button.<plant_id>_watering_mark_watered`
* `button.<plant_id>_fertilizing_mark_fertilized`
* `button.<plant_id>_ai_analyze`

The AI button uses the default image configured in the plant options. If no image is available,
Home Assistant reports a clear service error.

#### Binary Sensors (Tasks)

* `binary_sensor.<plant_id>_watering_due`
* `binary_sensor.<plant_id>_fertilizing_due`

Attributes on task sensors:

* `next_due_date`
* `days_overdue`

#### Sensors (Task Diagnostics)

* `sensor.<plant_id>_watering_last`
* `sensor.<plant_id>_watering_next`
* `sensor.<plant_id>_fertilizing_last`
* `sensor.<plant_id>_fertilizing_next`

#### AI Analysis Results

* `sensor.<plant_id>_ai_health_score` — integer from 0 to 100
* `sensor.<plant_id>_ai_status` — `healthy`, `watch`, `stressed`, `critical`, or `unknown`
* `sensor.<plant_id>_ai_confidence` — confidence from 0 to 100%
* `sensor.<plant_id>_ai_diagnosis` — short primary issue or summary
* `sensor.<plant_id>_ai_last_analysis` — timestamp of the last successful analysis
* `binary_sensor.<plant_id>_ai_attention_required`

The diagnosis sensor exposes the latest summary, observations, recommendations, urgency, and
watering advice as attributes. Full analysis history is deliberately kept out of entity attributes.
Use `plant_care.get_analysis_history` to retrieve up to the 20 retained analyses.

### AI Service Examples

Target the existing plant device and optionally override its configured image:

```yaml
action: plant_care.analyze_plant
target:
  device_id: YOUR_PLANT_DEVICE_ID
data:
  image_entity: camera.peace_lily_current
```

Use a local Home Assistant media item:

```yaml
action: plant_care.analyze_plant
data:
  plant_id: peace_lily
  image_media_content_id: media-source://media_source/local/plants/peace-lily.jpg
```

An allowlisted local file path is also supported for scripts:

```yaml
action: plant_care.analyze_plant
data:
  plant_id: peace_lily
  image_path: /config/www/plants/peace-lily.jpg
```

Retrieve bounded history for a future dashboard or script:

```yaml
action: plant_care.get_analysis_history
data:
  plant_id: peace_lily
  limit: 5
response_variable: plant_analysis_history
```

`plant_care.analyze_plant` also supports an optional response. When requested, it returns the newly
stored analysis object.

### Privacy, Cost, and Limitations

When analysis is triggered, the selected image, plant metadata, current measurements, aggregated
sensor history, care timestamps, and compact prior analysis summaries are sent to OpenAI. Review
OpenAI's data and privacy terms before enabling the feature. Raw recorder state changes are not sent;
Plant Care sends aggregates and daily averages to limit tokens and cost. Images are limited to 10 MB.

AI diagnosis is advisory and can be wrong. It cannot inspect roots, soil structure, pests hidden from
the image, or conditions that are not represented by configured sensors. Treat urgent or repeated
findings as prompts for closer inspection rather than definitive diagnoses.

Recorder is optional. If it is unavailable, analysis continues with current measurements and care
state. Provider authentication, quota, network, malformed-response, unavailable-image, unsupported
format, and oversized-image failures are reported as Home Assistant errors; a failed result is never
stored.

#### Binary Sensors (Environment Problems)

(only meaningful if external sensors are assigned)

* `binary_sensor.<plant_id>_temperature_out_of_range`
* `binary_sensor.<plant_id>_humidity_out_of_range`
* `binary_sensor.<plant_id>_moisture_out_of_range`

#### Sensors (Environment Deviation)

* `sensor.<plant_id>_temperature_deviation`
* `sensor.<plant_id>_humidity_deviation`
* `sensor.<plant_id>_moisture_deviation`

Deviation behavior:

* `0.0` → value is within bounds
* `> 0` → value is outside bounds
* `unavailable` → no sensor configured / invalid sensor value

---

## How It Works

### Core Rules (Watering & Fertilizing)

#### Disable a task

If interval is `0`:

* task is disabled
* due sensor is `off`
* next due date is `None`
* no overdue calculation

#### Enable a task

If interval is `> 0`:

* If never done before: task is **immediately due**
* If done before: next due date = `last_done + interval_days`
* Due when `today >= next_due_date`

### External Sensors (Optional)

You may assign these in the plant device options:

* temperature sensor
* humidity sensor
* soil moisture sensor

If you don’t assign a sensor:

* related entities are disabled by default
* values show `unavailable`
* out-of-range sensors won’t create false alerts

---

## Automations (YAML Examples)

> Tip: These examples use `notify.mobile_app_phone`. Replace it with your notifier (e.g. `notify.notify`, `notify.mobile_app_<device>`, etc.).

### 1) Notify when watering is due

```yaml
alias: "Plant - Monstera needs watering"
description: "Send a notification when Monstera watering becomes due"
trigger:
  - platform: state
    entity_id: binary_sensor.monstera_deliciosa_watering_due
    to: "on"
action:
  - service: notify.mobile_app_phone
    data:
      message: "Monstera needs watering 🌱"
mode: single
```

### 2) Include overdue days in the message

```yaml
alias: "Plant - Watering overdue message"
trigger:
  - platform: state
    entity_id: binary_sensor.monstera_deliciosa_watering_due
    to: "on"
action:
  - service: notify.mobile_app_phone
    data:
      message: >-
        Monstera needs watering 🌱
        Overdue: {{ state_attr('binary_sensor.monstera_deliciosa_watering_due', 'days_overdue') }} day(s)
mode: single
```

### 3) Notify when temperature is out of range

```yaml
alias: "Plant - Temperature out of range"
trigger:
  - platform: state
    entity_id: binary_sensor.monstera_deliciosa_temperature_out_of_range
    to: "on"
action:
  - service: notify.mobile_app_phone
    data:
      message: >-
        Monstera temperature is out of range 🌡️
        Deviation: {{ states('sensor.monstera_deliciosa_temperature_deviation') }}
mode: single
```

### 4) Disable fertilizing for a plant

```yaml
service: number.set_value
target:
  entity_id: number.monstera_deliciosa_fertilizing_interval_days
data:
  value: 0
```

### 5) Notify on **any** plant problem (one automation)

This automation listens to *all* `state_changed` events and notifies you when any Plant Care **problem** binary sensor turns `on`.

> ✅ Includes task due sensors and out-of-range sensors.
> ❗ Replace `notify.mobile_app_phone` with your notifier.

```yaml
alias: Plant Care - Notify on any problem
description: ""
mode: queued

trigger:
  - platform: event
    event_type: state_changed

condition:
  - condition: template
    value_template: >
      {% set e  = trigger.event.data.entity_id %}
      {% set ns = trigger.event.data.new_state %}
      {% set os = trigger.event.data.old_state %}
      {{ e is string
         and e.startswith('binary_sensor.')
         and ns is not none
         and ns.state == 'on'
         and (os is none or os.state != 'on')
         and ns.attributes.get('device_class') == 'problem'
         and (
           e.endswith('_watering_due')
           or e.endswith('_fertilizing_due')
           or e.endswith('_temperature_out_of_range')
           or e.endswith('_humidity_out_of_range')
           or e.endswith('_moisture_out_of_range')
         )
      }}

action:
  - service: notify.mobile_app
    data:
      title: Plant Care
      message: >
        {% set ns = trigger.event.data.new_state %}
        🚨 {{ ns.name }}
        {% set attrs = ns.attributes %}
        {% if attrs.get('next_due_date') %} Next due: {{ attrs.get('next_due_date') }}{% endif %}
        {% if attrs.get('days_overdue') is not none %} Overdue: {{ attrs.get('days_overdue') }} day(s){% endif %}
        {% if attrs.get('deviation') is not none %}
          {% set dev = attrs.get('deviation') | float(default=none) %}
          {% if dev is not none %} Deviation: {{ dev | round(2) }}{% else %} Deviation: {{ attrs.get('deviation') }}{% endif %}
        {% endif %}

```

---

## Update Behavior

The coordinator recalculates:

* Every **15 minutes** (environment monitoring)
* Daily at **03:00**
* Immediately when:
  * a button is pressed
  * a number setting changes

---
## FAQ

<details>
<summary><strong>Click to expand FAQ</strong></summary>

### What problem does this integration solve?
This integration does **not** water your plants automatically.

It helps you **track when care is needed** and **detect problems**, then exposes that information as Home Assistant entities so you can build automations, notifications, and dashboards around it.

Think of it as a **plant care state engine**, not a controller.

---

### Why are there no notifications?
Home Assistant users typically want full control over notification channels, schedules, and quiet hours.

This integration exposes **state**, and you decide what happens via automations.  
Feel free to use and adapt the automation templates provided in the README.

---

### Why are some entities disabled by default?
Environment-related entities are disabled by default when no external sensors are assigned.

This avoids:
- unnecessary noise
- permanent `unavailable` states
- clutter in dashboards and entity lists

---

### What happens if I don’t have temperature / humidity / soil sensors?
Nothing breaks.

All environment sensors are **optional**:
- watering and fertilizing tracking still works
- environment entities remain `unavailable`
- no false alerts are generated

---

### Will renaming a plant break my automations?
No.

Entity IDs are based on a generated `<plant_id>` and remain stable.  
Renaming a plant only affects:
- the device name
- friendly names

---

### What does setting an interval to `0` mean?
An interval of `0` means the feature is **disabled**.

For example:
- `watering_interval_days = 0` → watering tracking is disabled
- `fertilizing_interval_days = 0` → fertilizing tracking is disabled

Disabled tasks:
- never become due
- never become overdue
- do not generate alerts

---

### What happens the first time I enable watering or fertilizing?
If a task has **never been marked as done** and the interval is `> 0`, it is considered **immediately due**.

This avoids silently waiting for weeks after initial setup.

---

### Can I use this with many plants?
Yes — this is a core design goal.

Each plant:
- is its own Home Assistant device
- has its own entities
- can be filtered, grouped, and automated independently

The integration scales cleanly from **one plant to dozens**.

---

### Does this integrate with the Home Assistant Plant integration?
No.

This is a separate integration with a different design philosophy:
- interval-based tasks
- explicit due / overdue states
- optional sensors
- no opinionated notifications

Both integrations can be used side by side if desired.

---

### Why is there no automatic watering or pump control?
This integration focuses on **state and decision-making**, not hardware control.

If you use pumps, valves, or relays:
- trigger them via automations
- use the `*_due` sensors as conditions
- mark tasks done using the provided buttons

This keeps the integration simple, predictable, and hardware-agnostic.

</details>

---

## ❤️ Support

If this Home Assistant integration is useful to you and saves you time, you can support its development:

🍕 **Buy me a pizza:** https://buymeacoffee.com/ako_

Starring the repository ⭐ and reporting issues or improvements are also great ways to help.
