# Bambu-Notify

A powerful, customizable notification and logging tool for your Bambu Lab 3D printer. Get real-time updates with camera snapshots on Discord, and dive deep into your printer's activity with an advanced log analyzer.

![Example Notification](https://github.com/kloptops/Bambu-Notify/blob/main/resources/screenshot.png)

## ✨ Features

- **Granular Event Notifications:** Get alerts for the *exact* moment a print phase begins or ends:
  - **Start Events:** Choose to be notified at the start of the print *process*, the beginning of *calibration*, or the moment *extrusion* begins (best for camera shots!).
  - **End Events:** Get a notification the moment the print *physically finishes* (before the bed lowers) or when the entire *process is complete*.
  - Standard alerts for Failure, Pause, and Resume.
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

3.  **Install Dependencies:**

    Create a file named `requirements.txt` in the project root with the exact content below. This is crucial for installing the correct libraries.

    ```
    # requirements.txt

    # Standard libraries from PyPI
    pyyaml
    jinja2
    requests

    # Custom dependency from a GitHub fork
    git+https://github.com/kloptops/bambu-connect.git
    ```

    > **📌 Important Note:** This project relies on a specific fork of the `bambu-connect` library to support all its features. The line `git+https://...` in the requirements file directs `pip` to install this specific version from GitHub instead of the standard version from PyPI.

    Now, run the installation command from your terminal:
    ```bash
    pip install -r requirements.txt
    ```

## 🔧 Configuration

All settings are managed in a single `config.yml` file.

1.  **Copy the example configuration:**
    ```bash
    cp config.yml.example config.yml
    ```

2.  **Edit `config.yml`** with your printer details, webhook URLs, and desired notification settings.

### Bambu Printer Details
```yaml
bambu_printer:                     # On the devices LCD.
  hostname: "192.168.1.100"        # From Settings -> WLAN -> IP Address
  access_code: "12345678"          # From Settings -> WLAN -> Access Code
  serial: "00M00A000000000"        # From Settings -> Device -> "Printer"
```

### Notification Settings
This section controls what you get notified about and how.

```yaml
notifications:
  webhooks:
    - "https://discord.com/api/webhooks/your_webhook_id/your_webhook_token"

  # --- Event Triggers ---
  # Defines which event triggers the "Print Start" notification.
  # 'off', 'process_start', 'print_begin' (default), 'extrusion_start'
  report_start_event: "print_begin"

  # Defines which event triggers the "Print Finish" notification.
  # 'off', 'print_end' (default), 'process_end'
  report_finish_event: "print_end"

  # ... other triggers ...
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

All notification messages are generated from the `messages.jinja` file. You can edit the text, add emojis, or rearrange information to your liking using the variables documented in the `README.md` and `bambu_defs.py`.

## ❤️ Contributing

Contributions are welcome! If you have a feature idea, find a bug, or want to improve the documentation, please feel free to open an issue or submit a pull request.

--

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

```bash
# Watch for changes in 'stg_cur' and 'mc_print_sub_stage'
python3 log-analyzer.py print_logs/your_log.log --watch stg_cur --watch mc_print_sub_stage
```

## 📜 License

This project is licensed under the [MIT License](LICENSE).
