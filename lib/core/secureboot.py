import os
import glob

def detect_system_keys():
    """Auto-detect vendor keys and certificates from common system locations"""
    key_locations = [
        # MOK (Machine Owner Key) locations
        '/var/lib/shim-signed/mok/MOK.priv',
        '/var/lib/shim-signed/mok/MOK.key',
        '/etc/secureboot/keys/MOK.key',
        '/boot/efi/EFI/keys/MOK.key',
        
        # Custom key locations
        '/etc/efi-keys/db.key',
        '/etc/ssl/certs/secure-boot.key',
        '/usr/local/share/ca-certificates/secure-boot.key',
        
        # User home directory
        os.path.expanduser('~/secure-boot/MOK.key'),
        os.path.expanduser('~/.efi-keys/db.key'),
    ]
    
    cert_locations = [
        # MOK certificate locations
        '/var/lib/shim-signed/mok/MOK.pem',
        '/var/lib/shim-signed/mok/MOK.crt',
        '/etc/secureboot/keys/MOK.crt',
        '/boot/efi/EFI/keys/MOK.crt',
        
        # Custom certificate locations
        '/etc/efi-keys/db.crt',
        '/etc/ssl/certs/secure-boot.crt',
        '/usr/local/share/ca-certificates/secure-boot.crt',
        
        # User home directory
        os.path.expanduser('~/secure-boot/MOK.crt'),
        os.path.expanduser('~/.efi-keys/db.crt'),
    ]
    
    # Find first available key and certificate
    found_key = None
    found_cert = None
    
    for key_path in key_locations:
        if os.path.exists(key_path) and os.access(key_path, os.R_OK):
            found_key = key_path
            break
    
    for cert_path in cert_locations:
        if os.path.exists(cert_path) and os.access(cert_path, os.R_OK):
            found_cert = cert_path
            break
    
    return found_key, found_cert

def get_machine_owner_guid():
    """Try to get the machine owner GUID from various sources"""
    guid_sources = [
        '/sys/firmware/efi/efivars/MokListRT-605dab50-e046-4300-abb6-3dd810dd8b23',
        '/sys/firmware/efi/vars/MokListRT-605dab50-e046-4300-abb6-3dd810dd8b23/data',
        '/proc/sys/kernel/random/boot_id',  # Fallback to boot ID
    ]
    
    # Try to read from EFI variables first
    for guid_file in guid_sources[:2]:
        try:
            if os.path.exists(guid_file):
                # This would require parsing EFI variable data
                # For now, return a default GUID
                return "77fa9abd-0359-4d32-bd60-28f4e78f784b"  # Microsoft GUID as example
        except:
            continue
    
    # Fallback: generate a consistent GUID based on machine ID
    try:
        with open('/etc/machine-id', 'r') as f:
            machine_id = f.read().strip()
            # Convert machine ID to GUID format
            if len(machine_id) >= 32:
                guid = f"{machine_id[:8]}-{machine_id[8:12]}-{machine_id[12:16]}-{machine_id[16:20]}-{machine_id[20:32]}"
                return guid
    except:
        pass
    
    return ""  # Return empty if nothing found
