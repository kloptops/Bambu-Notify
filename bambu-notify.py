#!/usr/bin/env python3

import argparse
import logging
import queue
import signal
import sys
import threading
import time
import json

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Union

import jinja2
import requests
import yaml

from bambu_connect import BambuClient, PrinterStatus

from bambu_defs import STAGE_DESCRIPTIONS

# --- Setup Logging ---
log = logging.getLogger("bambu-notify")

# --- Helper Functions & Classes ---
def format_time(minutes: int) -> str:
    """Formats minutes into a human-readable string like '1 day, 2 hours, and 5 minutes'."""
    if minutes == 0:
        return "less than a minute"

    days, rem = divmod(minutes, 1440)
    hours, mins = divmod(rem, 60)
    parts = []

    if days > 0:
        parts.append(f"{days} day{'s' if days > 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours > 1 else ''}")
    if mins > 0:
        parts.append(f"{mins} minute{'s' if mins > 1 else ''}")
    
    if len(parts) == 0:
        return ""

    if len(parts) == 1:
        return parts[0]

    return ", ".join(parts[:-1]) + f" and {parts[-1]}"


class StateManager:
    """Encapsulates all logic for managing printer state and deciding when to notify."""

    def __init__(self, config):
        self.config = config.get('notifications', {})
        self.is_primed = False
        # The gcode_state is now initialized here and NOT in the reset method.
        self.last_gcode_state = "IDLE" 
        self._reset_print_state()

    def _reset_print_state(self):
        """Resets all flags related to a single print job."""
        log.info("Resetting print job tracking.")
        # DO NOT reset last_gcode_state here. That tracks the machine, not the job.
        self.reported_percentages = set()
        self.reported_first_layer = False
        self.reported_second_layer = False

    def prime_state(self, status: PrinterStatus):
        """Sets the initial state from the first status message to prevent old notifications."""
        log.info("Priming state from initial printer status...")
        # We don't need a full reset here, just set the initial state
        self.last_gcode_state = status.gcode_state

        if status.gcode_state == 'RUNNING':
            log.debug(f"Printer is running. Priming progress: {status.mc_percent}% complete, layer {status.layer_num}.")
            if status.layer_num > 1:
                self.reported_first_layer = True
            if status.layer_num > 2:
                self.reported_second_layer = True

            # Mark all past percentages as "reported"
            for p in range(status.mc_percent + 1):
                self.reported_percentages.add(p)

        self.is_primed = True
        log.info("State has been primed.")

    def process_status(self, status: PrinterStatus) -> Union[str, None]:
        """Processes a new status update and returns an event name if a notification is needed."""
        if not self.is_primed:
            self.prime_state(status)
            return None # Don't notify on the first priming message

        event = None
        # --- Check for major state changes ---
        if status.gcode_state != self.last_gcode_state:
            log.info(f"State changed from '{self.last_gcode_state}' to '{status.gcode_state}'")
            
            # --- FIX: More specific condition for a new print start ---
            if status.gcode_state == 'RUNNING' and self.last_gcode_state != 'PAUSE':
                self._reset_print_state()
                if self.config.get('report_start', True): event = 'print_start'
            elif status.gcode_state == 'FINISH':
                if self.config.get('report_finish', True): event = 'print_finish'
            elif status.gcode_state == 'FAILED':
                if self.config.get('report_failure', True): event = 'print_failure'
            elif status.gcode_state == 'PAUSE':
                if self.config.get('report_pause', True): event = 'print_pause'
            elif self.last_gcode_state == 'PAUSE' and status.gcode_state == 'RUNNING':
                if self.config.get('report_resume', True): event = 'print_resume'
            
            # Update the state AFTER processing the change
            self.last_gcode_state = status.gcode_state
            if event: return event

        # --- If not printing, do nothing else ---
        if status.gcode_state != 'RUNNING':
            return None

        # --- Check for progress-based notifications ---
        if self.config.get('report_first_layer') and not self.reported_first_layer and status.layer_num > 1:
            self.reported_first_layer = True
            return 'progress_report'

        if self.config.get('report_second_layer') and not self.reported_second_layer and status.layer_num > 2:
            self.reported_second_layer = True
            return 'progress_report'

        # Percentage-based reporting
        for p in self.config.get('report_percentages', []):
            if p not in self.reported_percentages and status.mc_percent >= p:
                # Mark this and all previous percentages as reported to avoid spam
                for i in range(p + 1):
                    self.reported_percentages.add(i)
                return 'progress_report'
        
        return None


