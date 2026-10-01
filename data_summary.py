"""Read-only counts of fields present in collected records."""
import pandas as pd


def summarize_records(frame):
    """Return counts and percentages, or None when there are no records."""
    total = len(frame)
    if total == 0:
        return None

    def present(column):
        if column not in frame.columns:
            return pd.Series(False, index=frame.index)
        return frame[column].map(
            lambda value: bool(value.strip()) if isinstance(value, str) else not pd.isna(value)
        )

    contact = present("Website") | present("Phone") | present("Email")
    address = present("Street") & present("City") & present("Postcode")
    return {
        "total": total,
        **{name: {"count": int(mask.sum()), "percentage": float(mask.sum()) / total * 100}
           for name, mask in (("contact", contact), ("website", present("Website")), ("address", address))},
    }
