"""The ROS application catalogue.

ROS ships no third-party browser or office suite. These entries are the ROS
applications that replace them: open source upstreams, packaged and presented
under ROS names, with the ROS interface font and ROS defaults.

The names are Kinyarwanda, chosen so that each one says what the application
is for rather than who wrote it. They are paired with a plain English
descriptor, because a tender document and a dock tooltip want different things.

This list seeds the database the first time the console starts. After that the
catalogue belongs to whoever runs the console - editing an entry here will not
overwrite theirs.
"""

from __future__ import annotations

from typing import Any, Dict, List

CATEGORIES = ["Internet", "Office", "Media", "Utilities", "System"]

SEED_CATALOGUE: List[Dict[str, Any]] = [
    {
        "slug": "urubuga",
        "name": "Urubuga",
        "tagline": "Web browser",
        "description": (
            "The ROS browser. Built on Firefox ESR, with telemetry off, ROS "
            "defaults and the ROS interface font."
        ),
        "category": "Internet",
        "upstream": "Firefox ESR",
        "source": "apt",
        "reference": "firefox-esr",
        "desktop_id": "firefox-esr.desktop",
        "icon": "web-browser-symbolic",
    },
    {
        "slug": "inyandiko",
        "name": "Inyandiko",
        "tagline": "Documents",
        "description": (
            "Write and edit documents, including .docx. Built on LibreOffice "
            "Writer."
        ),
        "category": "Office",
        "upstream": "LibreOffice Writer",
        "source": "apt",
        "reference": "libreoffice-writer",
        "desktop_id": "libreoffice-writer.desktop",
        "icon": "x-office-document-symbolic",
    },
    {
        "slug": "imibare",
        "name": "Imibare",
        "tagline": "Spreadsheets",
        "description": (
            "Spreadsheets and calculations, including .xlsx. Built on "
            "LibreOffice Calc."
        ),
        "category": "Office",
        "upstream": "LibreOffice Calc",
        "source": "apt",
        "reference": "libreoffice-calc",
        "desktop_id": "libreoffice-calc.desktop",
        "icon": "x-office-spreadsheet-symbolic",
    },
    {
        "slug": "imurika",
        "name": "Imurika",
        "tagline": "Presentations",
        "description": (
            "Slides and presentations, including .pptx. Built on LibreOffice "
            "Impress."
        ),
        "category": "Office",
        "upstream": "LibreOffice Impress",
        "source": "apt",
        "reference": "libreoffice-impress",
        "desktop_id": "libreoffice-impress.desktop",
        "icon": "x-office-presentation-symbolic",
    },
    {
        "slug": "umusomyi",
        "name": "Umusomyi",
        "tagline": "PDF reader",
        "description": "Read, search and annotate PDFs. Built on Papers.",
        "category": "Office",
        "upstream": "Papers",
        "source": "apt",
        "reference": "papers",
        "desktop_id": "org.gnome.Papers.desktop",
        "icon": "x-office-address-book-symbolic",
    },
    {
        "slug": "ububiko",
        "name": "Ububiko",
        "tagline": "Archives",
        "description": "Open and create zip, tar and 7z archives. Built on File Roller.",
        "category": "Utilities",
        "upstream": "File Roller",
        "source": "apt",
        "reference": "file-roller",
        "desktop_id": "org.gnome.FileRoller.desktop",
        "icon": "package-x-generic-symbolic",
    },
    {
        "slug": "ubutumwa",
        "name": "Ubutumwa",
        "tagline": "Mail",
        "description": "Email, calendar and contacts. Built on Thunderbird.",
        "category": "Internet",
        "upstream": "Thunderbird",
        "source": "apt",
        "reference": "thunderbird",
        "desktop_id": "thunderbird.desktop",
        "icon": "mail-unread-symbolic",
    },
    {
        "slug": "amashusho",
        "name": "Amashusho",
        "tagline": "Photos",
        "description": "View and crop images. Built on Loupe.",
        "category": "Media",
        "upstream": "Loupe",
        "source": "apt",
        "reference": "loupe",
        "desktop_id": "org.gnome.Loupe.desktop",
        "icon": "image-x-generic-symbolic",
    },
    {
        "slug": "injyana",
        "name": "Injyana",
        "tagline": "Media player",
        "description": "Play audio and video. Built on Celluloid and mpv.",
        "category": "Media",
        "upstream": "Celluloid",
        "source": "apt",
        "reference": "celluloid",
        "desktop_id": "io.github.celluloid_player.Celluloid.desktop",
        "icon": "multimedia-player-symbolic",
    },
    {
        "slug": "ikarita",
        "name": "Ikarita",
        "tagline": "Maps",
        "description": "Maps and directions. Built on GNOME Maps.",
        "category": "Utilities",
        "upstream": "GNOME Maps",
        "source": "apt",
        "reference": "gnome-maps",
        "desktop_id": "org.gnome.Maps.desktop",
        "icon": "map-symbolic",
    },
]


def seed() -> List[Dict[str, Any]]:
    return [dict(app) for app in SEED_CATALOGUE]
