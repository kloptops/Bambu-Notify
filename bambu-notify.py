#!/bin/env python3

# SPDX-License-Identifier: MIT

import json
import os
import pathlib
import pprint
import queue
import threading
import time

from pathlib import Path
from dataclasses import asdict

import requests

from dotenv import load_dotenv
from bambu_connect import BambuClient, PrinterStatus


load_dotenv()

# Replace these with your actual details
hostname      = os.getenv('HOSTNAME')
access_code   = os.getenv('ACCESS_CODE')
serial        = os.getenv('SERIAL')
webhook_urls  = [os.getenv('WEBHOOK')]
messages_file = os.getenv('MESSAGES_FILE')

i = 2
while True:
    additional_url = os.getenv(f'WEBHOOK_{i}')
    if additional_url is None:
        break

    webhook_urls.append(additional_url)
    i += 1

report_first_layer  = os.getenv('REPORT_FIRST_LAYER', 'Y')
report_second_layer = os.getenv('REPORT_SECOND_LAYER', 'Y')

report_25_perc = os.getenv('REPORT_25_PERC', 'N')
report_50_perc = os.getenv('REPORT_50_PERC', 'Y')
report_75_perc = os.getenv('REPORT_75_PERC', 'N')

report_every_5_perc  = os.getenv('REPORT_EVERY_5_PERC', 'N')
report_every_10_perc = os.getenv('REPORT_EVERY_10_PERC', 'N')

report_start   = os.getenv('REPORT_START',   'Y')
report_finish  = os.getenv('REPORT_FINISH',  'Y')
report_failure = os.getenv('REPORT_FAILURE', 'Y')

# Running variables.
FIRST_STATE_EVENT = False

LAST_FRAME = b""
LAST_STATE = None

REPORTED_PERCENTAGES  = {}
REPORTED_FIRST_LAYER  = False
REPORTED_SECOND_LAYER = False
REPORTED_25_PERCENT = False
REPORTED_50_PERCENT = False
REPORTED_75_PERCENT = False

THREAD_LOCK   = threading.RLock()

CAMERA_ACTIVE = False

CAMERA_TIMER  = None
TASK_QUEUE    = queue.Queue()

bambu_client  = None

### Classes

class ReusableTimer:
    def __init__(self, interval, task, recurring=False):
        self.interval = interval
        self.task = task
        self.timer = None
        self.running = False
        self.recurring = recurring

    def start(self):
        if not self.running:
            self.running = True
            self._schedule_next()

    def _schedule_next(self):
        if self.running:
            self.timer = threading.Timer(self.interval, self._run_task)
            self.timer.start()

    def _run_task(self):
        self.task()
        if self.recurring:
            self._schedule_next()  # Schedule the next execution

    def restart(self):
        # cancel task if running then start it again, otherwise just start it.
        if self.running:
            self.stop()
        self.start()

    def stop(self):
        if self.timer:
            self.timer.cancel()
        self.running = False


### Functions

def do_start_print():
    global REPORTED_FIRST_LAYER, REPORTED_SECOND_LAYER, REPORTED_PERCENTAGES
    global REPORTED_25_PERCENT, REPORTED_50_PERCENT, REPORTED_75_PERCENT

    REPORTED_PERCENTAGES.clear()
    REPORTED_FIRST_LAYER  = False
    REPORTED_SECOND_LAYER = False
    REPORTED_25_PERCENT = False
    REPORTED_50_PERCENT = False
    REPORTED_75_PERCENT = False


