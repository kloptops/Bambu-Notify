# Bambu-Notify

A powerful, customizable notification and logging tool for your Bambu Lab 3D printer. Get real-time updates with camera snapshots on Discord, and dive deep into your printer's activity with an advanced log analyzer.


![Example Notification](https://github.com/kloptops/Bambu-Notify/blob/main/resources/screenshot.png)

## ✨ Features

- **Event-Driven Notifications:** Get alerts for key events:
  - Print Start, Finish, Failure, Pause, and Resume.
- **Rich Progress Reporting:**
  - Receive updates at configurable percentage milestones (e.g., 25%, 50%, 75%).
  - Get special notifications after the first and/or second layers complete.
- **Camera Snapshots:** Automatically attach a live camera frame to your notifications.
- **Flexible Percentage Calculation:** Choose between the printer's time-based estimate or a more accurate layer-based percentage.
- **Detailed Print Logging:** Optionally save a detailed log of every print job, capturing every status update for analysis.
- **Powerful Log Analyzer:** Use a dedicated script to analyze print logs, diff changes between states, and watch for specific value changes to understand your printer's behavior.
- **Highly Customizable Messages:** All notification messages are controlled via a simple-to-edit [Jinja2](https://jinja.palletsprojects.com/) template.

## ⚙️ How It Works

This script connects to your Bambu Lab printer over your local network via its built-in MQTT service. It listens for real-time status messages, processes them through a state machine to decide when to send a notification, captures a frame from the camera stream, and sends a formatted message to your configured webhooks.

## 🚀 Getting Started

### Prerequisites

- Python 3.9+
- A Bambu Lab printer (P1P, P1S, X1C, etc.) accessible on your local network.

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/bambu-notify.git
    cd bambu-notify
    ```

2.  **Create and activate a virtual environment (recommended):**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    # On Windows, use: venv\Scripts\activate
    ```

3.  **Install the required packages:**
    ```bash
    pip install -r requirements.txt
    ```

    *(You will need to create a `requirements.txt` file containing `requests`, `pyyaml`, `jinja2`, and `bambu-connect`)*

## 🔧 Configuration

All settings are managed in a single `config.yml` file.

1.  **Copy the example configuration:**
    ```bash
    cp config.yml.example config.yml
    ```

2.  **Edit `config.yml`** with your favorite text editor.

### Bambu Printer Details
You need to provide your printer's IP address, access code, and serial number.

```yaml
bambu_printer:
  hostname: "192.168.1.100"       # IP address of your printer
  access_code: "12345678"          # Access code from the printer's screen
  serial: "00M00A000000000"        # Serial number of your printer
```
-   **`hostname`**: Your printer's IP address. You can find this in your router's device list or on the printer's network settings screen.
-   **`access_code`**: Found on the printer's screen under `Settings -> Network`.
-   **`serial`**: Found on a label on the back of the printer or in the device info screen.

### Notification Settings
This section controls what you get notified about and how.

```yaml
notifications:
  # A list of Discord webhook URLs.
  webhooks:
    - "https://discord.com/api/webhooks/your_webhook_id/your_webhook_token"

  # How to calculate print completion percentage.
  # 'time' (default) or 'layer'
  percentage_mode: "layer"

  # --- Event Triggers (true/false) ---
  report_start: true
  report_finish: true
  report_failure: true
  report_pause: true
  report_resume: true
  
  report_first_layer: true
  report_second_layer: false

  # Send a progress report when these percentages are reached.
  report_percentages:
    - 25
    - 50
    - 75
```
-   **`webhooks`**: A list of one or more Discord webhook URLs. [How to create a Discord Webhook](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks).
-   **`percentage_mode`**: Use `'time'` for the printer's estimate or `'layer'` for a more accurate physical progress calculation (`current_layer / total_layers`).

### Print Log Settings
Enable this to save detailed logs for every print, which can be analyzed with the `log-analyzer.py` tool.

```yaml
print_log:
  enabled: true                    # Set to true to enable logging prints.
  log_directory: "print_logs"      # Directory to save the log files.
  log_interval_seconds: 15         # How often to write a status update to the log.
```

## ▶️ Running the Script

Once configured, simply run the main script from your terminal:

```bash
python3 bambu-notify.py
```

The script will run continuously in the background. To see more detailed output for debugging, use the `--verbose` or `-v` flag:

```bash
python3 bambu-notify.py --verbose
```

Press `Ctrl+C` to stop the script gracefully.

## 🎨 Customizing Notifications

All notification messages are generated from the `messages.jinja` file. You can edit the text, add emojis, or rearrange information to your liking.

The following variables are available inside the template:

-   `event`: The name of the event that triggered the notification (e.g., `'print_start'`).
-   `print`: The full `PrinterStatus` object, giving you access to all data from the printer. Key attributes include:
    -   `print.subtask_name`: The name of the G-code file.
    -   `print.mc_percent`: The completion percentage.
    -   `print.mc_remaining_time`: Estimated time remaining in minutes.
    -   `print.layer_num` / `print.total_layer_num`: Current and total layer counts.
    -   `print.stage_name`: A human-readable description of the printer's current activity (e.g., "Auto bed leveling", "Printing", "Paused due to filament runout").

A helper function is also available:
-   `format_time(minutes)`: Formats an integer of minutes into a friendly string (e.g., "1 hour and 25 minutes").

## ❤️ Contributing

Contributions are welcome! If you have a feature idea, find a bug, or want to improve the documentation, please feel free to open an issue or submit a pull request.

## 🔬 Advanced Tool: Log Analyzer

If you have `print_log` enabled, you can use the `log-analyzer.py` script to inspect the generated log files. This is incredibly useful for debugging or understanding the printer's internal state machine.

### Standard Diff Mode

Shows a running list of every value that changes between log entries.

```bash
# Basic usage
python3 log-analyzer.py print_logs/your_print_log_file.log

# Ignore noisy values like temperature fluctuations
python3 log-analyzer.py print_logs/your_log.log --tolerance bed_temper:1.0 --tolerance nozzle_temper:1.0
```

### Watch Mode

Pinpoint what happens when a specific value changes. The analyzer will only print output when a "watched" key changes, showing the entries immediately before and after the event.

This is perfect for figuring out what mysterious values like `stg_cur` mean.

```bash
# Watch for changes in 'stg_cur' and show 3 log entries of context
python3 log-analyzer.py print_logs/your_log.log --watch stg_cur --context 3
```

## 📜 License

This project is licensed under the MIT License. See the `LICENSE` file for details.