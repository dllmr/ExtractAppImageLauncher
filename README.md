# ExtractAppImageLauncher

A simple Python utility that extracts icons and creates desktop entries from AppImage files.

## Features

- Extracts icons from AppImage files
- Creates desktop entry files (.desktop) for easy application launching
- Automatically cleans application names
- Handles different icon formats (SVG, PNG)
- Searches multiple locations within the AppImage for icon files

## Requirements

- Python 3.6+
- AppImage files with executable permissions

## Installation

Clone this repository:

```bash
git clone https://github.com/dllmr/ExtractAppImageLauncher.git
cd ExtractAppImageLauncher
```

Make the script executable:

```bash
chmod +x extract_appimage_launcher.py
```

## Usage

```bash
./extract_appimage_launcher.py /path/to/your-application.AppImage
```

### Example

```bash
./extract_appimage_launcher.py ~/Downloads/cider-linux-x64.AppImage
```

## How It Works

1. Extracts the AppImage to a temporary directory
2. Locates the .desktop file within the extracted content
3. Parses the .desktop file to find the icon name
4. Searches for the best matching icon in the extracted files
5. Copies the icon to the current directory with a cleaned name
6. Creates a new .desktop file that points to the extracted icon

## Output

The script will generate:
- An icon file in the current directory (with appropriate extension)
- A .desktop file that can be used to launch the application

## License

[MIT License](LICENSE) 