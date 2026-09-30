from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from .models import XmlMetadata


def local_name(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def extract_xml_payload(path: Path) -> tuple[str, XmlMetadata, str]:
    metadata = XmlMetadata()
    root_name = ""
    try:
        for event, elem in ET.iterparse(path, events=("start", "end")):
            if event == "start" and not root_name:
                root_name = local_name(elem.tag)
                continue

            if event != "end":
                continue

            name = local_name(elem.tag)
            text = (elem.text or "").strip()
            if text:
                if name == "identifier" and not metadata.identifier:
                    metadata.identifier = text
                elif name == "organizationIdentifier" and not metadata.company_name:
                    metadata.company_name = text
                elif name == "accountantName" and not metadata.accountant_name:
                    metadata.accountant_name = text
                elif name == "creator" and not metadata.creator:
                    metadata.creator = text
                elif name == "creationDate" and not metadata.creation_date:
                    metadata.creation_date = text
                elif name == "SigningTime" and not metadata.signing_time:
                    metadata.signing_time = text
                elif name == "periodCoveredStart" and not metadata.period_start:
                    metadata.period_start = text
                elif name == "periodCoveredEnd" and not metadata.period_end:
                    metadata.period_end = text
            elem.clear()
    except Exception as exc:  # noqa: BLE001
        return root_name, metadata, str(exc)
    if not root_name:
        return "", metadata, "Empty XML"
    return root_name, metadata, ""


def read_xml_root_name(path: Path) -> tuple[str, str]:
    root_name, _, error = extract_xml_payload(path)
    return root_name, error


def extract_xml_metadata(path: Path) -> tuple[XmlMetadata, str]:
    _, metadata, error = extract_xml_payload(path)
    return metadata, error
