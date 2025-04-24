#!/usr/bin/env python3

import sys
import tempfile
import subprocess
import shutil
import os
from pathlib import Path
import re
from typing import Optional, Tuple

def extract_appimage(appimage_path: Path, extract_dir: Path) -> None:
    """Extract AppImage contents to specified directory."""
    # Convert to absolute path to ensure it's found regardless of working directory
    absolute_appimage_path = appimage_path.absolute()
    try:
        subprocess.run([str(absolute_appimage_path), "--appimage-extract"],
                      cwd=extract_dir,
                      stdout=subprocess.DEVNULL,
                      check=True)
    except subprocess.CalledProcessError:
        raise Exception(f"Failed to extract AppImage with command: {absolute_appimage_path} --appimage-extract")
    except FileNotFoundError:
        raise Exception(f"AppImage file not found at: {absolute_appimage_path}")

def get_desktop_file(extract_dir: Path) -> Optional[Path]:
    """Find the .desktop file in the extracted AppImage."""
    desktop_files = list(extract_dir.glob("squashfs-root/**/*.desktop"))
    return desktop_files[0] if desktop_files else None

def parse_icon_name(desktop_file: Path) -> Optional[str]:
    """Extract icon name from .desktop file."""
    with open(desktop_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('Icon='):
                return line.strip().split('=')[1]
    return None

def find_best_icon(extract_dir: Path, icon_name: str) -> Optional[Tuple[Path, str]]:
    """
    Find the best available icon file.
    Returns tuple of (icon_path, extension) or None if not found.
    """
    squashfs_root = extract_dir / "squashfs-root"

    # Common icon locations
    icon_dirs = [
        squashfs_root / "usr/share/icons",
        squashfs_root / "usr/share/pixmaps",
        squashfs_root / ".DirIcon",
        squashfs_root
    ]

    # First, look for exact matches
    for icon_dir in icon_dirs:
        if not icon_dir.exists():
            continue

        # Check for SVG first
        svg_candidates = list(icon_dir.rglob(f"{icon_name}.svg"))
        if svg_candidates:
            return (svg_candidates[0], '.svg')

        # Then check for PNG
        png_candidates = list(icon_dir.rglob(f"{icon_name}.png"))
        if png_candidates:
            # If multiple PNGs exist, find the largest one
            largest_png = max(png_candidates, key=lambda p: p.stat().st_size)
            return (largest_png, '.png')

    # If no exact matches, look for similar names
    for icon_dir in icon_dirs:
        if not icon_dir.exists():
            continue

        # Look for SVGs first
        svg_candidates = list(icon_dir.rglob("*.svg"))
        for svg in svg_candidates:
            if icon_name.lower() in svg.stem.lower():
                return (svg, '.svg')

        # Then look for PNGs
        png_candidates = list(icon_dir.rglob("*.png"))
        if png_candidates:
            # Filter for ones containing the icon name
            matching_pngs = [p for p in png_candidates
                           if icon_name.lower() in p.stem.lower()]
            if matching_pngs:
                largest_png = max(matching_pngs, key=lambda p: p.stat().st_size)
                return (largest_png, '.png')

    # Check if .DirIcon exists and is an image
    diricon = squashfs_root / ".DirIcon"
    if diricon.exists():
        # Try to determine file type from contents
        with open(diricon, 'rb') as f:
            magic_number = f.read(4)
            if magic_number.startswith(b'\x89PNG'):
                return (diricon, '.png')
            elif b'<?xml' in magic_number or b'<svg' in magic_number:
                return (diricon, '.svg')

    return None

def clean_app_name(appimage_path: str) -> str:
    """Clean the AppImage filename to create a base for the icon filename.

    Removes version, date, architecture, OS, build tags, and other common noise,
    while preserving the original case.
    Cleans the remaining string to contain only letters, digits, and hyphens.
    """
    name = Path(appimage_path).stem # Start with original case stem

    # Define patterns to remove
    # More comprehensive version pattern
    version_pattern = r'[-_.]?v?\d+(\.\d+)+([-_.]?\w+)*'
    # Date pattern (YYYYMMDD, YYYY-MM-DD, YYYY.MM.DD)
    date_pattern = r'[-_.]?\d{4}[-_.]?\d{2}[-_.]?\d{2}'
    # Expanded pattern for architecture, OS, distribution, type, build tags etc.
    noise_pattern = (
        r'[-_.](x86[_-]?64|amd64|x64|i\d86|i386|i686|armv\dl|armhf|arm64|aarch64|'
        r'linux|macos|windows|win32|win64|AppImage|portable|deb|rpm|snap|flatpak|'
        r'setup|installer|bundle|build|release|stable|beta|alpha|rc\d*)\b'
    )

    # Apply patterns sequentially - order can matter
    # Remove noise patterns first (case-insensitive)
    name = re.sub(noise_pattern, '', name, flags=re.IGNORECASE)
    # Then remove version strings (case-insensitive for potential 'v' or suffixes)
    name = re.sub(version_pattern, '', name, flags=re.IGNORECASE)
    # Then remove date strings (case doesn't matter)
    name = re.sub(date_pattern, '', name)

    # Final cleanup: only keep letters (case preserved) and digits, replace others with hyphens
    # Replace sequences of non-alphanumeric chars with a single hyphen
    name = re.sub(r'[^a-zA-Z0-9]+', '-', name)
    # Remove leading/trailing hyphens that might have been introduced or left over
    name = name.strip('-')

    # Handle cases where the name becomes empty or just hyphens after cleaning
    if not name or name == '-':
        # Fallback to the original stem, minimally cleaned (alphanumeric+hyphen, case preserved)
        fallback_name = Path(appimage_path).stem
        fallback_name = re.sub(r'[^a-zA-Z0-9]+', '-', fallback_name)
        fallback_name = fallback_name.strip('-')
        # If even fallback is empty, use a default name (lowercase is fine here)
        return fallback_name if fallback_name else 'appimage-icon'

    return name

def create_desktop_file(original_desktop_path: Path, clean_name: str, icon_extension: str, output_dir: Path) -> None:
    """Creates a new .desktop file based on the original, modifying Icon and Exec lines,
       and removing Actions and related sections."""
    new_desktop_path = output_dir / f"AppImage-{clean_name}.desktop"
    
    # Get the full home directory path instead of using ~
    home_dir = str(Path.home())
    appimage_dir = os.path.join(home_dir, "AppImage")
    
    new_icon_entry = f"Icon={appimage_dir}/{clean_name}{icon_extension}"
    new_exec_entry = f"Exec={appimage_dir}/_launch_appimage {clean_name} %U"

    in_action_section = False
    try:
        with open(original_desktop_path, 'r', encoding='utf-8') as infile, \
             open(new_desktop_path, 'w', encoding='utf-8') as outfile:
            for line in infile:
                stripped_line = line.strip()

                # Check for section headers
                if stripped_line.startswith('[') and stripped_line.endswith(']'):
                    section_name = stripped_line[1:-1]
                    # Check if it's a Desktop Action section (case-insensitive)
                    if "desktop action" in section_name.lower():
                        in_action_section = True
                        continue # Skip the action section header itself
                    else:
                        in_action_section = False
                        outfile.write(line) # Write other section headers
                        continue # Process next line

                # Skip lines within an action section
                if in_action_section:
                    continue

                # Process lines outside action sections
                if stripped_line.startswith('Icon='):
                    outfile.write(new_icon_entry + '\n')
                elif stripped_line.startswith('Exec='):
                    outfile.write(new_exec_entry + '\n')
                elif stripped_line.startswith('X-AppImage-Version='):
                    pass # Skip this line
                elif stripped_line.startswith('Actions='):
                    pass # Skip this line
                else:
                    # Write any other line that isn't skipped
                    outfile.write(line)

        print(f".desktop file created at: {new_desktop_path}")
    except OSError as e:
        print(f"Error creating .desktop file {new_desktop_path}: {e}")
        # Don't exit the whole script, just report the error for this part.

def main():
    if len(sys.argv) != 2:
        print("Usage: extract_appimage_icon.py <appimage_file>")
        sys.exit(1)

    appimage_path = Path(sys.argv[1])
    if not appimage_path.exists():
        print(f"Error: File {appimage_path} not found")
        sys.exit(1)

    # Create temporary directory for extraction
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        try:
            # Extract AppImage
            print("Extracting AppImage...")
            extract_appimage(appimage_path, temp_path)

            # Find desktop file
            desktop_file = get_desktop_file(temp_path)
            if not desktop_file:
                print("Error: No .desktop file found in AppImage")
                sys.exit(1)

            # Get icon name from desktop file
            icon_name = parse_icon_name(desktop_file)
            if not icon_name:
                print("Error: No icon specified in .desktop file")
                sys.exit(1)

            # Find best icon
            icon_result = find_best_icon(temp_path, icon_name)
            if not icon_result:
                print("Error: No suitable icon found")
                sys.exit(1)

            icon_path, extension = icon_result

            # Create output filename
            clean_name = clean_app_name(appimage_path.name)
            output_icon_path = Path.cwd() / f"{clean_name}{extension}"

            # Copy icon to current directory
            shutil.copy2(icon_path, output_icon_path)
            print(f"Icon extracted to: {output_icon_path}")

            # Create the .desktop file
            create_desktop_file(desktop_file, clean_name, extension, Path.cwd())
            
            # Combined reminder for complete setup
            desktop_file_name = f"AppImage-{clean_name}.desktop"
            print(f"\nSetup Instructions:")
            print(f"For your AppImage to work with the launcher, please complete these steps:")
            print(f"1. Create the required directories:")
            print(f"   mkdir -p ~/.local/share/applications/ ~/AppImage")
            print(f"2. Place the extracted icon and AppImage in the AppImage directory:")
            print(f"   cp {clean_name}{extension} ~/AppImage/")
            print(f"   cp {appimage_path.name} ~/AppImage/")
            print(f"3. Copy the _launch_appimage script and make it executable:")
            print(f"   cp _launch_appimage ~/AppImage/ && chmod +x ~/AppImage/_launch_appimage")
            print(f"4. Install the desktop file to make the app appear in your system menu:")
            print(f"   cp {desktop_file_name} ~/.local/share/applications/")
            print(f"Once completed, your application should appear in your desktop environment's application menu.")

        except subprocess.CalledProcessError:
            print("Error: Failed to extract AppImage")
            sys.exit(1)
        except Exception as e:
            print(f"Error: {str(e)}")
            sys.exit(1)

if __name__ == "__main__":
    main()
