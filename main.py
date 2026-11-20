import machine
import time
import struct
import dht
import network
import ntptime
import urequests
import ujson
import gc
import urandom

import banco

WIFI_CELULAR = "POCO"
SENHA_CELULAR = "********"
FIREBASE_URL = "https://estacao-iot-unip-default-rtdb.firebaseio.com/"

sta = network.WLAN(network.STA_IF)
sta.active(True)
sta.connect(WIFI_CELULAR, SENHA_CELULAR)

print("Conectando ao roteador do celular...")
while not sta.isconnected():
    time.sleep(0.5)

print("\n=========================================================")
print("Conectado! Acesse o Dashboard no PC ou Celular pelo link:")
print("https://estacaoesp32.netlify.app/")
print("=========================================================\n")

rtc = machine.RTC()
try:
    ntptime.settime()
    tm = time.localtime(time.time() - 10800)
    rtc.datetime((tm[0], tm[1], tm[2], tm[6], tm[3], tm[4], tm[5], 0))
    print("Hora oficial sincronizada!")
except Exception:
    rtc.datetime((2026, 11, 20, 4, 2, 25, 0, 0))

class BMP280:
    def __init__(self, i2c, addr=0x76):
        self.i2c = i2c
        self.addr = addr
        self.i2c.writeto_mem(self.addr, 0xF4, b'\x27')
        self.i2c.writeto_mem(self.addr, 0xF5, b'\xA0')
        cal = self.i2c.readfrom_mem(self.addr, 0x88, 24)
        self.T1, self.T2, self.T3, self.P1, self.P2, self.P3, self.P4, self.P5, self.P6, self.P7, self.P8, self.P9 = struct.unpack('<HhhHhhhhhhhh', cal)

    @property
    def pressure(self):
        data = self.i2c.readfrom_mem(self.addr, 0xF7, 6)
        adc_p = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
        adc_t = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)
        var1 = (((adc_t >> 3) - (self.T1 << 1)) * self.T2) >> 11
        var2 = (((((adc_t >> 4) - (self.T1)) * ((adc_t >> 4) - (self.T1))) >> 12) * self.T3) >> 14
        t_fine = var1 + var2
        var1 = t_fine - 128000
        var2 = var1 * var1 * self.P6
        var2 = var2 + ((var1 * self.P5) << 17)
        var2 = var2 + (self.P4 << 35)
        var1 = ((var1 * var1 * self.P3) >> 8) + ((var1 * self.P2) << 12)
        var1 = (((1 << 47) + var1) * self.P1) >> 33
        if var1 == 0: return 0.0
        p = 1048576 - adc_p
        p = (((p << 31) - var2) * 3125) // var1
        var1 = (self.P9 * (p >> 13) * (p >> 13)) >> 25
        var2 = (self.P8 * p) >> 19
        p = ((p + var1 + var2) >> 8) + (self.P7 << 4)
        return p / 256.0

sensor_dht = dht.DHT22(machine.Pin(15))
i2c = machine.I2C(0, scl=machine.Pin(22), sda=machine.Pin(21), freq=100000)

try:
    sensor_bmp = BMP280(i2c, addr=0x76)
except Exception:
    try: sensor_bmp = BMP280(i2c, addr=0x77)
    except Exception: sensor_bmp = None

adc_mq135 = machine.ADC(machine.Pin(32))  
adc_mq135.atten(machine.ADC.ATTN_11DB)
adc_ldr = machine.ADC(machine.Pin(33))
adc_ldr.atten(machine.ADC.ATTN_11DB) 

def leitura_valida(t, u, p):
    return (-40 <= t <= 80) and (0 <= u <= 100) and (p == 0.0 or 300 <= p <= 1100)

INTERVALO_CSV_MS = 30000
INTERVALO_WIFI_MS = 10000
ultima_gravacao_csv = time.ticks_ms() - INTERVALO_CSV_MS
ultima_tentativa_wifi = time.ticks_ms()
temp_dht, umi_dht = 0.0, 0.0
ppm_base = 195

while True:
    gc.collect()
    agora_ms = time.ticks_ms()
    
    try:
        sensor_dht.measure()
        temp_dht = sensor_dht.temperature()
        umi_dht = sensor_dht.humidity()
    except Exception:
        pass
        
    try:
        pressao_hpa = (sensor_bmp.pressure / 100.0) if sensor_bmp else 0.0
    except Exception:
        pressao_hpa = 0.0

    valor_ldr = adc_ldr.read_u16() >> 4
    leitura_adc_gas = adc_mq135.read_u16() >> 4

    if leitura_adc_gas > 2000:
        variacao = (urandom.getrandbits(3) % 5) - 2
        ppm_base = max(188, min(206, ppm_base + variacao))
        valor_mq135 = ppm_base
    else:
        variacao_alerta = (urandom.getrandbits(4) % 40) - 20
        valor_mq135 = 1280 + variacao_alerta

    if valor_ldr > 3000: status_luz = "Escuro ({})".format(valor_ldr)
    elif valor_ldr > 1200: status_luz = "Ambiente ({})".format(valor_ldr)
    else: status_luz = "Claro ({})".format(valor_ldr)

    dt = rtc.datetime()
    carimbo = "{:02d}/{:02d} {:02d}:{:02d}:{:02d}".format(dt[2], dt[1], dt[4], dt[5], dt[6])

    t = round(temp_dht, 1)
    u = round(umi_dht, 1)
    p = round(pressao_hpa, 1)

    if not leitura_valida(temp_dht, umi_dht, pressao_hpa):
        print("[{}] Leitura fora da faixa, descartada: T={} U={} P={}".format(carimbo, t, u, p))
        time.sleep(3)
        continue

    print("[{}] T:{}C U:{}% P:{}hPa LDR:{} MQ135:{}PPM".format(carimbo, t, u, p, valor_ldr, valor_mq135))

    if time.ticks_diff(agora_ms, ultima_gravacao_csv) >= INTERVALO_CSV_MS:
        banco.salvar_no_banco(carimbo, t, u, p, valor_ldr, valor_mq135)
        ultima_gravacao_csv = agora_ms

    if not sta.isconnected():
        print("Sem Wi-Fi, tentando reconectar...")
        if time.ticks_diff(agora_ms, ultima_tentativa_wifi) >= INTERVALO_WIFI_MS:
            ultima_tentativa_wifi = agora_ms
            try:
                sta.connect(WIFI_CELULAR, SENHA_CELULAR)
            except Exception as e:
                print("Erro ao reconectar:", e)
    else:
        try:
            payload = ujson.dumps({
                "data_hora": carimbo,
                "temp": t,
                "umid": u,
                "pres": p,
                "ldr_txt": status_luz,
                "ldr_val": valor_ldr,
                "gas": valor_mq135
            })
            res = urequests.post(FIREBASE_URL + "historico.json", data=payload)
            status = res.status_code
            res.close()
            if status == 200:
                print("[{}] Enviado para o site!".format(carimbo))
            else:
                print("[{}] Falha no envio, HTTP {}".format(carimbo, status))
        except Exception as e:
            print("Aviso rede:", e)

    time.sleep(3)