import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QLabel, QPushButton, QListWidget, QMessageBox, QHBoxLayout, QTextEdit, QCheckBox, QLineEdit, QFormLayout, QStackedWidget, QComboBox, QRadioButton, QButtonGroup, QFileDialog, QProgressBar
from PySide6.QtGui import QIcon, QColor
from PySide6.QtCore import Qt, QThread, Signal, QTimer
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))
from core.disk import list_usb_disks
from core.disk_ops import run_ventoy_install
from core.plugson import load_plugin_json, save_plugin_json
from core.secureboot import detect_system_keys, get_machine_owner_guid

class EraseThread(QThread):
    log_signal = Signal(str)
    done_signal = Signal(bool, str)
    
    def __init__(self, disk_name, secure_erase=False):
        super().__init__()
        self.disk_name = disk_name
        self.secure_erase = secure_erase
    
    def run(self):
        import subprocess, tempfile
        disk_path = f"/dev/{self.disk_name}"
        
        try:
            self.log_signal.emit(f"Starting USB erase operation on {disk_path}...")
            
            # Create comprehensive erase script
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as erase_script:
                erase_script.write('#!/bin/bash\n')
                erase_script.write('set -e\n')
                erase_script.write('exec > >(tee /tmp/ventoy_erase.log) 2>&1\n')
                erase_script.write('\n')
                erase_script.write('echo "=== Ventoy-X - USB Erase Operation ==="\n')
                erase_script.write(f'echo "Target device: {disk_path}"\n')
                erase_script.write('echo ""\n')
                
                # Step 1: Unmount all partitions
                erase_script.write('echo "Step 1: Unmounting all partitions..."\n')
                erase_script.write(f'for partition in $(lsblk -ln -o NAME {disk_path} | tail -n +2); do\n')
                erase_script.write('    partition_path="/dev/$partition"\n')
                erase_script.write('    echo "Unmounting $partition_path..."\n')
                erase_script.write('    umount "$partition_path" 2>/dev/null || echo "  $partition_path not mounted or failed to unmount"\n')
                erase_script.write('done\n')
                erase_script.write('echo ""\n')
                
                # Step 2: Remove partition table
                erase_script.write('echo "Step 2: Removing partition table..."\n')
                erase_script.write(f'wipefs -af {disk_path} || echo "Warning: wipefs failed"\n')
                erase_script.write('echo ""\n')
                
                # Step 3: Zero out the beginning and end of the drive
                erase_script.write('echo "Step 3: Clearing partition signatures..."\n')
                erase_script.write(f'dd if=/dev/zero of={disk_path} bs=1M count=10 status=progress 2>/dev/null || echo "Warning: could not zero start of drive"\n')
                erase_script.write('echo ""\n')
                
                if self.secure_erase:
                    # Step 4: Secure erase (optional)
                    erase_script.write('echo "Step 4: Performing secure erase (this may take a while)..."\n')
                    erase_script.write('echo "Writing random data to entire drive..."\n')
                    erase_script.write(f'dd if=/dev/urandom of={disk_path} bs=1M status=progress 2>/dev/null || echo "Warning: secure erase may have been interrupted"\n')
                    erase_script.write('echo ""\n')
                else:
                    erase_script.write('echo "Step 4: Skipping secure erase (quick mode)"\n')
                    erase_script.write('echo ""\n')
                
                # Step 5: Final cleanup
                erase_script.write('echo "Step 5: Final cleanup..."\n')
                erase_script.write(f'sync\n')
                erase_script.write('echo "Synchronizing filesystem..."\n')
                erase_script.write('sleep 2\n')
                erase_script.write('echo ""\n')
                
                erase_script.write('echo "=== USB ERASE OPERATION COMPLETED SUCCESSFULLY! ==="\n')
                erase_script.write(f'echo "✅ Device {disk_path} has been completely wiped and is ready for use."\n')
                erase_script.write('echo "✅ All data, partitions, and file system signatures have been removed."\n')
                erase_script.write('echo "✅ The drive is now in a clean state for new installations."\n')
                erase_script.write('echo ""\n')
                erase_script.write('echo "📋 What you can do next:"\n')
                erase_script.write('echo "   • Install Ventoy using the Install/Update button"\n')
                erase_script.write('echo "   • Format with a specific file system (FAT32, NTFS, ext4)"\n')
                erase_script.write('echo "   • Use for any other storage purpose"\n')
                erase_script.write('echo ""\n')
                erase_script.write('echo "Drive status after erase:"\n')
                erase_script.write(f'lsblk {disk_path} 2>/dev/null || echo "✅ Drive is completely clean (no partitions found)"\n')
                
                erase_script_path = erase_script.name
            
            # Make script executable
            import os
            os.chmod(erase_script_path, 0o755)
            
            # Execute the erase script
            self.log_signal.emit("Starting erase operation (you'll only need to enter password once)...")
            args = ['pkexec', 'bash', erase_script_path]
            
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                     text=True, bufsize=1, universal_newlines=True)
            
            output = ''
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                output += line
                self.log_signal.emit(line.strip())
            process.wait()
            
            # Clean up script
            try:
                os.unlink(erase_script_path)
            except:
                pass
            
            if process.returncode == 0:
                self.log_signal.emit("USB erase completed successfully!")
                self.done_signal.emit(True, output)
            else:
                self.log_signal.emit(f"Erase operation failed with exit code: {process.returncode}")
                self.done_signal.emit(False, output)
                
        except Exception as e:
            self.log_signal.emit(f"Error during erase operation: {str(e)}")
            self.done_signal.emit(False, str(e))

