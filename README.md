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

# Report differently for prints over 120 minutes (2 hours)
REPORT_LONG_THRESHOLD = "120"
REPORT_LONG_25_PERC = "Y"
REPORT_LONG_50_PERC = "Y"
REPORT_LONG_75_PERC = "Y"

# Report every 5%
REPORT_EVERY_5_PERC = "N"

# Report every 10%
REPORT_EVERY_10_PERC = "N"

```


# Things it cant do:

- Info is kinda sparse atm, will add more variables as i figure them out.
- Start notification cannot have picture.
- If it disconnects it just bugs out, i will add more error handling as we go... threads fucking suck arse.


# TODO:

- [ ] Add more variables
- [ ] Add better error handling
- [ ] Add better state handling for resuming from crashes.
- [ ] Create some better default templates.
- [ ] Create a script that will launch the program when it detects the printer is online and will restart it.
