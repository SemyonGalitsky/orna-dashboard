"""Warning-light icons (24x24 stroke SVGs, same as the design)."""

ICONS = {
    "bms": '<rect x="2" y="7" width="18" height="11" rx="2"/><path d="M22 11 V14 M7 12 H11 M15 10 V15"/>',
    "imd": '<path d="M13 2 L4 14 H11 L10 22 L19 10 H12 L13 2 Z"/>',
    "safe": '<path d="M12 2 L20 6 V12 C20 17 16.5 21.5 12 22 C7.5 21.5 4 17 4 12 V6 Z"/><path d="M12 8 V12 M12 16 H12.01"/>',
    "hazard": '<path d="M12 3 L22 20 H2 Z"/><path d="M12 9 L16.5 17 H7.5 Z"/>',
    "motor": '<path d="M14 14.76 V3.5 A2.5 2.5 0 0 0 9 3.5 V14.76 A4.5 4.5 0 1 0 14 14.76 Z"/>',
    "ctrl": '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M9 9 H15 V15 H9 Z"/>',
    "tire": '<circle cx="12" cy="12" r="8"/><path d="M12 8 V13 M12 16 H12.01"/>',
    "link": '<path d="M2 2 L22 22 M8.5 16.5 A5 5 0 0 1 15.5 16.5 M5 13 A10 10 0 0 1 10.17 10.34"/>',
    "data": '<path d="M3 12 H7 L10 5 L14 19 L17 12 H21"/>',
}


def svg(name: str, color: str) -> bytes:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
        f'{ICONS[name]}</svg>'
    ).encode()
