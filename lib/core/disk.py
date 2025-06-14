import subprocess
import re

def list_usb_disks():
    """Detect available USB disks using lsblk and return a list of dicts."""
    try:
        output = subprocess.check_output(['lsblk', '-o', 'NAME,MODEL,SIZE,TYPE,TRAN'], text=True)
        disks = []
        for line in output.splitlines():
            if 'usb' in line.lower() and 'disk' in line.lower():
                # Split more carefully to handle spaces in model names
                parts = line.strip().split()
                if len(parts) >= 5:
                    name = parts[0]
                    # The model might have spaces, so we need to reconstruct it
                    # Format: NAME MODEL... SIZE TYPE TRAN
                    size = parts[-3]
                    disk_type = parts[-2] 
                    tran = parts[-1]
                    # Everything between name and the last 3 parts is the model
                    model_parts = parts[1:-3]
                    model = ' '.join(model_parts) if model_parts else 'Unknown'
                    
                    disks.append({
                        'name': name,
                        'model': model,
                        'size': size,
                        'type': disk_type,
                        'tran': tran,
                    })
        return disks
    except Exception as e:
        return []
