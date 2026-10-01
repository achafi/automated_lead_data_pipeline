"""Copy agreed values within explicitly confirmed duplicate groups only."""
import pandas as pd

from duplicate_review import COLUMN_MAPPING, USEFUL_FIELDS, _validate_groups, is_populated, record_identifier
from data_validation import valid_email, valid_phone, valid_website

FILL_FIELDS = tuple(COLUMN_MAPPING[key] for key in USEFUL_FIELDS)
PROPOSAL_COLUMNS = ["Group", "Target record", "Field", "Value", "Source records", "Status", "Reason"]
CHECKERS = {"Phone": valid_phone, "Website": valid_website, "Email": valid_email}


def complete_records(original, groups, confirmed_groups, positions=None):
    """Return a separate completed copy and provenance/skip report.

    Positions select original or explicitly retained rows; donors always come from
    the original group, including excluded rows. Exact-value agreement is required.
    Nothing is copied between groups or from an unconfirmed group.
    """
    _validate_groups(original, groups)
    confirmed = set(confirmed_groups)
    if any(type(i) is not int or not 0 <= i < len(groups) for i in confirmed):
        raise ValueError("Confirm only existing duplicate groups.")
    positions = list(range(len(original))) if positions is None else list(positions)
    if (len(set(positions)) != len(positions) or any(type(i) is not int or not 0 <= i < len(original) for i in positions)):
        raise ValueError("Completion requires unique original row positions.")
    result = original.iloc[positions].copy(deep=True)
    targets = {position: offset for offset, position in enumerate(positions)}
    proposals = []
    for number in sorted(confirmed):
        group = groups[number]
        for field in FILL_FIELDS:
            if field not in original.columns:
                continue
            donors = [(i, original.iloc[i][field]) for i in group if is_populated(original.iloc[i][field])]
            if not donors:
                continue
            first = donors[0][1]
            conflict = any(value != first for _, value in donors[1:])
            invalid = not conflict and field in CHECKERS and not CHECKERS[field](first)
            for position in group:
                if position not in targets or is_populated(original.iloc[position][field]):
                    continue
                status = "Skipped" if conflict or invalid else "Ready to fill"
                reason = ("Conflicting values — manual review needed" if conflict else
                          "Source value fails the format check" if invalid else "All populated source values agree exactly")
                value = " | ".join(dict.fromkeys(str(value) for _, value in donors))
                proposals.append([number + 1, record_identifier(position), field, value,
                                  ", ".join(record_identifier(i) for i, _ in donors), status, reason])
                if not conflict and not invalid:
                    if result[field].dtype != object:
                        result[field] = result[field].astype(object)
                    result.iat[targets[position], result.columns.get_loc(field)] = first
    return result, pd.DataFrame(proposals, columns=PROPOSAL_COLUMNS)


def deduplicate_and_complete(original, groups, decisions):
    """A decision to retain one row also authorizes agreed missing-field fills."""
    from duplicate_review import apply_duplicate_decisions, KEEP_RECOMMENDED, KEEP_SPECIFIC
    retained = apply_duplicate_decisions(original.reset_index(drop=True), groups, decisions)
    authorized = [number for number in range(len(groups))
                  if decisions.get(number, {}).get("action") in (KEEP_RECOMMENDED, KEEP_SPECIFIC)]
    result, report = complete_records(original, groups, authorized, retained.index.tolist())
    report.loc[report["Status"] == "Ready to fill", "Status"] = "Filled"
    return result, report
