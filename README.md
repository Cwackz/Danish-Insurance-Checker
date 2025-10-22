# Danish Vehicle Insurance Checker

A Python application that detects Danish license plates from your camera and checks if vehicles are self-insured, highlighting them with red tracking boxes.

## Features

- **Real-time camera detection** - Uses your webcam to detect license plates
- **Computer vision** - OpenCV-based license plate detection and OCR
- **Insurance checking** - Scrapes tjekbil.dk for insurance information
- **Visual tracking** - Red boxes around self-insured vehicles with tracking trails
- **Command-line interface** - Check individual plates or run camera mode

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Install ChromeDriver (required for Selenium):
   - **macOS**: `brew install chromedriver`
   - **Ubuntu/Debian**: `sudo apt-get install chromium-chromedriver`
   - **Windows**: Download from [ChromeDriver website](https://chromedriver.chromium.org/)

3. Install Tesseract OCR (required for license plate recognition):
   - **macOS**: `brew install tesseract`
   - **Ubuntu/Debian**: `sudo apt-get install tesseract-ocr`
   - **Windows**: Download from [Tesseract website](https://github.com/UB-Mannheim/tesseract/wiki)

## Usage

### Camera Mode (Real-time Detection):
```bash
python3 main.py camera
```
- Opens your webcam and detects license plates in real-time
- Red boxes highlight self-insured vehicles
- Green boxes show vehicles with regular insurance
- Press 'q' to quit, 's' to save screenshot

### Check a single license plate:
```bash
python3 main.py AB12345
```

### Run test suite:
```bash
python3 main.py
```

## How it works

### Camera Mode:
1. **Frame Capture** - Captures video frames from your webcam
2. **License Plate Detection** - Uses OpenCV to detect rectangular regions that look like license plates
3. **OCR Processing** - Uses Tesseract OCR to extract text from detected regions
4. **Pattern Matching** - Validates text against Danish license plate patterns (2-3 letters + 4-5 digits)
5. **Insurance Lookup** - For each valid plate, queries tjekbil.dk for insurance information
6. **Visual Tracking** - Draws colored boxes around vehicles based on insurance status
7. **Trail Tracking** - Shows red trails for self-insured vehicles as they move

### Single Plate Mode:
1. Uses Selenium to handle JavaScript-heavy content
2. Navigates to the vehicle's overview page on tjekbil.dk
3. Waits for dynamic content to load
4. Parses vehicle details for insurance information
5. Detects self-insurance keywords in Danish text

## Insurance Detection

The scraper looks for these Danish keywords to detect self-insurance:
- `selvforsikret` (self-insured)
- `egenforsikring` (own insurance)
- `selvforsikring` (self-insurance)
- `selvansvar` (self-responsibility)

For regular insurance, it detects:
- `forsikringsselskab` (insurance company)
- `ansvarsforsikring` (liability insurance)
- `kaskoforsikring` (comprehensive insurance)
- Common Danish insurance company names

## Output

The scraper provides:
- ⚠️ **SELF-INSURED!** - Vehicle is self-insured
- ✅ **Regular insurance** - Vehicle has standard insurance
- ❓ **Unclear** - Insurance status could not be determined

## Important Notes

- This tool is for educational/research purposes
- Respect the website's terms of service
- Use reasonable delays between requests
- The tjekbil.dk website may change, requiring updates to the scraper
- Always verify results through official channels

## Troubleshooting

If you get "insurance status unclear" results:
1. The license plate may not exist in the database
2. The website structure may have changed
3. The vehicle may not have insurance information available

## Legal Disclaimer

This tool is provided for educational purposes only. Users are responsible for complying with all applicable laws and website terms of service. The authors are not responsible for any misuse of this tool.
