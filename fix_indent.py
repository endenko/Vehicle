import sys

def fix_file(filename, start_marker, end_marker):
    with open(filename, 'r') as f:
        lines = f.readlines()
        
    start_idx = -1
    end_idx = -1
    for i, line in enumerate(lines):
        if start_marker in line:
            start_idx = i
        if end_marker in line and start_idx != -1 and end_idx == -1:
            end_idx = i
            
    if start_idx != -1 and end_idx != -1:
        for i in range(start_idx + 1, end_idx):
            lines[i] = "    " + lines[i]
            
        with open(filename, 'w') as f:
            f.writelines(lines)
        print(f"Fixed {filename}")
    else:
        print(f"Markers not found in {filename}")

fix_file("gui/pages/xe_vao_page.py", "Ngăn xử lý vào ngoài giờ hoạt động", "threading.Thread(target=_register_and_wait, daemon=True).start()")
fix_file("gui/pages/xe_ra_page.py", "from ..utils.db_local import calc_fee_with_surcharge", "threading.Thread(target=_register_and_wait, daemon=True).start()")

