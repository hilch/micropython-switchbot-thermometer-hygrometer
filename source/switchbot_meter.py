# https://github.com/hilch/micropython-switchbot-thermometer-hygrometer
# tested with Raspberry Pico W and ESP32-WROOM and Micropython V 1.25.0

import time
import bluetooth
from micropython import const
import math


_IRQ_SCAN_RESULT = const(5)
_ADV_IND = const(0x00)
_SCAN_RSP = const(0x4)

MAX_DEVICES = const(20)

def macAddress( b : bytes ):
    return ':'.join(["%02x" % int(x) for x in b]).upper()

def toHex( b : bytes ):
    return ' '.join(["%02x" % int(x) for x in b]).lower()

def celsius2fahrenheit(celsius):
    return  celsius * 1.8 + 32.0


class SwitchbotMeter():
    def __init__(self):
        self._temperature = -273.15
        self._humidity = 0
        self._batteryLevel = -1
        self._dewPoint = -273.15
        self._unit = 'C'
        self._battery = 0
        self._rssi = 0
        self._MAC = bytes(6)
        self._scan_rsp = bytes(5)
        self._adv_ind = bytes(5)
    
    
    def store_scan_rsp( self, mac, rssi, data ):
        self._MAC = mac
        self._rssi = rssi
        self._scan_rsp = bytes(data)
    
    
    def store_adv_ind( self, rssi, data ):
        self._rssi = rssi
        self._adv_ind = bytes(data)
       
       
    def _process_scan_results(self):
        if self._adv_ind != bytes(5) and self._scan_rsp != bytes(5):
            if self._scan_rsp[4] == 0x54: # WoSensorTH
                self._process_scan_rsp_th()
                self._process_adv_ind_th()
            elif self._scan_rsp[4] == 0x77: # WoSensorTHO
                self._process_scan_rsp_tho()
                self._process_adv_ind_tho()
    
    # SBM classic
    def _process_adv_ind_th(self):
        frame = self._adv_ind
        pass
    
    # SBM classic
    def _process_scan_rsp_th(self):
        frame = self._scan_rsp
        # Absolute value of temp
        self._temperature = (frame[8] & 0x7f) + ((frame[7] & 0x7f) / 10 )  
        if not (frame[8] & 0x80):  # Is temp negative?
                self._temperature = -self._temperature

        # unit set by user
        self._unit = 'F' if frame[9] & 0x80 else 'C'
        # relative humidity in %
        self._humidity = frame[9] & 0x7f
        # battery health in %
        self._battery = frame[6] & 0x7f
        # Fahrenheit ?
        if self._unit == 'F':
            self._temperature = celsius2fahrenheit(self._temperature)
        self._calc_dewpoint()
    
    # SBM outdoor
    def _process_adv_ind_tho(self):
        frame = self._adv_ind
        # Absolute value of temp
        self._temperature = (frame[16] & 0x7f) + ((frame[15] & 0x7f) / 10 )  
        if not (frame[16] & 0x80):  # Is temp negative?
            self._temperature = -self._temperature              
        # relative humidity in %
        self._humidity = frame[17] & 0x7f
        self._calc_dewpoint()
    
    # SBM outdoor
    def _process_scan_rsp_tho(self):
        frame = self._scan_rsp
        self._battery = frame[6] & 0x7f

    def _calc_dewpoint(self):
        # dew point in degree
        # https://en.wikipedia.org/wiki/Dew_point
        a = const(6.1121) # millibars
        b = 17.368 if self._temperature >= 0.0 else 17.966
        c = 238.88 if self._temperature >= 0.0 else 247.15 # °C;
        ps = a * math.exp(b * self._temperature/(c + self._temperature)) # saturated water vapor pressure [millibars]
        pa = self._humidity/100.0 * ps # actual vapor pressure [millibars]
        dp = c * math.log(pa/a) / ( b - math.log(pa/a) )
        if self._unit == 'C':
            self._dewPoint = round( dp, 1)
        else:
            self._dewPoint =  round( celsius2fahrenheit(dp), 1)  # Convert to F     
    
    @property
    def data(self):
        self._process_scan_results()
        return {
                "temperature" : self._temperature,
                "humidity" : self._humidity,
                "dew" : self._dewPoint,
                "unit" : self._unit,
                "battery" : self._battery,
                "rssi" : self._rssi,
                "MAC" : str(macAddress(self._MAC)),
                "device_type" : self.device_type
        } if (self.device_type
                and self._temperature > -270
                and self._battery > 0) else None
    
    @property
    def MAC(self):
        return self._MAC
       
    @property
    def device_type(self):
        if self._scan_rsp[4] == 0x54:
            return 'WoSensorTH'
        elif self._scan_rsp[4] == 0x77:
            return 'WoSensorTHO'
        else:
            return None


    def __repr__(self):
        self._process_scan_results()
        temperature = self._temperature if self._temperature > -270 else '-'
        return( (f'SwitchbotMeter {self.device_type} {macAddress(self.MAC)}'
                 f' {temperature} {self._unit}') )
    
    @classmethod
    def get_device_list(cls):
        return [d for d in _devices if d.data]
    
   
    @classmethod
    def bt_irq( cls, event, data):  # A single scan result.
        if event == _IRQ_SCAN_RESULT:
            _, addr, adv_type, rssi, adv_data = data
            if adv_type == _SCAN_RSP and len(adv_data)>=5:
                mac = bytes(addr)
                if adv_data[4] == 0x54 or adv_data[4] == 0x77:
                    for d in _devices:
                        if d.MAC == mac:
                            d.store_scan_rsp(mac, rssi, adv_data)
                            return
                    for d in _devices:
                        if d.MAC == b'\x00\x00\x00\x00\x00\x00':
                            d.store_scan_rsp(mac, rssi, adv_data)
                            return
            elif adv_type == _ADV_IND:
                mac = bytes(addr)
                for d in _devices:
                    if d.MAC == mac:
                        d.store_adv_ind(rssi, adv_data)


_devices = [SwitchbotMeter() for _ in range(MAX_DEVICES)]


# example call

if( __name__ == '__main__'):
    from micropython import alloc_emergency_exception_buf
    import gc
    alloc_emergency_exception_buf(100)
    print("start")
    # Bluetooth
    ble = bluetooth.BLE()
    ble.irq(SwitchbotMeter.bt_irq)
    ble.active(True)
    ble.gap_scan( 0, 31000, 30000, True)
    while True:
        for d in SwitchbotMeter.get_device_list():
            print( d.data )
        gc.collect()
        time.sleep(5)
    