def do_report_event(printer_status):
    """
    Figure out the most appropriate event to send a message about.

    The logic is that if we want first/second layer notification, then 25% progress should not fire before that event.

    TODO: base percentage on the number of layers done instead of the printer reporting.
    """

    global LAST_STATE, REPORTED_SECOND_LAYER, REPORTED_FIRST_LAYER, REPORTED_PERCENTAGES, FIRST_STATE_EVENT
    global REPORTED_25_PERCENT, REPORTED_50_PERCENT, REPORTED_75_PERCENT

    state_text = {
        "PREPARE": "Starting",
        "FAILED": "Failed",
        "FINISH": "Finished",
        "RUNNING": "Printing",
        "IDLE": "Idle",
        }

    printer_status.setdefault('current_status', state_text.get(printer_status['gcode_state']
, 'Printing'))

    printer_status['layer_num'] = get_value(printer_status, 'layer_num', 0)
    printer_status['total_layer_num'] = get_value(printer_status, 'total_layer_num', 1)

    if printer_status['total_layer_num'] == 0:
        printer_status['total_layer_num'] = 1

    # Fix the percentage based on layer number.
    printer_status['mc_percent'] = int(printer_status['layer_num'] / printer_status['total_layer_num'] * 100)

    # ALL OTHER STATE LOGIC
    if printer_status['gcode_state'] != LAST_STATE:
        if printer_status['gcode_state'] == 'PREPARE':

            LAST_STATE = printer_status['gcode_state']

            do_start_print()

            if report_start == 'Y':
                return 'print_start'

            return None

        if printer_status['gcode_state'] == 'FAILED':
            LAST_STATE = printer_status['gcode_state']

            if report_failure == 'Y':
                return 'print_fail'

            return None

        if printer_status['gcode_state'] == 'FINISH':
            LAST_STATE = printer_status['gcode_state']

            if report_finish == 'Y':
                return 'print_finish'

            return None

        if printer_status['gcode_state'] != 'RUNNING':
            LAST_STATE = printer_status['gcode_state']
            print(f"Unknown state {LAST_STATE}")
            return None

        LAST_STATE = printer_status['gcode_state']

    if printer_status['gcode_state'] != 'RUNNING':
        return None

    # RUNNING STATE LOGIC
    if report_first_layer == 'Y' and REPORTED_FIRST_LAYER == False:
        if printer_status['layer_num'] > 1:
            REPORTED_FIRST_LAYER = True
            return 'print_status'

        return None

    if report_second_layer == 'Y' and REPORTED_SECOND_LAYER == False:
        if printer_status['layer_num'] > 2:
            REPORTED_SECOND_LAYER = True
            return 'print_status'

        return None

    # Highest priority.
    percentage_5_perc = (printer_status['mc_percent'] // 5 * 5) == printer_status['mc_percent']
    if report_every_5_perc == 'Y':
        if REPORTED_PERCENTAGES.get(printer_status['mc_percent'], False) == False:
            REPORTED_PERCENTAGES[printer_status['mc_percent']] = True
            return 'print_status'

        return None

    # Next highest priority.
    percentage_10_perc = (printer_status['mc_percent'] // 10 * 10) == printer_status['mc_percent']
    if report_every_10_perc == 'Y':
        if REPORTED_PERCENTAGES.get(printer_status['mc_percent'], False) == False:
            REPORTED_PERCENTAGES[printer_status['mc_percent']] = True
            return 'print_status'

        return None

    # Fall back to standard 25/50/75% reporting.
    if report_25_perc == "Y" and REPORTED_25_PERCENT == False:
        if printer_status['mc_percent'] >= 25:
            REPORTED_25_PERCENT = True
            return 'print_status'

        return None

    if report_50_perc == "Y" and REPORTED_50_PERCENT == False:
        if printer_status['mc_percent'] >= 50:
            REPORTED_50_PERCENT = True
            return 'print_status'

        return None

    if report_75_perc == "Y" and REPORTED_75_PERCENT == False:
        if printer_status['mc_percent'] >= 75:
            REPORTED_75_PERCENT = True
            return 'print_status'

        return None

    return None


def oc_join(strings):
    """
    Oxford comma join
    """
    if len(strings) == 0:
        return ""

    elif len(strings) == 1:
        return strings[0]

    elif len(strings) == 2:
        return f"{strings[0]} and {strings[1]}"

    else:
        oxford_comma_list = ", ".join(strings[:-1]) + ", and " + strings[-1]
        return oxford_comma_list


def format_time(minutes):
    if minutes == 0:
        return "0 minutes"

    days = minutes // (24 * 60)
    hours = (minutes % (24 * 60)) // 60
    mins = minutes % 60

    parts = []
    if days > 0:
        parts.append(f"{days} day{'s' if days > 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours > 1 else ''}")
    if mins > 0:
        parts.append(f"{mins} minute{'s' if mins > 1 else ''}")

    return oc_join(parts)


def format_file(data):
    file_name = data.get('gcode_file', None)
    if file_name == '' or file_name is None:
        file_name = data.get('subtask_name', None)

        if file_name == '' or file_name is None:
            return 'Unknown File'

    if file_name.rsplit('.', 1)[-1] in ('stl', '3mf', 'step'):
        file_name = file_name.rsplit('.', 1)[0]

    return file_name


def get_value(data, value, default):
    result = data.get(value, default)

    if result is None:
        return default

    return result


def format_message(message_text, printer_status):
    return (message_text
        .replace("{{CURRENT_STATUS}}", get_value(printer_status, 'current_status', 'Printing'))
        .replace("{{CURRENT_LAYER}}", str(get_value(printer_status, 'layer_num', 0)))
        .replace("{{TOTAL_LAYERS}}", str(get_value(printer_status, 'total_layer_num', 1)))
        .replace("{{PERCENTAGE}}", str(get_value(printer_status, 'mc_percent', 1)))
        .replace("{{REMAINING}}", format_time(get_value(printer_status, 'mc_remaining_time', 0)))
        .replace("{{PRINT_NAME}}", format_file(printer_status))
        )


def get_message(event_type):
    global messages_file

    default_message = "**{{CURRENT_STATUS}} {{PRINT_NAME}}:**\nLayer: {{CURRENT_LAYER}} / {{TOTAL_LAYERS}} *({{PERCENTAGE}} %)*\nREMAINING: {{REMAINING}}"
    if messages_file is None:
        return default_message

    try:
        with open(messages_file, 'r') as fh:
            data = json.load(fh)

        return data.get(event_type, data.get(event_type, default_message))

    except Exception as err:
        print(f"Error: problem parsing {messages_file}: {err}")
        return default_message


def save_latest_frame(img):
    global LAST_FRAME, THREAD_LOCK
    """Save the latest frame to a variable."""
    with THREAD_LOCK:
        LAST_FRAME = img


def get_latest_frame():
    global LAST_FRAME, THREAD_LOCK
    """Fetch the latest frame from the variable."""
    with THREAD_LOCK:
        return LAST_FRAME


def start_camera():
    global THREAD_LOCK, CAMERA_ACTIVE, CAMERA_TIMER, bambu_client

    with THREAD_LOCK:
        if CAMERA_ACTIVE:
            return

        if CAMERA_TIMER.running:
            print("Notice: REENABLE CAMERA STREAM")

            CAMERA_TIMER.stop()
            CAMERA_ACTIVE = True
            return

        print("Notice: ENABLE CAMERA STREAM")
        bambu_client.start_camera_stream(save_latest_frame, stop_camera_for_reals)
        CAMERA_ACTIVE = True


def stop_camera():
    global THREAD_LOCK, CAMERA_ACTIVE, CAMERA_TIMER

    with THREAD_LOCK:
        if not CAMERA_ACTIVE:
            return

        print("Notice: DISABLING CAMERA STREAM")
        CAMERA_TIMER.start()
        CAMERA_ACTIVE = False


def stop_camera_for_reals():
    global bambu_client, LAST_FRAME, THREAD_LOCK, CAMERA_ACTIVE

    print("Notice: DISABLE CAMERA STREAM")
    bambu_client.stop_camera_stream()

    with THREAD_LOCK:
        CAMERA_ACTIVE = False
        LAST_FRAME = b""


def custom_callback(msg):
    global FIRST_STATE_EVENT, TASK_QUEUE

    printer_status = asdict(msg)

    if not FIRST_STATE_EVENT:
        event_type = do_report_event(printer_status)

        print(f"- {event_type}")

        if event_type == 'printer_status':
            TASK_QUEUE.put((event_type, printer_status))

        while (skipped_events := do_report_event(printer_status)):
            print(f"   skipping {skipped_events} event")
            pass

        FIRST_STATE_EVENT = True
        return

    event_type = do_report_event(printer_status)

    if not event_type:
        return

    print(f"- {event_type}")

    while (skipped_events := do_report_event(printer_status)):
        print(f"   skipping {skipped_events} event")
        pass

    # Add to event queue
    TASK_QUEUE.put((event_type, printer_status))


def main_queue_runner():
    global TASK_QUEUE, THREAD_LOCK, LAST_FRAME, webhook_urls

    while True:
        task = TASK_QUEUE.get()
        if task is None:
            break

        print(f"{task}")

        event_type, printer_status = task

        print(f"{event_type}")

        if event_type in ('print_status'):
            start_camera()

        if event_type in ('print_fail', 'print_finish'):
            stop_camera()

        camera_image = b""

        for i in range(10):
            # Wait 10 seconds maximum for an image from the camera.
            camera_image = get_latest_frame()
            if LAST_FRAME != b"":
                break

            time.sleep(1)

        else:
            print("Error: Unable to get camera_image.")

        # DO DISPLAY STUFF HERE.
        print(f"EVENT {event_type}")

        message_text = format_message(get_message(event_type), printer_status)

        for i, webhook_url in enumerate(webhook_urls):
            if camera_image is None or camera_image == b"":
                response = requests.post(
                    webhook_url,
                    data={"content": message_text})

            else:
                response = requests.post(
                    webhook_url,
                    files={"camera.jpg": camera_image},
                    data={"content": message_text})

            if response.status_code in (204, 200):  # No Content
                print(f"  WEBHOOK {i} SUCCESS")
            else:
                print(f"  WEBHOOK {i} FAILURE: {response.status_code}: {response.text}")

            time.sleep(2)

def on_watch_client_connect():
    print("Notice: WatchClient connected, Waiting for connection...")
    time.sleep(1)  # Waits for 1 second

    print("Notice: Executing dump_info.")
    bambu_client.dump_info()

### Stuff

def main():
    global bambu_client, CAMERA_ACTIVE, CAMERA_TIMER, TASK_QUEUE

    bambu_client = BambuClient(hostname, access_code, serial)
    activity_thread = None

    # Stop camera after 30 or so seconds.
    CAMERA_TIMER = ReusableTimer(30, stop_camera_for_reals)

    try:
        bambu_client.start_watch_client(custom_callback, on_watch_client_connect)

        activity_thread = threading.Thread(target=main_queue_runner)

        activity_thread.start()

        while True:
            time.sleep(1)  # Just keep the main thread alive

    except KeyboardInterrupt as err:
        pass

    finally:
        print("Notice: Streaming stopped.")

        TASK_QUEUE.put(None)

        if activity_thread:
            activity_thread.join()

        if CAMERA_ACTIVE:
            bambu_client.stop_camera_stream()

        bambu_client.stop_watch_client()


if __name__ == '__main__':
    main()
