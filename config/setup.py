from setuptools import setup, find_packages

# Read version from VERSION file
with open('VERSION', 'r') as f:
    version = f.read().strip()

# Read long description from README
with open('README.md', 'r', encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='EnhancedVentoyGUI',
    version=version,
    description='Modern, feature-rich GUI for Ventoy with advanced USB management',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='Enhanced Ventoy GUI Team',
    packages=find_packages(),
    install_requires=[
        'PySide6>=6.0.0',
    ],
    entry_points={
        'gui_scripts': [
            'ventoy-gui = main:main',
        ],
        'console_scripts': [
            'ventoy-gui-cli = main:main',
        ],
    },
    include_package_data=True,
    python_requires='>=3.8',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: End Users/Desktop',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Topic :: System :: Boot',
        'Topic :: System :: Systems Administration',
        'Topic :: Utilities',
    ],
    keywords='ventoy usb bootable installer gui',
)
