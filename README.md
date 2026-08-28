# Kungsbacka Library

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Home Assistant custom integration for **Kungsbacka kommun bibliotek** (Kungsbacka public library). Track your active loans, overdue books, and upcoming due dates directly in your smart home dashboard.

## Features

- **Active loans** — sensor showing the total number of books you currently have on loan, with full details (title, author, due date, branch) as attributes.
- **Overdue loans** — sensor counting how many books are past their due date.
- **Next due date** — timestamp sensor showing when your next book is due, useful for automations.
- **Multiple cards** — add multiple library cards (family members) as separate entries.
- **Swedish & English** — full UI translations.

## Installation

### HACS (recommended)

1. Open HACS in your Home Assistant instance.
2. Go to **Integrations** → **⋮** (top right) → **Custom repositories**.
3. Add this repository URL and select **Integration** as the category.
4. Click **Install**.
5. Restart Home Assistant.

### Manual

1. Copy the `custom_components/kungsbacka_library` folder into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration

1. Go to **Settings** → **Devices & Services** → **Add Integration**.
2. Search for **Kungsbacka Library**.
3. Enter your library card number and 4-digit PIN code.

## Sensors

| Sensor | State | Attributes |
|--------|-------|------------|
| Active loans | Number of current loans | Full list of loans with title, author, due date, branch |
| Overdue loans | Number of overdue items | — |
| Next due date | Timestamp of soonest due date | Title, author, and branch of that book |

## Example automation

Get notified when a book is due tomorrow:

```yaml
automation:
  - alias: "Library book due tomorrow"
    trigger:
      - platform: template
        value_template: >
          {{ (states('sensor.kungsbacka_library_next_due_date') | as_datetime - now()).days == 1 }}
    action:
      - service: notify.mobile_app
        data:
          title: "📚 Book due tomorrow"
          message: >
            "{{ state_attr('sensor.kungsbacka_library_next_due_date', 'title') }}"
            is due tomorrow. Remember to return or renew it!
```

## Technical details

This integration communicates with the **Axiell Arena PALMA SOAP API** used by Kungsbacka kommun's library system. Data is polled once per hour by default.

## License

MIT