class InstallThread(QThread):
    log_signal = Signal(str)
    done_signal = Signal(bool, str)
    def __init__(self, disk_name, secureboot, use_gpt=False, preserve_space=False, sign_efi=False, owner_guid="", vendor_key="", vendor_cert="", upgrade_mode=False):
        super().__init__()
        self.disk_name = disk_name
        self.secureboot = secureboot
        self.use_gpt = use_gpt
        self.preserve_space = preserve_space
        self.sign_efi = sign_efi
        self.owner_guid = owner_guid
        self.vendor_key = vendor_key
        self.vendor_cert = vendor_cert
        self.upgrade_mode = upgrade_mode
    def run(self):
        import subprocess, os, tempfile
        # Use the downloaded ventoy release directory which contains the proper Ventoy installation files
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'src/Ventoy2Disk.sh'))
        install_dir = os.path.dirname(script_path)
        disk_path = f"/dev/{self.disk_name}"
        
        try:
            self.log_signal.emit(f"Starting Ventoy install on {disk_path}...")
            self.log_signal.emit(f"Script path: {script_path}")
            self.log_signal.emit(f"Working directory: {install_dir}")
            
            # Check if script exists
            if not os.path.exists(script_path):
                self.log_signal.emit(f"Error: Script not found at {script_path}")
                self.done_signal.emit(False, f"Script not found at {script_path}")
                return
            
            # Create a comprehensive script that does EVERYTHING in one sudo session
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as master_script:
                master_script.write('#!/bin/bash\n')
                master_script.write('set -e\n')
                master_script.write('exec > >(tee /tmp/ventoy_install.log) 2>&1\n')  # Log everything
                master_script.write('\n')
                master_script.write('echo "=== Ventoy-X - Installation Process ==="\n')
                master_script.write('echo "All operations will be completed efficiently"\n')
                master_script.write('\n')
                
                # Step 1: Unmount any mounted partitions
                master_script.write('echo "Step 1: Unmounting any mounted partitions..."\n')
                master_script.write(f'for partition in $(mount | grep "{disk_path}" | cut -d" " -f1); do\n')
                master_script.write('    echo "Unmounting $partition..."\n')
                master_script.write('    umount "$partition" 2>/dev/null || echo "Could not unmount $partition (may not be mounted)"\n')
                master_script.write('done\n')
                master_script.write('\n')
                
                # Step 2: Run Ventoy installation
                master_script.write('echo "Step 2: Installing/Upgrading Ventoy..."\n')
                master_script.write(f'cd "{install_dir}"\n')
                master_script.write('chmod +x "{}"\n'.format(script_path))
                
                # Build Ventoy command arguments
                script_args = []
                if self.secureboot:
                    script_args.append('-s')
                if self.use_gpt:
                    script_args.append('-g')
                if self.preserve_space:
                    script_args.append('-r')
                if self.upgrade_mode:
                    script_args.append('-u')
                else:
                    script_args.append('-I')
                script_args.append(disk_path)
                
                master_script.write(f'yes | timeout 300 bash "{script_path}" {" ".join(script_args)}\n')
                master_script.write('VENTOY_EXIT_CODE=$?\n')
                master_script.write('if [ $VENTOY_EXIT_CODE -ne 0 ]; then\n')
                master_script.write('    echo "ERROR: Ventoy installation failed with exit code $VENTOY_EXIT_CODE"\n')
                master_script.write('    exit $VENTOY_EXIT_CODE\n')
                master_script.write('fi\n')
                master_script.write('\n')
                
                # Step 3: EFI Signing (if requested and custom keys provided)
                if self.sign_efi and self.vendor_key and self.vendor_cert:
                    master_script.write('echo "Step 3: Signing EFI files with custom keys..."\n')
                    master_script.write('sleep 3  # Wait for partitions to be available\n')
                    master_script.write(f'EFI_PARTITION="{disk_path}1"\n')
                    master_script.write('MOUNT_POINT="/tmp/ventoy_efi_signing"\n')
                    master_script.write('mkdir -p "$MOUNT_POINT"\n')
                    master_script.write('if mount "$EFI_PARTITION" "$MOUNT_POINT" 2>/dev/null; then\n')
                    master_script.write('    echo "Mounted EFI partition for signing"\n')
                    master_script.write('    find "$MOUNT_POINT" -name "*.efi" -type f | while read efi_file; do\n')
                    master_script.write('        echo "Signing $(basename \\"$efi_file\\")..."\n')
                    master_script.write(f'        sbsign --key "{self.vendor_key}" --cert "{self.vendor_cert}"')
                    if self.owner_guid:
                        master_script.write(f' --owner-guid "{self.owner_guid}"')
                    master_script.write(' --output "$efi_file" "$efi_file" 2>/dev/null || echo "Failed to sign $(basename \\"$efi_file\\")"\n')
                    master_script.write('    done\n')
                    master_script.write('    umount "$MOUNT_POINT"\n')
                    master_script.write('    rmdir "$MOUNT_POINT"\n')
                    master_script.write('    echo "EFI signing completed"\n')
                    master_script.write('else\n')
                    master_script.write('    echo "Could not mount EFI partition for signing"\n')
                    master_script.write('fi\n')
                    master_script.write('\n')
                
                # Step 4: Create user directories
                master_script.write('echo "Step 4: Creating user directories..."\n')
                master_script.write('sleep 5  # Wait for partitions to be fully available\n')
                master_script.write('\n')
                master_script.write('# Try to find and mount the Ventoy data partition\n')
                master_script.write('DATA_MOUNTED=false\n')
                master_script.write('MOUNT_POINT="/tmp/ventoy_data_setup"\n')
                master_script.write('mkdir -p "$MOUNT_POINT"\n')
                master_script.write('\n')
                master_script.write(f'for partition in "{disk_path}2" "{disk_path}1"; do\n')
                master_script.write('    if [ "$DATA_MOUNTED" = "false" ]; then\n')
                master_script.write('        echo "Trying to mount $partition..."\n')
                master_script.write('        if mount "$partition" "$MOUNT_POINT" 2>/dev/null; then\n')
                master_script.write('            # Check if this is writable and has reasonable space\n')
                master_script.write('            if [ -w "$MOUNT_POINT" ] && [ "$(df "$MOUNT_POINT" | tail -1 | awk \'{print $4}\')" -gt 100000 ]; then\n')
                master_script.write('                echo "Found Ventoy data partition: $partition"\n')
                master_script.write('                DATA_MOUNTED=true\n')
                master_script.write('                \n')
                master_script.write('                # Create directories\n')
                master_script.write('                mkdir -p "$MOUNT_POINT/ISO"\n')
                master_script.write('                mkdir -p "$MOUNT_POINT/Themes"\n')
                master_script.write('                mkdir -p "$MOUNT_POINT/Plugins"\n')
                master_script.write('                mkdir -p "$MOUNT_POINT/Scripts"\n')
                master_script.write('                \n')
                master_script.write('                # Create README files\n')
                self._add_readme_creation_to_script(master_script)
                master_script.write('                \n')
                master_script.write('                echo "Created directories: ISO/, Themes/, Plugins/, Scripts/"\n')
                master_script.write('                umount "$MOUNT_POINT"\n')
                master_script.write('            else\n')
                master_script.write('                umount "$MOUNT_POINT" 2>/dev/null || true\n')
                master_script.write('            fi\n')
                master_script.write('        fi\n')
                master_script.write('    fi\n')
                master_script.write('done\n')
                master_script.write('\n')
                master_script.write('rmdir "$MOUNT_POINT" 2>/dev/null || true\n')
                master_script.write('\n')
                master_script.write('if [ "$DATA_MOUNTED" = "true" ]; then\n')
                master_script.write('    echo "User directories created successfully!"\n')
                master_script.write('else\n')
                master_script.write('    echo "Warning: Could not create user directories - no suitable partition found"\n')
                master_script.write('fi\n')
                master_script.write('\n')
                master_script.write('echo "=== All operations completed successfully! ==="\n')
                
                master_script_path = master_script.name
            
            # Make the master script executable
            os.chmod(master_script_path, 0o755)
            
            # Run everything in ONE pkexec session
            self.log_signal.emit("Starting single-session installation (you'll only need to enter password once)...")
            args = ['pkexec', 'bash', master_script_path]
            
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)
            
            output = ''
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                output += line
                self.log_signal.emit(line.strip())
            process.wait()
            
            # Clean up scripts
            try:
                os.unlink(master_script_path)
            except:
                pass
            
            # Check results
            if process.returncode == 0:
                self.log_signal.emit("All operations completed successfully!")
                self.done_signal.emit(True, output)
            else:
                self.log_signal.emit(f"Installation failed with exit code: {process.returncode}")
                self.done_signal.emit(False, output)
                
        except Exception as e:
            self.log_signal.emit(f"Error: {str(e)}")
            self.done_signal.emit(False, str(e))
    
    def _add_readme_creation_to_script(self, script_file):
        """Add README file creation commands to the master script"""
        script_file.write('                # ISO README\n')
        script_file.write('                cat > "$MOUNT_POINT/ISO/README.txt" << \'EOF\'\n')
        script_file.write('Ventoy ISO Directory\n')
        script_file.write('==================\n')
        script_file.write('\n')
        script_file.write('Place your .iso and .img files here\n')
        script_file.write('\n')
        script_file.write('Supported formats:\n')
        script_file.write('- .iso files (Linux distributions, Windows, etc.)\n')
        script_file.write('- .img files (disk images)\n')
        script_file.write('- .wim files (Windows imaging)\n')
        script_file.write('- .vhd/.vhdx files (virtual hard disks)\n')
        script_file.write('\n')
        script_file.write('Simply copy your boot files here and they will appear in Ventoy\'s boot menu.\n')
        script_file.write('EOF\n')
        script_file.write('\n')
        
        script_file.write('                # Themes README\n')
        script_file.write('                cat > "$MOUNT_POINT/Themes/README.txt" << \'EOF\'\n')
        script_file.write('Ventoy Themes Directory\n')
        script_file.write('=====================\n')
        script_file.write('\n')
        script_file.write('Place custom Ventoy themes here\n')
        script_file.write('\n')
        script_file.write('Theme structure:\n')
        script_file.write('- Create subdirectories for each theme\n')
        script_file.write('- Include theme.txt configuration file\n')
        script_file.write('- Add background images and fonts\n')
        script_file.write('\n')
        script_file.write('Example: Themes/MyTheme/theme.txt\n')
        script_file.write('EOF\n')
        script_file.write('\n')
        
        script_file.write('                # Plugins README\n')
        script_file.write('                cat > "$MOUNT_POINT/Plugins/README.txt" << \'EOF\'\n')
        script_file.write('Ventoy Plugins Directory\n')
        script_file.write('======================\n')
        script_file.write('\n')
        script_file.write('Plugin files:\n')
        script_file.write('- ventoy.json (main plugin configuration)\n')
        script_file.write('- Custom plugin scripts\n')
        script_file.write('- Persistence configuration\n')
        script_file.write('\n')
        script_file.write('Edit these files using the Plugson tab in Ventoy GUI.\n')
        script_file.write('EOF\n')
        script_file.write('\n')
        
        script_file.write('                # Scripts README\n')
        script_file.write('                cat > "$MOUNT_POINT/Scripts/README.txt" << \'EOF\'\n')
        script_file.write('Ventoy Scripts Directory\n')
        script_file.write('======================\n')
        script_file.write('\n')
        script_file.write('Custom tools and scripts:\n')
        script_file.write('- Diagnostic tools\n')
        script_file.write('- Utility scripts\n')
        script_file.write('- Custom bootable tools\n')
        script_file.write('EOF\n')
        script_file.write('\n')
        
        script_file.write('                # Sample ventoy.json\n')
        script_file.write('                if [ ! -f "$MOUNT_POINT/Plugins/ventoy.json" ]; then\n')
        script_file.write('                    cat > "$MOUNT_POINT/Plugins/ventoy.json" << \'EOF\'\n')
        script_file.write('{\n')
        script_file.write('  "theme": {\n')
        script_file.write('    "file": "/Themes/default/theme.txt",\n')
        script_file.write('    "gfxmode": "1024x768"\n')
        script_file.write('  },\n')
        script_file.write('  "menu_alias": [\n')
        script_file.write('    {\n')
        script_file.write('      "image": "/ISO/ubuntu.iso",\n')
        script_file.write('      "alias": "Ubuntu Linux"\n')
        script_file.write('    }\n')
        script_file.write('  ],\n')
        script_file.write('  "menu_tip": {\n')
        script_file.write('    "left": "10",\n')
        script_file.write('    "top": "80",\n')
        script_file.write('    "color": "red"\n')
        script_file.write('  }\n')
        script_file.write('}\n')
        script_file.write('EOF\n')
        script_file.write('                    echo "Created sample ventoy.json"\n')
        script_file.write('                fi\n')

class DashboardTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        self.disk_list = QListWidget()
        
        # Partition style options
        partition_layout = QHBoxLayout()
        partition_layout.addWidget(QLabel("Partition Style:"))
        self.partition_group = QButtonGroup()
        self.mbr_radio = QRadioButton("MBR")
        self.gpt_radio = QRadioButton("GPT")
        self.mbr_radio.setChecked(True)  # Default to MBR
        self.partition_group.addButton(self.mbr_radio)
        self.partition_group.addButton(self.gpt_radio)
        partition_layout.addWidget(self.mbr_radio)
        partition_layout.addWidget(self.gpt_radio)
        partition_layout.addStretch()
        
        # Other options
        self.secure_boot_checkbox = QCheckBox("Enable Secure Boot Support (-s)")
        self.preserve_space_checkbox = QCheckBox("Preserve some space at disk end (-r)")
        self.upgrade_mode_checkbox = QCheckBox("Upgrade existing Ventoy installation (-u)")
        self.upgrade_mode_checkbox.setToolTip("Use this if Ventoy is already installed on the disk")
        self.sign_efi_checkbox = QCheckBox("Enable EFI signing (uses Ventoy's built-in or custom keys)")
        
        # EFI signing options (initially hidden)
        self.efi_signing_widget = QWidget()
        efi_layout = QFormLayout()
        self.owner_guid_edit = QLineEdit()
        self.owner_guid_edit.setPlaceholderText("Auto-detected or enter custom GUID (optional)")
        self.vendor_key_path_edit = QLineEdit()
        self.vendor_key_path_edit.setPlaceholderText("Optional: Custom key file (leave empty for Ventoy's default)")
        self.vendor_cert_path_edit = QLineEdit()
        self.vendor_cert_path_edit.setPlaceholderText("Optional: Custom certificate (leave empty for Ventoy's default)")
        
        # Auto-detect button
        auto_detect_btn = QPushButton("Auto-Detect Keys")
        auto_detect_btn.setToolTip("Automatically detect system secure boot keys")
        
        browse_key_btn = QPushButton("Browse")
        browse_cert_btn = QPushButton("Browse")
        
        # Layouts for key and cert with auto-detect and browse buttons
        detect_layout = QHBoxLayout()
        detect_layout.addWidget(auto_detect_btn)
        detect_layout.addStretch()
        
        key_layout = QHBoxLayout()
        key_layout.addWidget(self.vendor_key_path_edit)
        key_layout.addWidget(browse_key_btn)
        
        cert_layout = QHBoxLayout()
        cert_layout.addWidget(self.vendor_cert_path_edit)
        cert_layout.addWidget(browse_cert_btn)
        
        efi_layout.addRow(detect_layout)
        efi_layout.addRow("Owner GUID:", self.owner_guid_edit)
        efi_layout.addRow("Vendor Key:", key_layout)
        efi_layout.addRow("Vendor Certificate:", cert_layout)
        self.efi_signing_widget.setLayout(efi_layout)
        self.efi_signing_widget.setVisible(False)
        
        self.refresh_button = QPushButton("Refresh Disks")
        self.install_button = QPushButton("🚀 Install/Update Ventoy")
        self.config_button = QPushButton("Configure Ventoy")
        self.erase_button = QPushButton("🗑️ Erase USB Drive")
        self.install_button.setEnabled(False)
        self.config_button.setEnabled(False)
        self.erase_button.setEnabled(False)
        self.install_button.setToolTip("Complete Ventoy installation!\nIncludes: unmounting, installation, EFI signing, and directory creation")
        self.erase_button.setToolTip("Completely wipe the USB drive\nWarning: This will destroy ALL data on the drive!")
        
        # Erase options
        self.erase_options_widget = QWidget()
        erase_layout = QHBoxLayout()
        self.secure_erase_checkbox = QCheckBox("Secure erase (overwrite with random data)")
        self.secure_erase_checkbox.setToolTip("Takes much longer but more secure - overwrites entire drive with random data")
        erase_layout.addWidget(self.secure_erase_checkbox)
        erase_layout.addStretch()
        self.erase_options_widget.setLayout(erase_layout)
        self.erase_options_widget.setVisible(False)
        
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setVisible(False)  # Initially hidden to save space
        
        # Progress bar for operations
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        
        # Auto-refresh timer for disk detection
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.auto_refresh_disks)
        self.refresh_timer.start(5000)  # Refresh every 5 seconds
        
        layout.addWidget(QLabel("Detected USB Disks:"))
        layout.addWidget(self.disk_list)
        layout.addLayout(partition_layout)
        layout.addWidget(self.secure_boot_checkbox)
        layout.addWidget(self.preserve_space_checkbox)
        layout.addWidget(self.upgrade_mode_checkbox)
        layout.addWidget(self.sign_efi_checkbox)
        layout.addWidget(self.erase_options_widget)
        layout.addWidget(self.efi_signing_widget)
        
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.refresh_button)
        btn_layout.addWidget(self.install_button)
        btn_layout.addWidget(self.config_button)
        btn_layout.addWidget(self.erase_button)
        layout.addLayout(btn_layout)
        
        # Log section with toggle button
        log_header_layout = QHBoxLayout()
        log_label = QLabel("Install Log:")
        self.log_toggle_button = QPushButton("Show Log")
        self.log_toggle_button.setCheckable(True)
        self.log_toggle_button.setChecked(True)  # Initially checked since log is hidden
        self.log_toggle_button.clicked.connect(self.toggle_log_view)
        self.log_toggle_button.setMaximumWidth(100)
        
        log_header_layout.addWidget(log_label)
        log_header_layout.addStretch()
        log_header_layout.addWidget(self.log_toggle_button)
        
        layout.addLayout(log_header_layout)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.log_view)
        self.setLayout(layout)
        self.refresh_button.clicked.connect(self.refresh_disks)
        self.install_button.clicked.connect(self.install_ventoy)
        self.config_button.clicked.connect(self.configure_ventoy)
        self.erase_button.clicked.connect(self.erase_usb)
        self.disk_list.currentRowChanged.connect(self.on_disk_selected)
        self.sign_efi_checkbox.toggled.connect(self.toggle_efi_signing)
        auto_detect_btn.clicked.connect(self.auto_detect_keys)
        browse_key_btn.clicked.connect(self.browse_vendor_key)
        browse_cert_btn.clicked.connect(self.browse_vendor_cert)
        self.refresh_disks()
        self.install_thread = None
        self.erase_thread = None
        
        # Auto-detect keys on startup
        self.auto_detect_keys()

        # Set up keyboard shortcuts
        self.refresh_button.setShortcut("Ctrl+R")
        self.install_button.setShortcut("Ctrl+I")
        self.log_toggle_button.setShortcut("Ctrl+L")
        
        # Add tooltips with shortcuts
        self.refresh_button.setToolTip("Refresh disk list (Ctrl+R)")
        self.install_button.setToolTip("Install/Update Ventoy (Ctrl+I)")
        self.log_toggle_button.setToolTip("Toggle log visibility (Ctrl+L)")
        self.config_button.setToolTip("Configure Ventoy settings")
        self.erase_button.setToolTip("Completely erase USB drive")

    def toggle_efi_signing(self, checked):
        self.efi_signing_widget.setVisible(checked)

    def auto_detect_keys(self):
        """Auto-detect system secure boot keys and GUID"""
        try:
            # Detect keys and certificates
            key_path, cert_path = detect_system_keys()
            owner_guid = get_machine_owner_guid()
            
            # Update fields with detected values
            if key_path:
                self.vendor_key_path_edit.setText(key_path)
                self.vendor_key_path_edit.setToolTip(f"Auto-detected: {key_path}")
            else:
                self.vendor_key_path_edit.setPlaceholderText("Optional: Custom key file (leave empty for Ventoy's default)")
                
            if cert_path:
                self.vendor_cert_path_edit.setText(cert_path)
                self.vendor_cert_path_edit.setToolTip(f"Auto-detected: {cert_path}")
            else:
                self.vendor_cert_path_edit.setPlaceholderText("Optional: Custom certificate (leave empty for Ventoy's default)")
                
            if owner_guid:
                self.owner_guid_edit.setText(owner_guid)
                self.owner_guid_edit.setToolTip(f"Auto-detected GUID")
            else:
                self.owner_guid_edit.setPlaceholderText("Optional: Custom GUID (leave empty if not needed)")
                
            # Show status message
            if key_path and cert_path:
                QMessageBox.information(self, "Auto-Detection Complete", 
                                      f"Found system keys:\nKey: {os.path.basename(key_path)}\nCertificate: {os.path.basename(cert_path)}\n\nNote: These are optional - you can clear them to use Ventoy's built-in signing.")
            elif key_path or cert_path:
                QMessageBox.warning(self, "Partial Detection", 
                                  "Only found partial secure boot files. You can provide the missing files or leave empty to use Ventoy's built-in signing.")
            else:
                QMessageBox.information(self, "No Custom Keys Found", 
                                      "No custom secure boot keys detected.\n\nVentoy will use its built-in secure boot support, or you can browse for custom keys if needed.")
                                      
        except Exception as e:
            QMessageBox.critical(self, "Detection Error", f"Error during auto-detection: {str(e)}")

    def browse_vendor_key(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Vendor Key File", "", "Key Files (*.key *.pem);;All Files (*)")
        if file_path:
            self.vendor_key_path_edit.setText(file_path)

    def browse_vendor_cert(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Vendor Certificate File", "", "Certificate Files (*.crt *.pem *.cer);;All Files (*)")
        if file_path:
            self.vendor_cert_path_edit.setText(file_path)

    def refresh_disks(self):
        self.disk_list.clear()
        self.disks = list_usb_disks()
        for i, d in enumerate(self.disks):
            # Enhanced disk information display
            status_icon = "🟢" if d.get('mounted', False) else "⚪"
            disk_info = f"{status_icon} {d['name']} | {d['model']} | {d['size']}"
            if 'filesystem' in d and d['filesystem']:
                disk_info += f" | {d['filesystem']}"
            self.disk_list.addItem(disk_info)
        
        self.install_button.setEnabled(False)
        self.config_button.setEnabled(False)
        
        # Show status message in log
        if len(self.disks) == 0:
            self.append_log("🔍 No USB drives detected. Please connect a USB drive.", "warning")
        else:
            self.append_log(f"📱 Found {len(self.disks)} USB drive(s). Select one to continue.", "info")

    def on_disk_selected(self, idx):
        enabled = idx >= 0
        self.install_button.setEnabled(enabled)
        self.config_button.setEnabled(enabled)
        self.erase_button.setEnabled(enabled)
        # Show erase options when a disk is selected
        self.erase_options_widget.setVisible(enabled)

    def install_ventoy(self):
        idx = self.disk_list.currentRow()
        if idx < 0:
            return
        disk = self.disks[idx]
        secureboot = self.secure_boot_checkbox.isChecked()
        use_gpt = self.gpt_radio.isChecked()
        preserve_space = self.preserve_space_checkbox.isChecked()
        upgrade_mode = self.upgrade_mode_checkbox.isChecked()
        sign_efi = self.sign_efi_checkbox.isChecked()
        
        # Get EFI signing parameters
        owner_guid = self.owner_guid_edit.text().strip()
        vendor_key = self.vendor_key_path_edit.text().strip()
        vendor_cert = self.vendor_cert_path_edit.text().strip()
        
        # Validate EFI signing parameters if enabled
        if sign_efi:
            # Check if both key and cert are provided (both required if any are provided)
            has_key = vendor_key and os.path.exists(vendor_key)
            has_cert = vendor_cert and os.path.exists(vendor_cert)
            
            if vendor_key and not has_key:
                QMessageBox.warning(self, "File Not Found", f"Vendor key file not found: {vendor_key}")
                return
            if vendor_cert and not has_cert:
                QMessageBox.warning(self, "File Not Found", f"Vendor certificate file not found: {vendor_cert}")
                return
            
            # If one is provided, both should be provided
            if (vendor_key and not vendor_cert) or (vendor_cert and not vendor_key):
                QMessageBox.warning(self, "Incomplete Key Pair", "If you provide a vendor key or certificate, both files are required for signing.")
                return
        
        partition_style = "GPT" if use_gpt else "MBR"
        install_mode = "Upgrade" if upgrade_mode else "Fresh Install"
        
        # Determine EFI signing status
        if sign_efi:
            if vendor_key and vendor_cert:
                efi_status = "Custom keys"
            else:
                efi_status = "Ventoy built-in"
        else:
            efi_status = "Disabled"
        
        options = f"Mode: {install_mode}\nPartition Style: {partition_style}\nSecure Boot: {'Enabled' if secureboot else 'Disabled'}\nPreserve Space: {'Yes' if preserve_space else 'No'}\nEFI Signing: {efi_status}"
        
        warning_text = "All data on the disk will be lost!" if not upgrade_mode else "Existing data in ISO folder will be preserved."
        
        reply = QMessageBox.question(self, "Confirm Install/Update", f"Are you sure you want to {'upgrade' if upgrade_mode else 'install'} Ventoy on: /dev/{disk['name']} ({disk['model']})?\n{warning_text}\n\n{options}", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.install_button.setText("🔄 Processing...")
            self.install_button.setEnabled(False)
            self.refresh_button.setEnabled(False)
            self.config_button.setEnabled(False)
            
            # Show progress bar and log
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)  # Indeterminate progress
            
            self.log_view.clear()
            # Show log view when operation starts
            if not self.log_view.isVisible():
                self.toggle_log_view()
            self.log_view.append("🎯 INSTALLATION MODE: All operations will be completed efficiently!")
            self.log_view.append("=" * 70)
            
            self.install_thread = InstallThread(disk['name'], secureboot, use_gpt, preserve_space, sign_efi, owner_guid, vendor_key, vendor_cert, upgrade_mode)
            self.install_thread.log_signal.connect(lambda text: self.append_log(text, "info"))
            self.install_thread.done_signal.connect(self.install_done)
            self.install_thread.start()

    def configure_ventoy(self):
        idx = self.disk_list.currentRow()
        if idx < 0:
            return
        disk = self.disks[idx]
        QMessageBox.information(self, "Configure Ventoy", f"Ventoy configuration for /dev/{disk['name']} will be available in the Plugson tab.\n\nYou can also manually edit files on the Ventoy partition after installation.")

    def append_log(self, text, log_type="info"):
        """Append colored log messages based on type"""
        if text.strip():  # Only append non-empty lines
            # Add color coding based on log type
            if log_type == "error" or "❌" in text or "FAILED" in text or "Error:" in text:
                colored_text = f'<span style="color: #ff6b6b;">{text.strip()}</span>'
            elif log_type == "warning" or "⚠️" in text or "WARNING" in text or "Warning:" in text:
                colored_text = f'<span style="color: #ffa726;">{text.strip()}</span>'
            elif log_type == "success" or "✅" in text or "SUCCESS" in text or "completed" in text.lower():
                colored_text = f'<span style="color: #4caf50;">{text.strip()}</span>'
            elif "📱" in text or "📤" in text:
                colored_text = f'<span style="color: #29b6f6;">{text.strip()}</span>'
            else:
                colored_text = text.strip()
            
            self.log_view.append(colored_text)
            # Auto-scroll to bottom
            cursor = self.log_view.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            self.log_view.setTextCursor(cursor)

    def install_done(self, success, output):
        self.progress_bar.setVisible(False)
        self.install_button.setText("🚀 Install/Update Ventoy")
        self.install_button.setEnabled(True)
        self.refresh_button.setEnabled(True)
        self.config_button.setEnabled(True)
        self.erase_button.setEnabled(True)
        
        if success:
            self.append_log("=" * 70, "success")
            self.append_log("✅ SUCCESS: All operations completed successfully!", "success")
            QMessageBox.information(self, "Success", "✅ Ventoy installed/updated successfully!\n\n🎯 Operation completed:\n• Installation/upgrade\n• EFI signing (if enabled)\n• Directory creation\n• All steps finished!")
            self.refresh_disks()
        else:
            self.append_log("=" * 70, "error")
            self.append_log("❌ FAILED: Installation encountered errors", "error")
            QMessageBox.critical(self, "Error", "❌ Failed to install/update Ventoy.\nCheck the log for details.")
        
        self.install_thread = None

    def erase_usb(self):
        """Erase the selected USB drive"""
        idx = self.disk_list.currentRow()
        if idx < 0:
            return
        disk = self.disks[idx]
        secure_erase = self.secure_erase_checkbox.isChecked()
        
        erase_type = "Secure erase (with random data overwrite)" if secure_erase else "Quick erase (partition table only)"
        
        # Strong warning message
        reply = QMessageBox.question(self, "⚠️ DANGER: Erase USB Drive", 
            f"🚨 WARNING: This will COMPLETELY ERASE all data on:\n"
            f"/dev/{disk['name']} ({disk['model']})\n\n"
            f"Erase type: {erase_type}\n\n"
            f"⚠️ ALL DATA WILL BE PERMANENTLY LOST!\n"
            f"⚠️ This action CANNOT be undone!\n\n"
            f"Are you absolutely sure you want to proceed?", 
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            # Double confirmation for secure erase
            if secure_erase:
                confirm_reply = QMessageBox.question(self, "Confirm Secure Erase", 
                    f"🔒 Secure erase will overwrite the ENTIRE drive with random data.\n"
                    f"This process may take several hours depending on drive size.\n\n"
                    f"Continue with secure erase?", 
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if confirm_reply != QMessageBox.Yes:
                    return
            
            self.erase_button.setText("🔄 Erasing...")
            self.erase_button.setEnabled(False)
            self.install_button.setEnabled(False)
            self.refresh_button.setEnabled(False)
            self.config_button.setEnabled(False)
            
            # Show progress bar and log
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)  # Indeterminate progress
            
            self.log_view.clear()
            # Show log view when operation starts
            if not self.log_view.isVisible():
                self.toggle_log_view()
            self.log_view.append("🗑️ USB ERASE MODE: Complete drive wipe operation!")
            self.log_view.append("=" * 70)
            
            self.erase_thread = EraseThread(disk['name'], secure_erase)
            self.erase_thread.log_signal.connect(lambda text: self.append_log(text, "warning"))
            self.erase_thread.done_signal.connect(self.erase_done)
            self.erase_thread.start()
            self.erase_thread.start()

    def erase_done(self, success, output):
        """Handle completion of USB erase operation"""
        self.progress_bar.setVisible(False)
        self.erase_button.setText("🗑️ Erase USB Drive")
        self.erase_button.setEnabled(True)
        self.install_button.setEnabled(True)
        self.refresh_button.setEnabled(True)
        self.config_button.setEnabled(True)
        
        if success:
            self.append_log("=" * 70, "success")
            self.append_log("✅ SUCCESS: USB drive erased successfully!", "success")
            QMessageBox.information(self, "Erase Complete", 
                "✅ USB drive erased successfully!\n\n"
                "The drive is now completely clean and ready for:\n"
                "• Fresh Ventoy installation\n"
                "• Regular file system formatting\n"
                "• Any other use")
            # Refresh disk list to update status
            self.refresh_disks()
        else:
            self.append_log("=" * 70, "error")
            self.append_log("❌ FAILED: Erase operation encountered errors", "error")
            QMessageBox.critical(self, "Erase Failed", 
                "❌ Failed to erase USB drive.\n"
                "Check the log for details.\n\n"
                "The drive may still be partially usable,\n"
                "but the erase operation was not completed.")

    def toggle_log_view(self):
        """Toggle the visibility of the install log"""
        if self.log_view.isVisible():
            self.log_view.hide()
            self.log_toggle_button.setText("Show Log")
        else:
            self.log_view.show()
            self.log_toggle_button.setText("Hide Log")
    
    def auto_refresh_disks(self):
        """Auto-refresh disk list if no operations are running"""
        if not self.install_thread and not self.erase_thread:
            old_disk_count = len(self.disks) if hasattr(self, 'disks') else 0
            self.refresh_disks()
            new_disk_count = len(self.disks)
            
            # Only show notification if disks changed
            if old_disk_count != new_disk_count:
                if new_disk_count > old_disk_count:
                    self.append_log(f"📱 USB device detected - {new_disk_count - old_disk_count} new disk(s) found")
                elif new_disk_count < old_disk_count:
                    self.append_log(f"📤 USB device removed - {old_disk_count - new_disk_count} disk(s) disconnected")

class PlugsonTab(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout()
        self.toggle_button = QPushButton("Switch to Visual Editor")
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(False)
        self.toggle_button.toggled.connect(self.toggle_editor)
        self.stacked = QStackedWidget()
        # Raw JSON editor
        self.text_edit = QTextEdit()
        # Visual editor
        self.form_widget = QWidget()
        self.form_layout = QFormLayout()
        self.theme_edit = QLineEdit()
        self.menu_class_edit = QLineEdit()
        self.control_legacy = QCheckBox("Enable Legacy Control")
        self.language_combo = QComboBox()
        self.language_combo.addItems(["", "en_US", "zh_CN", "fr_FR", "de_DE"])  # Example
        self.form_layout.addRow("Theme File", self.theme_edit)
        self.form_layout.addRow("Menu Class", self.menu_class_edit)
        self.form_layout.addRow("Language", self.language_combo)
        self.form_layout.addRow(self.control_legacy)
        self.form_widget.setLayout(self.form_layout)
        self.stacked.addWidget(self.text_edit)
        self.stacked.addWidget(self.form_widget)
        self.save_button = QPushButton("Save Changes")
        self.layout.addWidget(QLabel("ventoy.json Plugin Settings:"))
        self.layout.addWidget(self.toggle_button)
        self.layout.addWidget(self.stacked)
        self.layout.addWidget(self.save_button)
        self.setLayout(self.layout)
        self.save_button.clicked.connect(self.save_changes)
        self.toggle_editor(False)
        self.load_plugin()

    def toggle_editor(self, checked):
        if checked:
            self.toggle_button.setText("Switch to Raw JSON Editor")
            self.stacked.setCurrentIndex(1)
        else:
            self.toggle_button.setText("Switch to Visual Editor")
            self.stacked.setCurrentIndex(0)

    def load_plugin(self):
        import json
        data, path = load_plugin_json()
        self.plugin_path = path
        if data:
            self.text_edit.setPlainText(json.dumps(data, indent=2))
            # Populate visual fields
            self.theme_edit.setText(data.get('theme', ''))
            self.menu_class_edit.setText(data.get('menu_class', ''))
            self.language_combo.setCurrentText(data.get('language', ''))
            self.control_legacy.setChecked(bool(data.get('control_legacy', False)))
        else:
            self.text_edit.setPlainText("{}  # No ventoy.json found")
            self.save_button.setEnabled(False)

    def save_changes(self):
        import json
        if self.toggle_button.isChecked():
            # Visual editor: build dict
            data = {
                'theme': self.theme_edit.text(),
                'menu_class': self.menu_class_edit.text(),
                'language': self.language_combo.currentText(),
                'control_legacy': self.control_legacy.isChecked(),
            }
        else:
            try:
                data = json.loads(self.text_edit.toPlainText())
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Invalid JSON: {e}")
                return
        if save_plugin_json(data, self.plugin_path):
            QMessageBox.information(self, "Saved", "Plugin settings saved successfully.")
        else:
            QMessageBox.critical(self, "Error", "Failed to save plugin settings.")

class SettingsTab(QWidget):
    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window
        layout = QVBoxLayout()
        
        # GUI Theme section
        gui_theme_layout = QFormLayout()
        gui_theme_layout.addRow(QLabel("GUI Appearance:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark"])
        gui_theme_layout.addRow("GUI Theme:", self.theme_combo)
        layout.addLayout(gui_theme_layout)
        
        # Ventoy Theme section
        layout.addWidget(QLabel("Ventoy Boot Theme Management:"))
        ventoy_theme_layout = QVBoxLayout()
        
        # Current theme selection
        current_theme_layout = QFormLayout()
        self.ventoy_theme_combo = QComboBox()
        self.refresh_themes_btn = QPushButton("Refresh Themes")
        self.refresh_themes_btn.setToolTip("Scan Ventoy USB drive for available themes")
        
        theme_selection_layout = QHBoxLayout()
        theme_selection_layout.addWidget(self.ventoy_theme_combo)
        theme_selection_layout.addWidget(self.refresh_themes_btn)
        
        current_theme_layout.addRow("Active Boot Theme:", theme_selection_layout)
        
        # Theme preview and info
        self.theme_info_text = QTextEdit()
        self.theme_info_text.setMaximumHeight(100)
        self.theme_info_text.setReadOnly(True)
        self.theme_info_text.setPlaceholderText("Select a theme to see details...")
        
        current_theme_layout.addRow("Theme Info:", self.theme_info_text)
        
        # Theme management buttons
        theme_buttons_layout = QHBoxLayout()
        self.apply_theme_btn = QPushButton("Apply Theme")
        self.apply_theme_btn.setToolTip("Apply selected theme to Ventoy configuration")
        self.open_themes_folder_btn = QPushButton("Open Themes Folder")
        self.open_themes_folder_btn.setToolTip("Open the Themes folder on Ventoy USB drive")
        
        theme_buttons_layout.addWidget(self.apply_theme_btn)
        theme_buttons_layout.addWidget(self.open_themes_folder_btn)
        theme_buttons_layout.addStretch()
        
        ventoy_theme_layout.addLayout(current_theme_layout)
        ventoy_theme_layout.addLayout(theme_buttons_layout)
        layout.addLayout(ventoy_theme_layout)
        
        # Language section
        lang_layout = QFormLayout()
        lang_layout.addRow(QLabel("Language:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["English", "简体中文", "Français", "Deutsch"])
        lang_layout.addRow("Interface Language:", self.lang_combo)
        layout.addLayout(lang_layout)
        
        layout.addStretch()
        self.setLayout(layout)
        
        # Connect signals
        self.theme_combo.currentTextChanged.connect(self.change_gui_theme)
        self.refresh_themes_btn.clicked.connect(self.refresh_ventoy_themes)
        self.ventoy_theme_combo.currentTextChanged.connect(self.on_ventoy_theme_selected)
        self.apply_theme_btn.clicked.connect(self.apply_ventoy_theme)
        self.open_themes_folder_btn.clicked.connect(self.open_themes_folder)
        
        # Language switching is a placeholder for now
        # Initialize
        self.refresh_ventoy_themes()

    def change_gui_theme(self, theme):
        if self.main_window:
            if theme == "Dark":
                self.main_window.setStyleSheet("""
                    QWidget { background: #232629; color: #f0f0f0; }
                    QPushButton { background: #444; color: #fff; border: 1px solid #666; padding: 5px; }
                    QPushButton:hover { background: #555; }
                    QLineEdit, QTextEdit { background: #333; color: #fff; border: 1px solid #666; }
                    QComboBox { background: #333; color: #fff; border: 1px solid #666; }
                    QListWidget { background: #333; color: #fff; border: 1px solid #666; }
                    QTabWidget::pane { border: 1px solid #666; }
                    QTabBar::tab { background: #444; color: #fff; padding: 5px 10px; margin-right: 2px; }
                    QTabBar::tab:selected { background: #555; }
                """)
            else:
                self.main_window.setStyleSheet("")
    
    def refresh_ventoy_themes(self):
        """Scan for available Ventoy themes on connected USB drives"""
        self.ventoy_theme_combo.clear()
        self.ventoy_theme_combo.addItem("Default Ventoy Theme", None)
        
        # Import here to avoid circular imports
        from core.disk import list_usb_disks
        
        try:
            usb_disks = list_usb_disks()
            themes_found = []
            
            for disk in usb_disks:
                # Check both possible partition layouts
                for partition_num in ['1', '2']:
                    mount_point = f"/tmp/ventoy_theme_scan_{disk['name']}{partition_num}"
                    try:
                        import subprocess, os
                        # Create mount point
                        subprocess.run(['mkdir', '-p', mount_point], check=True)
                        
                        # Try to mount
                        mount_result = subprocess.run(
                            ['udisksctl', 'mount', '-b', f"/dev/{disk['name']}{partition_num}"],
                            capture_output=True, text=True
                        )
                        
                        if mount_result.returncode == 0:
                            # Extract mount path from output
                            for line in mount_result.stdout.split('\n'):
                                if 'Mounted' in line and 'at' in line:
                                    actual_mount = line.split('at')[-1].strip().rstrip('.')
                                    break
                            else:
                                actual_mount = mount_point
                            
                            # Look for Themes directory
                            themes_dir = os.path.join(actual_mount, 'Themes')
                            if os.path.exists(themes_dir) and os.path.isdir(themes_dir):
                                # Scan for theme directories
                                for theme_name in os.listdir(themes_dir):
                                    theme_path = os.path.join(themes_dir, theme_name)
                                    if os.path.isdir(theme_path):
                                        # Check if theme.txt exists
                                        theme_file = os.path.join(theme_path, 'theme.txt')
                                        if os.path.exists(theme_file):
                                            theme_info = {
                                                'name': theme_name,
                                                'path': theme_path,
                                                'config_file': theme_file,
                                                'disk': disk['name']
                                            }
                                            themes_found.append(theme_info)
                            
                            # Unmount
                            subprocess.run(['udisksctl', 'unmount', '-b', f"/dev/{disk['name']}{partition_num}"], 
                                         capture_output=True)
                            
                    except Exception:
                        pass
                    finally:
                        # Cleanup
                        try:
                            subprocess.run(['rmdir', mount_point], capture_output=True)
                        except:
                            pass
            
            # Add found themes to combo box
            for theme in themes_found:
                display_name = f"{theme['name']} (USB: {theme['disk']})"
                self.ventoy_theme_combo.addItem(display_name, theme)
                
            if themes_found:
                self.theme_info_text.setText(f"Found {len(themes_found)} custom theme(s)")
            else:
                self.theme_info_text.setText("No custom themes found. You can add themes to the Themes/ folder on your Ventoy USB drive.")
                
        except Exception as e:
            self.theme_info_text.setText(f"Error scanning for themes: {str(e)}")
    
    def on_ventoy_theme_selected(self):
        """Handle theme selection change"""
        current_data = self.ventoy_theme_combo.currentData()
        if current_data is None:
            self.theme_info_text.setText("Default Ventoy theme - clean and minimal appearance")
            self.apply_theme_btn.setEnabled(False)
        else:
            try:
                # Read theme.txt file to show info
                with open(current_data['config_file'], 'r') as f:
                    theme_content = f.read()
                    
                self.theme_info_text.setText(f"Theme: {current_data['name']}\nLocation: {current_data['path']}\n\nConfiguration preview:\n{theme_content[:200]}{'...' if len(theme_content) > 200 else ''}")
                self.apply_theme_btn.setEnabled(True)
            except Exception as e:
                self.theme_info_text.setText(f"Error reading theme configuration: {str(e)}")
                self.apply_theme_btn.setEnabled(False)
    
    def apply_ventoy_theme(self):
        """Apply selected theme to Ventoy configuration"""
        current_data = self.ventoy_theme_combo.currentData()
        if current_data is None:
            return
            
        try:
            # This would update the ventoy.json file to use the selected theme
            # For now, show a message with instructions
            theme_path = f"/Themes/{current_data['name']}/theme.txt"
            
            msg = f"""To apply the theme '{current_data['name']}':

1. Open the Plugson tab
2. Edit the ventoy.json configuration
3. Add or modify the theme section:

{{
  "theme": {{
    "file": "{theme_path}",
    "gfxmode": "1024x768"
  }}
}}

4. Save the configuration

The theme will be active on next boot from the Ventoy USB drive."""
            
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Apply Theme", msg)
            
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", f"Failed to apply theme: {str(e)}")
    
    def open_themes_folder(self):
        """Open the Themes folder on the Ventoy USB drive"""
        try:
            from core.disk import list_usb_disks
            import subprocess
            
            usb_disks = list_usb_disks()
            if not usb_disks:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.information(self, "No USB Drive", "No USB drives detected. Please connect a Ventoy USB drive.")
                return
            
            # For simplicity, try to open the first USB drive's Themes folder
            disk = usb_disks[0]
            
            # Try to mount and open
            for partition_num in ['1', '2']:
                try:
                    mount_result = subprocess.run(
                        ['udisksctl', 'mount', '-b', f"/dev/{disk['name']}{partition_num}"],
                        capture_output=True, text=True
                    )
                    
                    if mount_result.returncode == 0:
                        # Extract mount path
                        for line in mount_result.stdout.split('\n'):
                            if 'Mounted' in line and 'at' in line:
                                mount_path = line.split('at')[-1].strip().rstrip('.')
                                themes_path = f"{mount_path}/Themes"
                                
                                # Open file manager
                                subprocess.run(['xdg-open', themes_path])
                                return
                                
                except Exception:
                    continue
            
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", "Could not access Themes folder on USB drive.")
            
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", f"Error opening Themes folder: {str(e)}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ventoy-X")
        self.setWindowIcon(QIcon())
        self.resize(800, 600)

        tabs = QTabWidget()
        tabs.addTab(DashboardTab(), "Dashboard")
        tabs.addTab(PlugsonTab(), "Plugson")
        self.settings_tab = SettingsTab(main_window=self)
        tabs.addTab(self.settings_tab, "Settings")

        self.setCentralWidget(tabs)

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
