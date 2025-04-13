import network
import socket
import time
from machine import Pin, I2C
import machine, onewire, ds18x20

# Configuration
WIFI_SSID = "WiFi Name"
WIFI_PASSWORD = "Wifi Password"
I2C_SDA_PIN = 0
I2C_SCL_PIN = 1
I2C_FREQ = 40000
LCD_I2C_ADDR = 0x27
LCD_COLS = 16
LCD_ROWS = 2
HTTP_PORT = 80
DS_PIN = 26
LED_PIN = "LED"
TEMP_READ_INTERVAL = 2  # seconds

# LCD Commands (moved outside class)
LCD_CLEARDISPLAY = 0x01
LCD_RETURNHOME = 0x02
LCD_ENTRYMODESET = 0x04
LCD_DISPLAYCONTROL = 0x08
LCD_CURSORSHIFT = 0x10
LCD_FUNCTIONSET = 0x20
LCD_SETCGRAMADDR = 0x40
LCD_SETDDRAMADDR = 0x80

# Flags for display entry mode
LCD_ENTRYRIGHT = 0x00
LCD_ENTRYLEFT = 0x02
LCD_ENTRYSHIFTINCREMENT = 0x01
LCD_ENTRYSHIFTDECREMENT = 0x00

# Flags for display on/off control
LCD_DISPLAYON = 0x04
LCD_DISPLAYOFF = 0x00
LCD_CURSORON = 0x02
LCD_CURSOROFF = 0x00
LCD_BLINKON = 0x01
LCD_BLINKOFF = 0x00

# Flags for display/cursor shift
LCD_DISPLAYMOVE = 0x08
LCD_CURSORMOVE = 0x00
LCD_MOVERIGHT = 0x04
LCD_MOVELEFT = 0x00

# Flags for function set
LCD_8BITMODE = 0x10
LCD_4BITMODE = 0x00
LCD_2LINE = 0x08
LCD_1LINE = 0x00
LCD_5x10DOTS = 0x04
LCD_5x8DOTS = 0x00

# Flags for backlight control
LCD_BACKLIGHT = 0x08
LCD_NOBACKLIGHT = 0x00

# Enable bit
En = 0b00000100  
Rw = 0b00000010  
Rs = 0b00000001  

class I2cLcd:
    def __init__(self, i2c, addr, cols, rows):
        self.i2c = i2c
        self.addr = addr
        self.cols = cols
        self.rows = rows
        self.backlight = True
        self._write_init_sequence()
        self.displaycontrol = LCD_DISPLAYON | LCD_CURSOROFF | LCD_BLINKOFF
        self.display(True)
        self.displaymode = LCD_ENTRYLEFT | LCD_ENTRYSHIFTDECREMENT
        self._write_cmd(LCD_ENTRYMODESET | self.displaymode)
        self.clear()

    def _write_init_sequence(self):
        for cmd in [0x33, 0x32, 0x28, 0x0C, 0x06, 0x01]:
            self._write_cmd(cmd)
            time.sleep_ms(5)

    def _write_cmd(self, cmd):
        self._write(cmd, 0)

    def _write_char(self, char):
        self._write(ord(char), Rs)

    def _write(self, data, mode):
        high_bits = mode | (data & 0xF0) | (LCD_BACKLIGHT if self.backlight else 0)
        low_bits = mode | ((data << 4) & 0xF0) | (LCD_BACKLIGHT if self.backlight else 0)
        self.i2c.writeto(self.addr, bytes([high_bits]))
        self._pulse_enable(high_bits)
        self.i2c.writeto(self.addr, bytes([low_bits]))
        self._pulse_enable(low_bits)

    def _pulse_enable(self, data):
        self.i2c.writeto(self.addr, bytes([data | En]))  
        time.sleep_us(1)
        self.i2c.writeto(self.addr, bytes([data & ~En]))  
        time.sleep_us(50)

    def clear(self):
        self._write_cmd(LCD_CLEARDISPLAY)
        time.sleep_ms(2)

    def home(self):
        self._write_cmd(LCD_RETURNHOME)
        time.sleep_ms(2)

    def setCursor(self, col, row):
        row_offsets = [0x00, 0x40, 0x14, 0x54]
        if row >= self.rows:
            row = self.rows - 1
        self._write_cmd(LCD_SETDDRAMADDR | (col + row_offsets[row]))

    def display(self, state):
        if state:
            self.displaycontrol |= LCD_DISPLAYON
        else:
            self.displaycontrol &= ~LCD_DISPLAYON
        self._write_cmd(LCD_DISPLAYCONTROL | self.displaycontrol)

    def backlight_on(self):
        self.backlight = True
        self.i2c.writeto(self.addr, bytes([LCD_BACKLIGHT]))

    def backlight_off(self):
        self.backlight = False
        self.i2c.writeto(self.addr, bytes([LCD_NOBACKLIGHT]))

    def print(self, text):
        for char in text:
            self._write_char(char)

    def create_char(self, location, charmap):
        location &= 0x7
        self._write_cmd(LCD_SETCGRAMADDR | (location << 3))
        for i in range(8):
            self._write_char(charmap[i])

