# Bambu-Notify

A simple webhook notification script for Bambu Lab printers.

# Usage

```sh
python3 ./bambu-notify.py
```

# Configure

```sh
HOSTNAME    = "YOUR_PRINTER_IP"
ACCESS_CODE = "YOUR_PRINTER_ACCESS_CODE"
SERIAL      = "YOUR_PRINTER_SERIAL_NUMBER"
WEBHOOK     = "URL TO WEBHOOK"

WEBHOOK_2   = "URL TO ADDITIONAL WEBHOOK 2."
WEBHOOK_3   = "URL TO ADDITIONAL WEBHOOK 3."
WEBHOOK_4   = "URL TO ADDITIONAL WEBHOOK 4."
WEBHOOK_5   = "URL TO ADDITIONAL WEBHOOK 5."

MESSAGES_FILE = "messages.json"

## These are the defaults

# Report start, finish and failure.
REPORT_START = "Y"
REPORT_FINISH = "Y"
REPORT_FAILURE = "Y"

# Show the first Layer
REPORT_FIRST_LAYER = "Y"

# Show the second layer
REPORT_SECOND_LAYER = "Y"

# Report at 25%, 50%, 75%
REPORT_25_PERC = "N"
REPORT_50_PERC = "Y"
REPORT_75_PERC = "N"

# Report every 5%
REPORT_EVERY_5_PERC = "N"

# Report every 10%
REPORT_EVERY_10_PERC = "N"

```
