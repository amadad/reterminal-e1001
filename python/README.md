# Python Client

Python library for controlling reTerminal E1001.

## Install

```bash
pip install -r requirements.txt
```

## Usage

### As a Library

```python
from reterminal import ReTerminal

rt = ReTerminal("192.168.1.100")

# Get status
print(rt.status())

# Push text
rt.push_text("Hello World", page=0, font_size=72)

# Push image
rt.push_image("photo.png", page=1)

# Navigation
rt.next_page()
rt.prev_page()
rt.set_page(2)

# Buzzer
rt.beep()
```

### Command Line

```bash
# Display text
python reterminal.py --host 192.168.1.100 --text "Hello World" --page 0

# Display image
python reterminal.py --host 192.168.1.100 --image photo.png --page 1

# Test pattern
python reterminal.py --host 192.168.1.100 --pattern checkerboard

# Device status
python reterminal.py --host 192.168.1.100 --status

# Navigation
python reterminal.py --host 192.168.1.100 --next
python reterminal.py --host 192.168.1.100 --prev
```

## Examples

### Clock Display

```bash
# One-time update
python examples/clock.py --host 192.168.1.100 --page 1

# Continuous (updates every minute)
python examples/clock.py --host 192.168.1.100 --page 1 --loop
```

### System Dashboard

```bash
python examples/dashboard.py --host 192.168.1.100 --page 0
```

## API Reference

### ReTerminal Class

| Method | Description |
|--------|-------------|
| `status()` | Get device status |
| `buttons()` | Get button states |
| `beep()` | Trigger buzzer |
| `get_page()` | Get current page info |
| `set_page(n)` | Set current page |
| `next_page()` | Navigate to next page |
| `prev_page()` | Navigate to previous page |
| `push_raw(data, page)` | Push raw bitmap data |
| `push_image(path, page)` | Convert and push image |
| `push_text(text, page)` | Render and push text |

### Helper Functions

| Function | Description |
|----------|-------------|
| `image_to_raw(path)` | Convert image to raw bitmap |
| `text_to_raw(text)` | Render text to raw bitmap |
| `create_pattern(type)` | Create test pattern |