# Initialize I2C and LCD
i2c = I2C(0, sda=Pin(I2C_SDA_PIN), scl=Pin(I2C_SCL_PIN), freq=I2C_FREQ)
devices = i2c.scan()
if not devices:
    raise Exception("No I2C device found!")
LCD_I2C_ADDR = devices[0] if LCD_I2C_ADDR not in devices else LCD_I2C_ADDR
lcd = I2cLcd(i2c, LCD_I2C_ADDR, LCD_COLS, LCD_ROWS)
led = Pin(LED_PIN, Pin.OUT)
ds_sensor = ds18x20.DS18X20(onewire.OneWire(Pin(DS_PIN)))

def connect_wifi(max_retries=5):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    for attempt in range(max_retries):
        status = wlan.status()
        if status == network.STAT_CONNECTING:
            continue
            
        if not wlan.isconnected():
            print(f"Connection attempt {attempt+1}/{max_retries}")
            wlan.disconnect()
            wlan.connect(WIFI_SSID, WIFI_PASSWORD)
            
            start = time.time()
            while not wlan.isconnected() and (time.time() - start < 20):
                lcd.setCursor(0, 0)
                lcd.print(f"Connecting  {attempt+1}")
                time.sleep(0.5)
                
        if wlan.isconnected():
            ip = wlan.ifconfig()[0]
            print(f"Connected: {ip}")
            return ip
            
        print(f"Retry {attempt+1} failed. Status: {status}")
        time.sleep(5)
    
    raise RuntimeError("Max connection retries exceeded")

def read_temp():
    try:
        ds_sensor.convert_temp()
        time.sleep_ms(750)
        roms = ds_sensor.scan()
        for rom in roms:
            temp_c = ds_sensor.read_temp(rom)
            if isinstance(temp_c, float):
                return temp_c
        return None
    except Exception as e:
        print(f"Error reading temperature: {e}")
        return None

def create_response(temp):
    html = f"""HTTP/1.0 200 OK\nContent-Type: text/html\n\n<!DOCTYPE html><html><head><title>Pico W Data</title><meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="refresh" content="5"></head><body><h1>Wedzenie 2025 v0.1.0</h1><h1>Temperature: {temp:.2f} °C</h1><h1>Updated: {time.time()}</h1></body></html>"""
    return html

def main():
    lcd.backlight_on()
    lcd.clear()
    ip = None
    s = None
    
    while True:
        try:
            if not network.WLAN(network.STA_IF).isconnected() or ip is None:
                lcd.setCursor(0, 0)
                lcd.print("Reconnecting...")
                ip = connect_wifi()
                if s:
                    s.close()
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.bind(('', HTTP_PORT))
                s.settimeout(5)  
                s.listen(5)
            
            last_temp_read = time.time()
            temp_c = None

            while True:
                try:
                    if time.time() - last_temp_read >= TEMP_READ_INTERVAL:
                        new_temp = read_temp()
                        if new_temp is not None:
                            temp_c = new_temp
                        last_temp_read = time.time()

                    if temp_c is not None:
                        lcd.clear()
                        lcd.setCursor(0, 0)
                        lcd.print(f"Temp:{temp_c:.2f}C")
                    else:
                        lcd.clear()
                        lcd.setCursor(0, 0)
                        lcd.print("Temp: N/A")
                        
                    lcd.setCursor(0, 1)
                    lcd.print(f"{ip}")
                    
                    conn, addr = s.accept()
                    led.value(1)
                    request = conn.recv(1024)
                    response = create_response(temp_c if temp_c is not None else 0)
                    conn.send(response)
                    conn.close()
                    led.value(0)
                except OSError as e:
                    if e.errno == 110:  # ETIMEDOUT
                        continue
                    raise
                except Exception as e:
                    print(f"Error: {e}")
                    lcd.clear()
                    lcd.setCursor(0, 0)
                    lcd.print("Error:")
                    lcd.setCursor(0, 1)
                    lcd.print(str(e)[:15])
                    time.sleep(5)
                    break  # Break inner loop to reconnect
        except Exception as e:
            error_msg = f"Main loop error: {str(e)}"
            print(error_msg)
            lcd.clear()
            lcd.setCursor(0, 0)
            lcd.print("Main Error:")
            lcd.setCursor(0, 1)
            lcd.print(error_msg[:15])
            time.sleep(5)

if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as e:
            error_msg = f"Main loop error: {str(e)}"
            print(error_msg)
            lcd.clear()
            lcd.setCursor(0, 0)
            lcd.print("Main Error:")
            lcd.setCursor(0, 1)
            lcd.print(error_msg[:15])
            time.sleep(5)

