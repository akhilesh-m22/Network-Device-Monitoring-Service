"""Helper functions: input validation and the ping-based reachability check.

No user input is ever used to build a shell command: ``ping`` is always
called with a fixed argument list (no ``shell=True``), so a crafted device
name or IP cannot execute arbitrary commands on the host.
"""

import ipaddress
import platform
import re
import subprocess
import time

# Rough pattern for a hostname label (letters, digits, hyphens).
_HOSTNAME_LABEL_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")

# A string of dot-separated numbers that is meant to be an IP address.
_DOTTED_NUMBERS_RE = re.compile(r"^\d{1,3}(\.\d{1,3})+$")


def validate_ip_or_hostname(value):
    """Return the normalized value if valid, otherwise raise ValueError.

    Accepts IPv4 addresses and hostnames (e.g. ``192.168.1.10`` or
    ``router.home.local``). IPv6 is rejected because the ping command used
    here only targets IPv4/hostnames, which keeps the code simple.
    """
    if not value or not isinstance(value, str):
        raise ValueError("IP address or hostname is required.")

    value = value.strip()
    if not value:
        raise ValueError("IP address or hostname cannot be empty.")

    # Try to parse it as an IP address first.
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError:
        parsed = None

    if parsed is not None:
        if parsed.version == 6:
            raise ValueError("IPv6 addresses are not supported; use IPv4 or a hostname.")
        return parsed.compressed

    # Strings that look like an IP address (all dot-separated numbers) but
    # failed to parse contain out-of-range numbers - reject them instead of
    # treating them as hostnames.
    if _DOTTED_NUMBERS_RE.match(value):
        raise ValueError(
            "Invalid IP address: octets must be numbers between 0 and 255."
        )

    # Otherwise treat it as a hostname and validate the format.
    if not validate_hostname(value):
        raise ValueError(
            "Invalid IP address or hostname. Use e.g. 192.168.1.10 or my-server.local"
        )
    return value


def validate_hostname(hostname):
    """Return True if the string looks like a valid hostname."""
    if len(hostname) > 253:
        return False
    labels = hostname.rstrip(".").split(".")
    if not labels:
        return False
    return all(_HOSTNAME_LABEL_RE.match(label) for label in labels)


def ping_device(host, timeout=3):
    """Ping a host once and return (reachable, response_time_ms).

    ``reachable`` is True/False and ``response_time_ms`` is the round-trip
    time in milliseconds (or None when the ping failed).

    Uses ``subprocess.run`` with a fixed command line so there is no shell
    involved. The timeout prevents a slow device from blocking the monitor.
    """
    system = platform.system()
    if system == "Windows":
        # -n 1: one ping, -w: timeout in milliseconds
        command = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), host]
    elif system == "Darwin":
        # macOS/BSD: -W timeout is in milliseconds
        command = ["ping", "-c", "1", "-W", str(int(timeout * 1000)), host]
    else:
        # Linux: -W timeout is in seconds
        command = ["ping", "-c", "1", "-W", str(int(timeout)), host]

    start = time.perf_counter()
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout + 2,
        )
    except (subprocess.TimeoutExpired, OSError):
        # Ping did not finish in time or the command could not be started.
        return False, None

    elapsed_ms = (time.perf_counter() - start) * 1000

    if result.returncode != 0:
        return False, None

    parsed_time = parse_ping_time(result.stdout)
    if parsed_time is not None:
        return True, round(parsed_time, 2)

    # Fallback: no time reported by ping, use our own measurement.
    return True, round(elapsed_ms, 2)


def parse_ping_time(ping_output):
    """Extract the round-trip time in ms from a ping response.

    Matches both Windows output (``time=14ms`` or ``time<1ms``) and
    Linux/macOS output (``time=14.1 ms``). Returns None if not found.
    """
    match = re.search(r"time[=<]\s*([\d.]+)", ping_output)
    if match is None:
        return None
    return float(match.group(1))