class CameraManager:
    """Manages the camera stream and frame capture."""
    def __init__(self, bambu_client: BambuClient):
        self._client = bambu_client
        self._lock = threading.Lock()
        self._last_frame = b""
        self._is_active = False

    def _save_frame_callback(self, frame: bytes):
        with self._lock:
            self._last_frame = frame

    def start(self):
        with self._lock:
            if self._is_active:
                return
            log.info("Starting camera stream...")
            self._client.start_camera_stream(self._save_frame_callback)
            self._is_active = True

    def stop(self):
        with self._lock:
            if not self._is_active:
                return
            log.info("Stopping camera stream...")
            self._client.stop_camera_stream()
            self._last_frame = b""
            self._is_active = False

    def get_frame(self, wait_seconds=5) -> bytes:
        """Tries to get a fresh frame from the camera, waiting if necessary."""

        # First, ensure the camera is active. Call start() OUTSIDE of the lock.
        # The start() method handles its own locking, so this is safe.
        if not self._is_active:
            self.start()

        # Now, wait for a frame to be delivered by the callback.
        for _ in range(wait_seconds):
            # We only need to lock when we're actually reading the shared _last_frame variable.
            with self._lock:
                if self._last_frame:
                    return self._last_frame
            time.sleep(1)        

        log.warning("Could not retrieve a camera frame in time.")
        return b""


class Notifier:
    """Renders templates and sends notifications to webhooks."""
    def __init__(self, config):
        # First, get the 'notifications' section of the config.
        notifications_config = config.get('notifications', {})
        
        # Now, get the specific settings from within that section.
        self.webhooks = notifications_config.get('webhooks', [])
        template_path = Path(notifications_config.get('template_file', 'messages.jinja'))
        
        if not template_path.exists():
            log.error(f"Template file not found at: {template_path}")
            sys.exit(1)

        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_path.parent),
            autoescape=True
        )
        self.jinja_env.globals['format_time'] = format_time
        self.template_name = template_path.name

    def send(self, event: str, status: PrinterStatus, frame: bytes):
        log.info(f"Sending notification for event: '{event}'")
        
        # If there are no webhooks configured, don't even bother rendering.
        if not self.webhooks:
            log.warning("No webhooks configured. Skipping notification.")
            return

        context = {'print': status, 'event': event}
        try:
            template = self.jinja_env.get_template(self.template_name)

            if event in template.blocks:
                content = "".join(template.blocks[event](template.new_context(context)))
            else:
                content = template.render(context)

        except Exception as e:
            log.error(f"Failed to render template for event '{event}': {e}")
            return

        for i, url in enumerate(self.webhooks):
            try:
                files = {'camera.jpg': (f"camera_{event}.jpg", frame, 'image/jpeg')} if frame else None
                
                if files:
                    payload = {'payload_json': json.dumps({'content': content})}
                    response = requests.post(url, files=files, data=payload, timeout=10)
                else:
                    response = requests.post(url, json={'content': content}, timeout=10)

                response.raise_for_status()
                log.info(f"  Webhook {i+1} sent successfully (Status: {response.status_code}).")
            except requests.RequestException as e:
                log.error(f"  Webhook {i+1} failed: {e}")

            time.sleep(1)

class PrintLogger:
    """Handles logging of print jobs to a file for later analysis."""

    KEYS_TO_OMIT = [
        'ams', 'vt_tray', 'lights_report', 'ipcam', 'upgrade_state', 'online', 
        'force_upgrade'
        ]

    def __init__(self, config):
        self.config = config.get('print_log', {})
        if not self.config.get('enabled', False):
            return

        self.log_dir = Path(self.config.get('log_directory', 'print_logs'))
        self.log_interval = self.config.get('log_interval_seconds', 15)
        
        self.is_logging = False
        self.log_file = None
        self.last_log_time = 0

        # Create the log directory if it doesn't exist
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            log.info(f"Print logs will be saved to: {self.log_dir.resolve()}")
        except OSError as e:
            log.error(f"Failed to create log directory {self.log_dir}: {e}")
            self.config['enabled'] = False # Disable logging if dir fails

    def _generate_filename(self, status: PrinterStatus) -> str:
        """Generates a log filename based on print metadata."""
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")

        # Use metadata from the status, with fallbacks for safety
        project_id = status.project_id or "p0"
        task_id = status.task_id or "t0"
        subtask_id = status.subtask_id or "s0"

        return f"print_{date_str}_{project_id}_{task_id}_{subtask_id}.log"

    def _filter_status(self, raw_status: dict) -> dict:
        """Removes large, unnecessary keys from the status dictionary."""
        filtered_data = raw_status.copy()
        for key in self.KEYS_TO_OMIT:
            filtered_data.pop(key, None) # Use pop with a default to avoid KeyErrors
        return filtered_data

    def start_logging(self, status: PrinterStatus):
        """Opens a new log file at the start of a print."""
        if self.is_logging:
            return
            
        filename = self._generate_filename(status)
        filepath = self.log_dir / filename
        
        try:
            self.log_file = open(filepath, 'w')
            self.is_logging = True
            self.last_log_time = 0 # Reset timer to log the first status immediately
            log.info(f"Starting new print log: {filename}")
        except IOError as e:
            log.error(f"Could not open log file {filepath}: {e}")

    def stop_logging(self):
        """Closes the current log file."""
        if not self.is_logging or not self.log_file:
            return

        log.info(f"Closing print log: {self.log_file.name}")
        self.log_file.close()
        self.log_file = None
        self.is_logging = False

    def process_status(self, status: PrinterStatus):
        """The main entry point to be called for every status update."""
        if not self.config.get('enabled', False):
            return

        # --- Detect Print Start/Stop ---
        is_printing = status.gcode_state == 'RUNNING'
        is_finished = status.gcode_state in ('FINISH', 'FAILED')

        if is_printing and not self.is_logging:
            self.start_logging(status)
        elif is_finished and self.is_logging:
            # Log the final status before stopping
            self._write_log(status) 
            self.stop_logging()

        # --- Timed Logging during a print ---
        if self.is_logging:
            now = time.time()
            if now - self.last_log_time >= self.log_interval:
                self._write_log(status)
                self.last_log_time = now

    def _write_log(self, status: PrinterStatus):
        """Filters and writes a single status entry to the log file."""
        if not self.is_logging or not self.log_file:
            return

        filtered_data = self._filter_status(asdict(status))
        log_entry = json.dumps(filtered_data)
        self.log_file.write(log_entry + "\n")


