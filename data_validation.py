"""Local format checks on populated values; never change or enrich source records."""
import ipaddress
import math
import re
from urllib.parse import urlsplit

import pandas as pd

REPORT_COLUMNS = ["Record identifier", "Field", "Value", "Issue type", "Issue"]


def is_missing(value):
    return not value.strip() if isinstance(value, str) else value is None or bool(pd.isna(value))


def _valid_host(host):
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return False
    labels = host.rstrip(".").split(".")
    return len(labels) >= 2 and len(host) <= 253 and all(
        re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) for label in labels)


def valid_email(value):
    """Practical single-address check, not a full RFC or deliverability check."""
    if not isinstance(value, str) or not re.fullmatch(r"[^@\s]+@[^@\s]+", value):
        return False
    local, domain = value.split("@")
    return (len(local) <= 64 and len(value) <= 254 and not local.startswith(".")
            and not local.endswith(".") and ".." not in local
            and bool(re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+", local))
            and _valid_host(domain))


def valid_website(value):
    """Accept HTTP(S) URLs or bare domains; no network calls."""
    if not isinstance(value, str) or not value or re.search(r"\s|\\", value):
        return False
    try:
        parsed = urlsplit(value if "://" in value or value.startswith("//") else "//" + value)
        if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
            return False
        if parsed.username is not None or parsed.password is not None:
            return False
        port = parsed.port  # Access validates the port format and range.
        return bool(parsed.hostname and _valid_host(parsed.hostname) and (port is None or port > 0))
    except ValueError:
        return False


def valid_phone(value):
    """Basic single-number format check, not country-specific or reachability validation."""
    if not isinstance(value, str):
        return False
    number = re.sub(r"\s*(?:ext\.?|x|#)\s*[0-9]{1,6}$", "", value.strip(), flags=re.IGNORECASE).strip()
    if not re.fullmatch(r"\+?[0-9 ()\-.]+", number):
        return False
    if number.count("(") != number.count(")") or number.count("(") > 1:
        return False
    if "(" in number and number.index("(") > number.index(")"):
        return False
    return 7 <= len(re.sub(r"[^0-9]", "", number)) <= 15


def validate_records(frame, record_ids=None):
    """One report row per field issue, retaining IDs from original search order."""
    ids = list(record_ids) if record_ids is not None else [f"R{i+1:04d}" for i in range(len(frame))]
    if len(ids) != len(frame) or len(set(ids)) != len(ids):
        raise ValueError("Validation requires one unique record identifier per row.")
    issues = []
    for position, ident in enumerate(ids):
        record = frame.iloc[position].to_dict()
        def flag(field, kind, reason):
            value = record.get(field)
            issues.append([ident, field, "" if is_missing(value) else str(value), kind, reason])
        for field, limit in (("Latitude", 90), ("Longitude", 180)):
            value = record.get(field)
            if is_missing(value):
                continue
            try:
                number = float(value)
                if isinstance(value, bool) or not math.isfinite(number):
                    raise ValueError
            except (ValueError, TypeError, OverflowError):
                flag(field, "Invalid", "Coordinate must be a finite number")
                continue
            if not -limit <= number <= limit:
                flag(field, "Invalid", f"Outside the valid range {-limit} to {limit}")
        for field, checker, message in (
            ("Email", valid_email, "Invalid single-email format"),
            ("Website", valid_website, "Invalid website format; use an HTTP(S) URL or usable domain"),
            ("Phone", valid_phone, "Invalid single-phone format; expected 7–15 digits with optional formatting or extension"),
        ):
            value = record.get(field)
            if not is_missing(value) and not checker(value):
                flag(field, "Invalid", message)
    return pd.DataFrame(issues, columns=REPORT_COLUMNS)


def issue_counts(report):
    if report.empty:
        return pd.DataFrame(columns=["Field", "Issue type", "Records affected"])
    return report.groupby(["Field", "Issue type"], sort=False)["Record identifier"].nunique().reset_index(name="Records affected")
