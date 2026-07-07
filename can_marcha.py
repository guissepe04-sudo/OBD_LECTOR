import serial
import time

PORT = "/dev/ttyUSB0"
BAUDRATE = 115200

GEAR_CODES = {"01": "P", "02": "R", "03": "N", "04": "D"}

def enviar(ser, cmd, espera=0.5):
    ser.write((cmd + "\r").encode())
    time.sleep(espera)
    ser.read_all()

ser = serial.Serial(PORT, BAUDRATE, timeout=1)
enviar(ser, "ATZ", espera=2)
enviar(ser, "ATE0")
enviar(ser, "ATL0")
enviar(ser, "ATH1")
enviar(ser, "ATSP6")
enviar(ser, "0100")
ser.write(b"ATMA\r")

while True:
    linea = ser.read_until(b"\r").decode(errors="ignore").strip()
    if linea.startswith("28D"):
        partes = linea.split()
        if len(partes) >= 4:
            codigo = partes[3]
            marcha = GEAR_CODES.get(codigo, f"?({codigo})")
            print(f"Palanca: {marcha}")
    elif "BUFFER" in linea:
        ser.write(b"ATMA\r")
