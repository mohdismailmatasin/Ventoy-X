import subprocess
import os

def run_ventoy_install(disk_name, secureboot=False):
    """Run the Ventoy2Disk.sh script with the given disk name (e.g., /dev/sdX) and optional secure boot."""
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src/Ventoy2Disk.sh'))
    disk_path = f"/dev/{disk_name}"
    args = ['sudo', script_path]
    if secureboot:
        args.append('-s')
    args.extend(['-i', disk_path])
    try:
        result = subprocess.run(args, capture_output=True, text=True, check=True)
        return (True, result.stdout)
    except subprocess.CalledProcessError as e:
        return (False, e.stderr or str(e))