def main():
    parser = argparse.ArgumentParser(description="Bambu Lab printer monitoring and notification tool.")
    parser.add_argument("-c", "--config", default="config.yml", help="Path to the configuration file.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable detailed debug logging.")
    args = parser.parse_args()

    # --- Configure Logging ---
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')

    # --- Load Configuration ---
    try:
        with open(args.config, 'r') as f:
            config = yaml.safe_load(f)
    except (FileNotFoundError, yaml.YAMLError) as e:
        log.error(f"Failed to load configuration file '{args.config}': {e}")
        sys.exit(1)

    # --- Initialize Components ---
    bambu_cfg = config.get('bambu_printer', {})
    client = BambuClient(bambu_cfg['hostname'], bambu_cfg['access_code'], bambu_cfg['serial'])
    state_manager = StateManager(config)
    notifier = Notifier(config)
    camera_manager = CameraManager(client)
    print_logger = PrintLogger(config)
    task_queue = queue.Queue()
    shutdown_event = threading.Event()

    # --- Define Callbacks and Workers ---
    def printer_status_callback(status: PrinterStatus):
        percentage_mode = config.get('notifications', {}).get('percentage_mode', 'time')
        
        if percentage_mode == 'layer':
            # Defend against division by zero if total_layer_num is not yet known (e.g., at print start)
            if status.total_layer_num > 0:
                # Calculate layer-based percentage
                new_percent = int((status.layer_num / status.total_layer_num) * 100)
                # Overwrite the time-based percentage on the status object
                # log.debug(f"Overriding time-based percentage ({status.mc_percent}%) with layer-based ({new_percent}%).")
                status.mc_percent = min(new_percent, 100) # Cap at 100%
            else:
                # If we can't calculate, it's very early in the print. Use 0%.
                status.mc_percent = 0

        stage_code = status.mc_print_sub_stage
        status.stage_name = STAGE_DESCRIPTIONS.get(stage_code, f"Unknown Stage ({stage_code})")

        print_logger.process_status(status)

        event = state_manager.process_status(status)
        if event:
            log.debug(f"Queueing notification task for event: {event}")
            task_queue.put((event, status))

    def notification_worker():
        while not shutdown_event.is_set():
            try:
                event, status = task_queue.get(timeout=1)
                
                frame = b""
                if config.get('camera', {}).get('enabled', True):
                    frame = camera_manager.get_frame()
                
                notifier.send(event, status, frame)
                
                # Stop camera if the print is finished/failed
                if event in ('print_finish', 'print_failure'):
                    camera_manager.stop()

                task_queue.task_done()
            except queue.Empty:
                continue

    def on_connect_callback():
        log.info("WatchClient connected to printer. Requesting full status dump.")
        client.dump_info()

    # --- Signal Handler for Graceful Shutdown ---
    def signal_handler(signum, frame):
        log.info("Shutdown signal received. Cleaning up...")
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # --- Start Application ---
        log.info("Starting Bambu Notify...")
        worker_thread = threading.Thread(target=notification_worker, daemon=True)
        worker_thread.start()

        client.start_watch_client(printer_status_callback, on_connect_callback)
        log.info("Application is running. Press Ctrl+C to exit.")
        shutdown_event.wait() # Keep main thread alive until shutdown signal
    
    finally:
        log.info("Shutting down...")
        if worker_thread.is_alive():
            worker_thread.join(timeout=2)

        camera_manager.stop()
        print_logger.stop_logging()
        client.stop_watch_client()
        log.info("Cleanup complete. Exiting.")

if __name__ == '__main__':
    main()
