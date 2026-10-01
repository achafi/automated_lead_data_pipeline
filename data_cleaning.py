"""Optional formatting changes on a separate copy; no validation or enrichment."""
from dataclasses import dataclass

import pandas as pd

NAME_ADDRESS_COLUMNS = ("Business name", "Street", "House number", "City", "Postcode", "Country")
CONTACT_COLUMNS = ("Phone", "Website", "Email")
# Explicit aliases only: unknown countries remain unchanged. Outputs are ISO alpha-2 codes.
COUNTRY_ALIASES = {
    "gb": "GB", "uk": "GB", "united kingdom": "GB", "great britain": "GB",
    "us": "US", "usa": "US", "united states": "US", "united states of america": "US",
    "fr": "FR", "france": "FR", "de": "DE", "germany": "DE", "deutschland": "DE",
    "es": "ES", "spain": "ES", "españa": "ES", "it": "IT", "italy": "IT", "italia": "IT",
    "be": "BE", "belgium": "BE", "belgique": "BE", "belgië": "BE",
    "nl": "NL", "netherlands": "NL", "nederland": "NL",
    "ie": "IE", "ireland": "IE", "pt": "PT", "portugal": "PT",
    "ch": "CH", "switzerland": "CH", "ca": "CA", "canada": "CA",
    "au": "AU", "australia": "AU",
}


@dataclass(frozen=True)
class CleaningOptions:
    name_address_spaces: bool = True
    missing_values: bool = True
    contact_spaces: bool = True
    country_codes: bool = True


def _same_value(left, right):
    if pd.isna(left):
        return bool(pd.isna(right))
    if pd.isna(right):
        return False
    return bool(left == right)


def clean_records(frame, options=CleaningOptions()):
    """Return (cleaned copy, number of changed rows), preserving order and columns."""
    cleaned = frame.copy(deep=True)
    changed_rows = [False] * len(frame)
    for column in frame.columns:
        values = []
        column_changed = False
        for position, value in enumerate(frame[column]):
            new = value
            if options.missing_values and (pd.isna(new) or isinstance(new, str) and not new.strip()):
                new = ""
            if isinstance(new, str):
                if options.name_address_spaces and column in NAME_ADDRESS_COLUMNS:
                    new = " ".join(new.split())
                if options.contact_spaces and column in CONTACT_COLUMNS:
                    new = new.strip()
                if options.country_codes and column == "Country":
                    new = COUNTRY_ALIASES.get(new.strip().casefold(), new)
            if not _same_value(value, new):
                changed_rows[position] = True
                column_changed = True
            values.append(new)
        if column_changed:
            cleaned[column] = pd.Series(values, index=frame.index, dtype=object)
    return cleaned, sum(changed_rows)
