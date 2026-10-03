# iPhone watering widget

Plant Care supports the Home Assistant Companion App without a separate iOS
application. It exposes two Home Assistant actions for this purpose:

- `plant_care.get_watering_queue` returns the current due-only, urgency-sorted
  list.
- `plant_care.mark_watered` calls the same watering implementation as each
  plant's existing `button.<plant_id>_watering_mark_watered` entity.

The default due-soon window is one day. Pass `due_soon_days: 0` for only
overdue and due-today plants, or a larger value to look further ahead.
Both flows below require iOS 17 or later and a current Home Assistant Companion
App. The Custom Widget itself was introduced in Companion App 2025.3.

## Current iOS limitation

The Companion App's Custom Widget is the only native Home Screen widget that
can press a Home Assistant `button` entity in the background. Its configuration
is a saved, ordered list of entity IDs. The app currently does not let a Home
Assistant integration provide a dynamic list, filter tiles by state, or change
their order. Consequently, the stock app cannot yet combine all three of these
behaviors in one widget:

1. automatically show only due plants;
2. sort the visible rows whenever dates change; and
3. give every generated row its own action.

This is a Companion App constraint, not a Plant Care data limitation. Plant
Care therefore provides two supported choices instead of adding a fragile
second watering system.

## Install or update Plant Care

1. Update the Plant Care custom integration through HACS, or copy
   `custom_components/plant_care` into the Home Assistant configuration
   directory.
2. Restart Home Assistant.
3. Do not change the existing plant entries or dashboard cards. Existing
   watering buttons continue to work.
4. In **Developer tools > Actions**, run **Plant Care: Get watering queue**
   with a due-soon window of `1`. Confirm that the response contains the
   expected `plants` and `menu` values.
5. Test **Plant Care: Mark plant as watered** against one plant device. Confirm
   that its existing Last Watered, Next Watering, and Watering Due entities
   update.

No YAML helper, duplicate interval, API token, or external iOS app is needed.

## Option A: direct native controls

This is the fastest and most native option. It runs in the widget extension and
does not need to open Home Assistant, but the chosen plant tiles are static.

1. Update the Home Assistant Companion App on the iPhone.
2. Open **Home Assistant > Settings > Companion app > Widgets**.
3. Tap **Create**, name the widget `Plant Watering`, and add the existing
   `button.<plant_id>_watering_mark_watered` entities.
4. For each item, keep **On tap** set to **Default**. Choose a water icon and a
   short plant label. Disable **Require confirmation** only if accidental taps
   are acceptable.
5. Save the widget.
6. Touch and hold the iPhone Home Screen, tap **+**, choose **Home Assistant**,
   then choose **Custom Widget**.
7. Select a size, add it, touch and hold it, choose **Edit Widget**, and select
   `Plant Watering`.

The current Companion App supports up to 3 tiles in Small, 6 in Medium, and 12
in Large. Medium is the best default. Put the most important plants first,
because smaller families show a prefix of the saved list.

When a tile is tapped, the Companion App sends `button.press` directly. Plant
Care persists `last_watered`, recalculates `next_watering`, and refreshes the
existing entities. A connection or server error produces a failure
notification and does not report a successful watering.

## Option B: dynamic due-only chooser

This uses Apple's built-in Shortcuts app and the Home Assistant App Intents. It
always discovers the current plants and presents them in overdue, due-today,
then due-soon order. It is a single Home Screen tile that opens a native choice
menu; it cannot display that live menu before it is tapped.

Create a shortcut named `Water plants`:

1. Add **Home Assistant > Perform action**.
2. Select the Home Assistant server and action
   `plant_care.get_watering_queue`.
3. Set Action data to `{"due_soon_days": 1, "limit": 12}`.
4. Add **Get Dictionary from Input**, using the Perform Action result.
5. Add **Get Dictionary Value** for the key `menu`.
6. Add **Get Dictionary Value**, choose **All Keys**, and use the `menu`
   dictionary as input.
7. If the keys list is empty, show `No plants need watering` and stop the
   shortcut.
8. Otherwise, add **Choose from List** using the keys. The choices are formatted
   like `Peace Lily — 1 day overdue`.
9. Get the chosen key's value from the `menu` dictionary. This value is the
   stable Plant Care ID.
10. Add a **Dictionary** action with key `plant_id` and that value.
11. Add another **Home Assistant > Perform action**, select
    `plant_care.mark_watered`, and pass the Dictionary as Action data.
12. Add **Home Assistant > Reload widgets** so other Home Assistant widgets ask
    iOS for a fresh timeline.

To place it on the Home Screen, touch and hold the Home Screen, tap **+**,
choose **Shortcuts**, add the single-shortcut widget, then edit it and select
`Water plants`.

The Home Assistant app does not open during either Perform Action step. The
Shortcuts choice sheet is shown because a plant must be selected safely.

## Queue response

Example:

```json
{
  "count": 3,
  "plants": [
    {
      "plant_id": "peace_lily",
      "name": "Peace Lily",
      "status": "overdue",
      "status_label": "1 day overdue",
      "last_watered": "2026-09-25T08:30:00+02:00",
      "next_watering": "2026-10-02",
      "button_entity_id": "button.peace_lily_watering_mark_watered"
    }
  ],
  "menu": {
    "Peace Lily — 1 day overdue": "peace_lily"
  }
}
```

Plants are omitted when their watering interval is `0`, their next watering
date is missing, their coordinator is unavailable, or their next watering date
is outside the requested window. Dates use Home Assistant's local timezone.

## Verify end to end

1. Choose a plant that is currently due and note its Last Watered and Next
   Watering entity values.
2. Run `plant_care.get_watering_queue` and confirm the plant is present.
3. Tap its direct Custom Widget tile, or choose it in `Water plants`.
4. Confirm Last Watered changed to the current local time and Next Watering is
   Last Watered's local date plus the existing interval.
5. Run `plant_care.get_watering_queue` again. The plant must disappear unless
   its newly calculated date is still inside the due-soon window.

Widget timelines are controlled by iOS and normally refresh around every 15
minutes. The Shortcut explicitly calls Reload widgets after watering, but iOS
can still defer a visual refresh. The Home Assistant entities and queue response
are the authoritative verification.

## References

- [Home Assistant Companion: iOS Widgets](https://companion.home-assistant.io/docs/integrations/ios-widgets/)
- [Home Assistant Companion: Apple App Intents](https://companion.home-assistant.io/docs/integrations/siri-shortcuts/)
- [Companion App Custom Widget source](https://github.com/home-assistant/iOS/blob/main/Sources/Extensions/Widgets/Custom/WidgetCustomTimelineProvider.swift)
- [Companion App button App Intent source](https://github.com/home-assistant/iOS/blob/main/Sources/Extensions/Widgets/Custom/AppIntents/CustomWidgetPressButtonAppIntent.swift)
