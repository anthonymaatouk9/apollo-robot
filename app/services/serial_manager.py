import serial
import threading
import time
import queue
import logging
from config import Config

logger = logging.getLogger(__name__)


class SerialManager:
    """
    Manages serial communication between Raspberry Pi and Arduino.

    Commands sent TO Arduino:
      ROTATE_TUBE:n     — rotate stepper to tube n (1-4)
      DISPENSE_PILL     — drop one pill via servo
      DISPENSE_CUP      — drop one cup via servo
      FILL_WATER:n      — fill n milliliters of water
      RESET_TUBE        — rotate stepper back to home position
      PING              — check if Arduino is alive

    Events received FROM Arduino:
      ACK:COMMAND       — command received and executing
      PILL_CONFIRMED    — IR sensor detected pill drop
      WATER_DONE        — water fill complete
      CUP_OK            — cup dispensed successfully
      HOME_OK           — stepper reset to home
      EVT:BATTERY:n     — battery percentage update
      EVT:LOW_WATER     — water tank low
      ERR:REASON        — error with reason
    """

    def __init__(self):
        self.port        = Config.SERIAL_PORT
        self.baud        = Config.SERIAL_BAUD
        self.ser         = None
        self.connected   = False
        self.lock        = threading.Lock()
        self.event_queue = queue.Queue()
        self._listener   = None

    def connect(self):
        """Open serial connection to Arduino."""
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baud,
                timeout=1
            )
            time.sleep(2)  # wait for Arduino to reset after serial connect
            self.connected = True
            self._start_listener()
            logger.info(f"Serial connected on {self.port} at {self.baud} baud")
            return True
        except Exception as e:
            logger.error(f"Serial connect failed: {e}")
            self.connected = False
            return False

    def disconnect(self):
        """Close serial connection."""
        self.connected = False
        if self.ser and self.ser.is_open:
            self.ser.close()
        logger.info("Serial disconnected")

    def send_command(self, command, timeout=5):
        """
        Send a command to Arduino and wait for ACK or ERR.
        Returns (success: bool, response: str)

        Example:
            ok, resp = serial_manager.send_command("DISPENSE_PILL")
            ok, resp = serial_manager.send_command("ROTATE_TUBE:2")
            ok, resp = serial_manager.send_command("FILL_WATER:150")
        """
        if not self.connected:
            logger.warning("Serial not connected — command skipped")
            return False, "ERR:NOT_CONNECTED"

        with self.lock:
            try:
                # Clear any leftover data in buffer
                self.ser.reset_input_buffer()

                # Send command with newline terminator
                msg = f"{command}\n"
                self.ser.write(msg.encode("utf-8"))
                logger.info(f"SENT: {command}")

                # Wait for response line
                deadline = time.time() + timeout
                while time.time() < deadline:
                    if self.ser.in_waiting:
                        line = self.ser.readline().decode("utf-8").strip()
                        if not line:
                            continue
                        logger.info(f"RECV: {line}")

                        # Put events in queue for background processing
                        if line.startswith("EVT:"):
                            self.event_queue.put(line)
                            continue

                        # Return ACK or ERR as the command response
                        if line.startswith("ACK:") or line.startswith("ERR:"):
                            return not line.startswith("ERR:"), line

                        # Return specific confirmations
                        if line in ("PILL_CONFIRMED", "WATER_DONE", "CUP_OK", "HOME_OK"):
                            return True, line

                    time.sleep(0.05)

                logger.warning(f"Timeout waiting for response to: {command}")
                return False, "ERR:TIMEOUT"

            except Exception as e:
                logger.error(f"Serial send error: {e}")
                return False, f"ERR:{str(e)}"

    def wait_for_event(self, expected_event, timeout=10):
        """
        Wait for a specific event from Arduino after a command.
        Used when command has a delayed confirmation (e.g. IR sensor).

        Example:
            ok, evt = serial_manager.wait_for_event("PILL_CONFIRMED", timeout=5)
        """
        if not self.connected:
            return False, "ERR:NOT_CONNECTED"

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                line = self.ser.readline().decode("utf-8").strip()
                if not line:
                    continue
                logger.info(f"EVENT: {line}")
                if line.startswith("EVT:"):
                    self.event_queue.put(line)
                if line == expected_event:
                    return True, line
                if line.startswith("ERR:"):
                    return False, line
            except Exception as e:
                return False, f"ERR:{str(e)}"
            time.sleep(0.05)

        return False, "ERR:TIMEOUT"

    def _start_listener(self):
        """Background thread that reads unsolicited events from Arduino."""
        self._listener = threading.Thread(target=self._listen_loop, daemon=True)
        self._listener.start()

    def _listen_loop(self):
        """Continuously read serial and put events in queue."""
        while self.connected:
            try:
                if self.ser and self.ser.in_waiting:
                    line = self.ser.readline().decode("utf-8").strip()
                    if line:
                        logger.info(f"ASYNC: {line}")
                        self.event_queue.put(line)
            except Exception as e:
                logger.error(f"Listener error: {e}")
                break
            time.sleep(0.05)

    def is_connected(self):
        return self.connected and self.ser and self.ser.is_open

    def ping(self):
        """Check if Arduino is responsive."""
        ok, resp = self.send_command("PING", timeout=3)
        return ok


# Global instance — imported by routes
serial_manager = SerialManager()
