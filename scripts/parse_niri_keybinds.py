#!/usr/bin/env python3
"""
Parse niri config.kdl to extract keybinds for ii cheatsheet.
Outputs JSON with categorized keybinds.
"""

import json
import os
import re
import sys
from pathlib import Path


def get_niri_config_path():
    """Get the path to niri config, checking XDG and fallback."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return Path(xdg_config) / "niri" / "config.kdl"


def parse_keybinds_from_block(binds_content: str) -> list[dict]:
    """Parse keybinds handling both single-line and multi-line formats."""
    keybinds = []
    lines = binds_content.split('\n')
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip empty lines and comments
        if not line or line.startswith('//'):
            i += 1
            continue
        
        # Match keybind start: KEY_COMBO [options] { [action] }
        # Single line: Mod+Tab repeat=false { toggle-overview; }
        # Multi line: Alt+Tab { \n spawn ...; \n }
        
        match = re.match(r'^([A-Za-z0-9+_]+)\s*(.*?)(\{.*)$', line)
        if not match:
            i += 1
            continue
        
        key_combo = match.group(1)
        options = match.group(2).strip()
        rest = match.group(3)
        
        # Extract hotkey-overlay-title if present
        title_match = re.search(r'hotkey-overlay-title=("(?:\\.|[^"\\])*")', options)
        overlay_title = json.loads(title_match.group(1)) if title_match else None
        
        # Check if action is on same line or spans multiple lines
        if re.search(r'\{[^}]+\}', rest):
            # Single line - action is complete
            action_match = re.search(r'\{\s*(.*)\s*\}', rest)
            action = action_match.group(1).strip().rstrip(';') if action_match else ''
        else:
            # Multi-line - collect until closing brace
            action_lines = []
            i += 1
            while i < len(lines):
                inner_line = lines[i].strip()
                if inner_line == '}':
                    break
                if inner_line and not inner_line.startswith('//'):
                    action_lines.append(inner_line.rstrip(';'))
                i += 1
            action = ' '.join(action_lines)
        
        # Parse key combo
        parts = key_combo.split('+')
        mods = []
        key = parts[-1]
        
        for part in parts[:-1]:
            if part in ('Mod', 'Super'):
                mods.append('Super')
            elif part in ('Alt', 'Shift', 'Ctrl'):
                mods.append(part)
            else:
                mods.append(part)
        
        # Handle XF86 keys
        if key.startswith('XF86Audio'):
            key = key.replace('XF86Audio', '').replace('RaiseVolume', 'Vol+').replace('LowerVolume', 'Vol-')
        elif key.startswith('XF86MonBrightness'):
            key = key.replace('XF86MonBrightness', 'Brightness').replace('Up', '+').replace('Down', '-')
        elif key.startswith('XF86'):
            key = key.replace('XF86', '')
        
        # Generate comment - prefer overlay title
        comment = overlay_title if overlay_title else generate_comment(action)
        
        keybinds.append({
            'mods': mods,
            'key': key,
            'action': action,
            'comment': comment
        })
        
        i += 1
    
    return keybinds


# Share descriptions/categories with the editable Settings model.
import importlib.util
_spec = importlib.util.spec_from_file_location("inir_bind_metadata", Path(__file__).with_name("niri-config.py"))
_metadata = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_metadata)


def generate_comment(action: str) -> str:
    return _metadata._kb_generate_comment(action)


def categorize_keybind(kb: dict) -> str:
    action = kb.get("action", "")
    return _metadata._kb_categorize(generate_comment(action), action)


def find_all_binds_blocks(content: str) -> tuple[list[str], list[str]]:
    """Every top-level `binds { }` in file order, and the `binds { }` inside `recent-windows { }`."""
    text = '\n'.join('' if line.lstrip().startswith('//') else line for line in content.split('\n'))
    normal, recent = [], []
    depth = 0
    parents = []
    i = 0
    header = re.compile(r'([A-Za-z0-9_-]+)\s*\{')
    while i < len(text):
        ch = text[i]
        if ch == '{':
            name = ''
            for back in range(i - 1, max(-1, i - 64), -1):
                m = header.match(text, back)
                if m and m.end() == i + 1:
                    name = m.group(1)
                elif name:
                    break
            if name == 'binds' and depth == 0:
                end = _block_end(text, i + 1)
                normal.append(text[i + 1:end])
                i = end + 1
                continue
            if name == 'binds' and depth == 1 and parents and parents[-1] == 'recent-windows':
                end = _block_end(text, i + 1)
                recent.append(text[i + 1:end])
                i = end + 1
                continue
            parents.append(name)
            depth += 1
        elif ch == '}':
            depth = max(0, depth - 1)
            if parents:
                parents.pop()
        i += 1
    return normal, recent


def _block_end(text: str, start: int) -> int:
    depth = 1
    i = start
    while i < len(text) and depth > 0:
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
        i += 1
    return i - 1


def resolve_includes(content: str, config_dir: Path) -> str:
    """Resolve include directives by inlining included file contents."""
    def replace_include(match):
        rel_path = match.group(1)
        include_path = config_dir / rel_path
        if include_path.exists():
            return include_path.read_text()
        return ''
    return re.sub(r'^include\s+"([^"]+)"\s*$', replace_include, content, flags=re.MULTILINE)


def parse_niri_config(config_path: Path) -> dict:
    """Parse the niri config and extract keybinds."""
    if not config_path.exists():
        return {'error': f'Config not found: {config_path}', 'children': []}
    
    content = config_path.read_text()
    content = resolve_includes(content, config_path.parent)
    normal_blocks, recent_blocks = find_all_binds_blocks(content)
    if not normal_blocks and not recent_blocks:
        return {'error': 'No binds block found', 'children': []}

    # Niri: a later binds block overrides an earlier one on the same keys, and recent-windows
    # binds only work where no normal bind takes the key.
    merged = {}
    for block in normal_blocks:
        for kb in parse_keybinds_from_block(block):
            merged[(tuple(kb['mods']), kb['key'])] = kb
    for block in recent_blocks:
        for kb in parse_keybinds_from_block(block):
            merged.setdefault((tuple(kb['mods']), kb['key']), kb)
    # A personal disabled override suppresses the inherited action, not just
    # the UI row. Filter only after merging so the upstream row stays hidden.
    keybinds = [kb for kb in merged.values()
                if kb.get('action', '').strip('; ') != 'spawn "/usr/bin/true"']
    keybinds_by_category = {}
    
    for kb in keybinds:
        category = categorize_keybind(kb)
        if category not in keybinds_by_category:
            keybinds_by_category[category] = []
        keybinds_by_category[category].append({
            'mods': kb['mods'],
            'key': kb['key'],
            'comment': kb['comment']
        })
    
    category_order = [
        'System', 'iNiR Shell', 'Window Switcher', 'Screenshots',
        'Applications', 'Window Management', 'Layout', 'Resize',
        'Focus', 'Move Windows', 'Monitors', 'Workspaces',
        'Media', 'Brightness', 'Other'
    ]
    
    children = []
    for cat in category_order:
        if cat in keybinds_by_category and keybinds_by_category[cat]:
            children.append({
                'name': cat,
                'children': [{'keybinds': keybinds_by_category[cat]}]
            })
    
    return {'children': children, 'configPath': str(config_path)}


def main():
    config_path = get_niri_config_path()
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])
    
    result = parse_niri_config(config_path)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
