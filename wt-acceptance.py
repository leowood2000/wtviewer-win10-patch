import csv
import ctypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import win32con
import win32gui
import win32process


exe = Path(sys.argv[1]).resolve()
process = subprocess.Popen([str(exe)], cwd=exe.parent)
try:
    handled = set()
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        windows = []
        def remember(window, _):
            if win32process.GetWindowThreadProcessId(window)[1] == process.pid and win32gui.IsWindowVisible(window):
                windows.append((window, win32gui.GetWindowText(window)))
        win32gui.EnumWindows(remember, None)
        numeric = [window for window, title in windows if title.startswith('WTViewer - Numeric')]
        if len(numeric) == 1 and win32gui.IsWindowEnabled(numeric[0]):
            main = numeric[0]
            break
        for window, title in windows:
            options = {
                'Communications Mode': (1053, 1055, 1053),
                'Communications Interface': (1055, 1067, 1055),
                'Connection (GPIB)': None,
                'Measurement Mode': (1105, 1108, 1105),
            }
            if title in options and (window,title) not in handled:
                if options[title]:
                    ctypes.windll.user32.CheckRadioButton(window, *options[title])
                win32gui.PostMessage(window, win32con.WM_COMMAND, 1, win32gui.GetDlgItem(window, 1))
                handled.add((window,title))
        time.sleep(.15)
    else:
        raise RuntimeError(f'Could not open the WT210 numeric window. Windows: {windows}')

    children = []
    def child(window, _):
        if win32gui.GetClassName(window) == 'ToolbarWindow32':
            children.append(window)
    win32gui.EnumChildWindows(main, child, None)
    def state(button):
        for toolbar in children:
            code = int(win32gui.SendMessageTimeout(toolbar, 0x412, button, 0, 2, 2500)[1])
            if code not in (-1, 0xffffffff, 0xffffffffffffffff):
                return code
        raise RuntimeError(f'Missing button {button:#x}')

    def enabled(button):
        return bool(state(button) & 4)
    def responsive():
        win32gui.SendMessageTimeout(main, 0, 0, 0, 2, 2500)

    def file_stamps():
        locations = [Path(p) for p in sys.argv[2:]] or [exe.parent/'Data']
        return {entry:entry.stat().st_mtime_ns for loc in locations for entry in loc.glob('*.csv')}

    def run(duration):
        before = file_stamps()
        win32gui.PostMessage(main, win32con.WM_COMMAND, 0x41a, 0)
        time.sleep(1)
        responsive()
        assert enabled(0x41b), 'Stop button did not activate'
        time.sleep(duration-1)
        win32gui.PostMessage(main, win32con.WM_COMMAND, 0x41b, 0)
        time.sleep(1.5)
        responsive()
        assert enabled(0x41a) and not enabled(0x41b), 'Start/Stop did not return to idle'
        paths = [path for path, stamp in file_stamps().items() if before.get(path) != stamp]
        assert paths, 'No new CSV was written'
        path = max(paths, key=lambda item:item.stat().st_mtime_ns)
        with path.open(encoding='latin-1', newline='') as handle:
            records = [row for row in csv.DictReader(handle) if (row.get('Store No.') or '').strip().isdigit()]
        assert len(records) >= 4, f'Only {len(records)} rows saved in {path}'
        numeric = [tuple(float(row[key].strip()) for key in ('V-1','A-1','W-1')) for row in records]
        assert len(set(numeric)) > 1, f'Readings did not change in {path}'
        print(json.dumps({'rows':len(records),'first':numeric[0],'last':numeric[-1],'path':str(path),'stop':'responsive'}),flush=True)

    run(int(os.environ.get('WT_RUN_SECONDS', '6')))
    run(5)
    before = file_stamps()
    win32gui.PostMessage(main, win32con.WM_COMMAND, 0x41c, 0)
    time.sleep(2)
    responsive()
    assert enabled(0x41a) and not enabled(0x41b), 'Update did not return to idle'
    updates = [path for path, stamp in file_stamps().items() if before.get(path) != stamp]
    assert updates, 'Update did not write a measurement'
    with updates[0].open(encoding='latin-1', newline='') as handle:
        reading = next(csv.DictReader(handle))
        print('Update sample:', [float(reading[key].strip()) for key in ('V-1','A-1','W-1')],flush=True)
    print('Update and a second Start/Stop cycle passed.',flush=True)
    leave_open = os.environ.get('WT_LEAVE_OPEN') == '1'
finally:
    if not locals().get('leave_open', False):
        if 'main' in locals() and win32gui.IsWindow(main):
            win32gui.PostMessage(main, win32con.WM_CLOSE, 0, 0)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)
