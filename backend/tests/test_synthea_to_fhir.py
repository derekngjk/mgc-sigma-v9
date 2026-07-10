"""Tests for the Synthea CSV -> FHIR R4B converter (hermetic; uses tmp CSVs)."""

import csv
from pathlib import Path

import pytest

from scripts import synthea_to_fhir as s

PID = "test-uuid-1"


def _write(tmp_path: Path, name: str, header: list[str], rows: list[list[str]]) -> None:
    """Write a CRLF CSV with trailing all-empty padding rows, like the delivered files."""
    with (tmp_path / name).open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\r\n")
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)
        for _ in range(3):  # padding rows: every column blank
            writer.writerow([""] * len(header))


@pytest.fixture
def synthea_dir(tmp_path: Path) -> Path:
    _write(
        tmp_path,
        "patients.csv",
        ["Id", "BIRTHDATE", "DEATHDATE", "NRIC", "PREFIX", "FULL NAME", "LAST",
         "FIRST", "SUFFIX", "MARITAL", "RACE", "NATIONALITY", "GENDER",
         "ADDRESS", "POSTALCODE"],
        [[PID, "2/6/1992", "", "S6090453C", "Mr.", "Aaron Teo", "Teo", "Aaron",
          "", "M", "Chinese", "Singaporean", "M", "addr", "123"]],
    )
    _write(
        tmp_path,
        "conditions.csv",
        ["START", "STOP", "PATIENT", "ENCOUNTER", "CODE", "DESCRIPTION"],
        [
            ["11/8/2011", "1/9/2011", PID, "enc1", "444814009", "Viral sinusitis (disorder)"],
            ["1/5/2001", "", PID, "enc2", "40055000", "Chronic sinusitis (disorder)"],
            ["1/1/2000", "2/2/2000", "other-pid", "enc3", "10509002", "Acute bronchitis (disorder)"],
        ],
    )
    _write(
        tmp_path,
        "careplans.csv",
        ["Id", "START", "STOP", "PATIENT", "ENCOUNTER", "CODE", "DESCRIPTION",
         "REASONCODE", "REASONDESCRIPTION"],
        [["cp1", "22/1/2017", "12/2/2017", PID, "enc4", "225358003", "Wound care",
          "284551006", "Laceration of foot"]],
    )
    _write(
        tmp_path,
        "observations.csv",
        ["DATE", "PATIENT", "ENCOUNTER", "CODE", "DESCRIPTION", "VALUE", "UNITS", "TYPE"],
        [["2012-01-23T17:45:28Z", PID, "enc5", "8302-2", "Body Height", "193.3", "cm", "numeric"]],
    )
    return tmp_path


def test_build_patient_bundle_happy(synthea_dir: Path) -> None:
    bundle = s.build_patient_bundle(PID, base_dir=synthea_dir)

    patient = bundle["patient"]
    assert patient["id"] == PID
    assert patient["name"][0]["text"] == "Aaron Teo"
    assert patient["birthDate"] == "1992-06-02"
    assert patient["gender"] == "male"
    assert patient["identifier"][0]["value"] == "S6090453C"

    conditions = [e["resource"] for e in bundle["conditions"]["entry"]]
    assert len(conditions) == 2  # the other-pid row is excluded
    by_code = {c["code"]["coding"][0]["code"]: c for c in conditions}
    # Faithful clinical status: STOP present -> resolved, STOP empty -> active.
    assert by_code["444814009"]["clinicalStatus"]["coding"][0]["code"] == "resolved"
    assert by_code["40055000"]["clinicalStatus"]["coding"][0]["code"] == "active"
    assert by_code["444814009"]["code"]["coding"][0]["system"] == s.SNOMED_SYSTEM
    assert by_code["444814009"]["subject"]["reference"] == f"Patient/{PID}"

    care_plans = [e["resource"] for e in bundle["care_plans"]["entry"]]
    assert len(care_plans) == 1
    assert care_plans[0]["status"] == "completed"  # has STOP
    assert "Laceration of foot" in care_plans[0]["description"]


def test_dates_padding_and_missing_patient(synthea_dir: Path) -> None:
    assert s._to_iso_date("14/11/1983") == "1983-11-14"
    assert s._to_iso_date("") == ""
    assert s._to_iso_date("not-a-date") == "not-a-date"
    # Padding rows must not create phantom patients.
    with pytest.raises(KeyError):
        s.build_patient_bundle("does-not-exist", base_dir=synthea_dir)
