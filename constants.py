SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 768

language_lookup_table = {
    'cn': 'zh',
    'jp': 'ja'
}

ami_lookup_table = {
    'snapshot_used_en': 'ami-0132f892c5d80f6ba',
    'snapshot_used_zh': 'ami-041d43ade1bded250',
    'snapshot_used_ar': 'ami-0788f9675451c8c0b',
    'snapshot_used_ja': 'ami-09bf9d80c30e9a2bb',
    'snapshot_used_ru': 'ami-02199d3a0f6b08a9f',
    'snapshot_usedApps_en': 'ami-07f4fd69378358c18',
    'snapshot_usedApps_zh': 'ami-05d53e9457be4cb2c',
    'snapshot_usedApps_ar': 'ami-0ddb58aed32bc4e64',
    'snapshot_usedApps_ja': 'ami-0e331d94ceb1a41ed',
    'snapshot_usedApps_ru': 'ami-07e98ef3c25032b50',
}

env_init_command = """find /Library/Logs/DiagnosticReports -type f -name "panic*.panic" -mmin -20 2>/dev/null | grep -q . && osascript -e 'tell application "System Events" to click at {456,349}' && rm -rf /Library/Logs/DiagnosticReports/*.panic; diskutil list | grep Creedence | awk '{print $NF}' | xargs -I {} diskutil eject {} 2>/dev/null"""
# The first command ignores system crash pop-up windows to avoid them blocking the UI
# The second command removes excess hard drives to avoid their super-long name alters Finder's layout

eval_init_command = """osascript -e 'tell application "System Events" to get value of attribute "AXFullScreen" of window 1 of (first application process whose frontmost is true)' | grep -q true && osascript -e 'tell application "System Events" to keystroke "f" using {control down, command down}' """