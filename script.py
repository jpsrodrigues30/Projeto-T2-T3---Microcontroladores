import RPi.GPIO as GPIO
import smbus2
import time
import adafruit_dht
import board
import requests
import threading
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from luma.core.render import canvas
from PIL import ImageFont, ImageDraw

# Configuracao do broker MQTT
TOKEN = "BBUS-w5pyQyQpZR5IPhjfgQcaotks3CxNc8"
DEVICE_LABEL = "raspberrypi"
TEMPERATURE_LABEL = "Temperature"
HUMIDITY_LABEL = "Humidity"
CONFIG_TEMPERATURE_LABEL = "ConfigTemp"
COOLER_STATUS_LABEL="CoolerStatus"
PELTIER_STATUS_LABEL="PeltierStatus"
URL = f"https://industrial.api.ubidots.com/api/v1.6/devices/{DEVICE_LABEL}/"

# Definicao dos pinos para cada componente
GPIO.setmode(GPIO.BCM)

i2c0_sda_pin = 2
i2c0_slc_pin = 3

dht11_pin = board.D23

rele_pin = 25
GPIO.setup(rele_pin, GPIO.OUT)

ir_pin = 7
GPIO.setup(ir_pin, GPIO.IN)

segment_map = {
    '0': [0, 0, 0, 0, 0, 0, 1],
    '1': [1, 0, 0, 1, 1, 1, 1],
    '2': [0, 0, 1, 0, 0, 1, 0],
    '3': [0, 0, 0, 0, 1, 1, 0],
    '4': [1, 0, 0, 1, 1, 0, 0],
    '5': [0, 1, 0, 0, 1, 0, 0],
    '6': [0, 1, 0, 0, 0, 0, 0],
    '7': [0, 0, 0, 1, 1, 1, 1],
    '8': [0, 0, 0, 0, 0, 0, 0],
    '9': [0, 0, 0, 0, 1, 0, 0],
}

digit1_pins = [4, 17, 27, 22, 10, 9, 11]
digit2_pins = [5, 6, 13, 19, 26, 21, 20]
for pin in digit1_pins + digit2_pins:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)
    
increment_pin = 12
decrement_pin = 16
GPIO.setup(increment_pin, GPIO.IN)
GPIO.setup(decrement_pin, GPIO.IN)

# Definicao do barramento I2C
bus = smbus2.SMBus(1)

# Inicializa o display SSD1306 no end 0x3C
serial = i2c(port=1, address=0x3C)
device = ssd1306(serial)

# Inicializa o sensor de temperatura e humidade DHT11
dht_sensor = adafruit_dht.DHT11(board.D23, use_pulseio=False)

# Declaracao de variaveis globais
tempDesejada = 10
cooler_state = 0
last_cooler_state = 0

# Definicao de funcoes
def send_data(variable_label, valor):
    payload = {variable_label: valor}
    headers = {"X-Auth-Token": TOKEN, "Content-Type": "application/json"}
    
    response = requests.post(URL, json=payload, headers=headers)
    if response.status_code == 200:
        print("Dados enviados com sucesso!")
    else:
        print("Erro ao enviar os dados: ", response.status_code, response.text)
        
def get_data(variable_label):
    headers = {"X-Auth-Token": TOKEN, "Content-Type": "application/json"}
    url = URL + variable_label
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        valor = data.get("last_value", {}).get("value")
        if valor is not None:
            return float(valor)
        else:
            return None
    else:
        print("Erro ao fazer requisicao get ao Ubidots: ", response.status_code, response.text)
        return None

def read_and_display():
    for i in range(5):
        try:
            temperature = dht_sensor.temperature
            humidity = dht_sensor.humidity
        except RuntimeError as e:
            print("Erro interno na leitura, tentando novamente...")
    if temperature is not None and humidity is not None:
        with canvas(device) as draw:
            temp_message = f"Temperatura: {temperature:.1f}C"
            humid_message = f"Umidade: {humidity:.1f}%"
            print(f"Temperatura: {temperature:.1f}C")
            print(f"Umidade: {humidity:.1f}%")
             
            temp_size = draw.textbbox((0,0), temp_message, font=font)
            humidity_size = draw.textbbox((0,0), humid_message, font=font)
            
            temp_x = (device.width - temp_size[2]) // 2
            temp_y = (device.height // 4)
            
            humidity_x = (device.width - humidity_size[2]) // 2
            humidity_y = (device.height // 2)
            
            draw.text((temp_x, temp_y), temp_message, font=font, fill="white")
            draw.text((humidity_x, humidity_y), humid_message, font=font, fill="white")
            
            send_data(TEMPERATURE_LABEL, temperature)
            send_data(HUMIDITY_LABEL, humidity)
    else:
        print("Falha ao ler os dados do sensor...")
    return temperature, humidity

def display_digit(temp_param):
    result = temp_param / 10
    rest = temp_param % 10
    segments_first_digit = segment_map[str(int(result))]
    segments_second_digit = segment_map[str(int(rest))]
    
    for i in range(len(digit1_pins)):
        GPIO.output(digit1_pins[i], segments_first_digit[i])
    for i in range(len(digit2_pins)):
        GPIO.output(digit2_pins[i], segments_second_digit[i])
        
def altera():
    global tempDesejada
    while True:
        display_digit(tempDesejada)
        if GPIO.input(increment_pin) == GPIO.HIGH:
            tempDesejada += 1
            display_digit(tempDesejada)
            send_data(CONFIG_TEMPERATURE_LABEL, tempDesejada)
        elif GPIO.input(decrement_pin) == GPIO.HIGH:
            tempDesejada -= 1
            display_digit(tempDesejada)
            send_data(CONFIG_TEMPERATURE_LABEL, tempDesejada)
        time.sleep(1)
            
def coolerStatus():
    global cooler_state, last_cooler_state
    while True:
        if GPIO.input(ir_pin) == 0:
            print("Cooler fechado")
            last_cooler_state = cooler_state
            cooler_state = 1
        else:
            print("Cooler aberto")
            last_cooler_state = cooler_state
            cooler_state = 0
        send_data(COOLER_STATUS_LABEL, cooler_state)
        time.sleep(3)
        
# Inicializando as threads
thread_botao = threading.Thread(target = altera)
thread_ir = threading.Thread(target = coolerStatus)
thread_botao.start()
thread_ir.start()
        
# Inicializando as variaveis para o sistema
try:
    print("Inicializando o sistema...")
    font = ImageFont.load_default()
    rele_state = 0
    count = 15
    
    time.sleep(1)
    while True:
        tempDesejada = get_data(CONFIG_TEMPERATURE_LABEL)
        print(f"Temperatura desejada: {tempDesejada}")
        
        temp, hum = read_and_display()
        
        if(temp is not None and hum is not None):
            if(temp > tempDesejada + 2 and count >= 15 and cooler_state == 1):
                GPIO.output(rele_pin, GPIO.HIGH)
                rele_state = 1
                count = 0
            elif(temp < tempDesejada - 2 and count >= 15):
                GPIO.output(rele_pin, GPIO.LOW)
                rele_state = 0
                count = 0
            
        if(last_cooler_state == 0 and cooler_state == 1):
            GPIO.output(rele_pin, GPIO.HIGH)
            rele_state = 1
        elif(cooler_state == 0):
            GPIO.output(rele_pin, GPIO.LOW)
            rele_state = 0
        
        count += 1
        print(f"contando... {count}")
        
        send_data(PELTIER_STATUS_LABEL, rele_state)
        time.sleep(3)
except KeyboardInterrupt:
    print("Script interrupted by user...")
finally:
    GPIO.cleanup()
    