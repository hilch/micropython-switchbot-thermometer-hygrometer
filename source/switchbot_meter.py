# https://github.com/hilch/micropython-switchbot-thermometer-hygrometer
# tested with Raspberry Pico W and ESP32-WROOM and Micropython V 1.25.0

import time
import bluetooth
from micropython import const
import math


_IRQ_SCAN_RESULT = const(5)
_IRQ_SCAN_DONE = const(6)

_ADV_IND = const(0x00)
_ADV_DIRECT_IND = const(0x01)
_ADV_SCAN_IND = const(0x02)
_ADV_NONCONN_IND = const(0x03)
_SCAN_RSP = const(0x4)


def macAddress( b : bytes ):
    return ':'.join(["%02x" % int(x) for x in b]).upper()

def toHex( b : bytes ):
    return ' '.join(["%02x" % int(x) for x in b]).lower()

def celsius2fahrenheit(celsius):
    return  celsius * 1.8 + 32.0


class SwitchbotMeter():
    def __init__(self):
        self._temperature = 0.0
        self._humidity = 0
        self._batteryLevel = 0
        self._dewPoint = 0.0
        self._unit = 'C'
        self._battery = 0
        self._rssi = 0
        self._MAC = ''
        self._device_type = None
        
    def process_scan_result(self, data ):
        addr_type, addr, adv_type, rssi, adv_data = data
        self._MAC = macAddress(bytes(addr))
        self._rssi = rssi
        if adv_type == _SCAN_RSP and len(adv_data) >= 4:
            if adv_data[4] == 0x54:
                self._device_type = 'WoSensorTH'
                self._scan_rsp_th(adv_data)
            elif adv_data[4] == 0x77:
                self._device_type = 'WoSensorTHO'
                self._scan_rsp_tho(adv_data)
            else:
                return
        elif adv_type == _ADV_IND:
            if self._device_type == 'WoSensorTH':
                self._adv_ind_th(adv_data)
            elif self._device_type == 'WoSensorTHO':
                self._adv_ind_tho(adv_data)
    
    # SBM classic
    def _adv_ind_th(self, frame ):     
        pass
    
    # SBM classic
    def _scan_rsp_th(self, frame ):
        # Absolute value of temp
        self._temperature = (frame[8] & 0x7f) + ((frame[7] & 0x7f) / 10 )  
        if not (frame[8] & 0x7f):  # Is temp negative?
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
        self.calc_dewpoint()    
    
    # SBM outdoor
    def _adv_ind_tho(self, frame ):     
        # Absolute value of temp
        self._temperature = (frame[16] & 0x7e) + ((frame[15] & 0x7e) / 10 )  
        if not (frame[16] & 0x7e):  # Is temp negative?
            self._temperature = -self._temperature              
        # relative humidity in %
        self._humidity = frame[17] & 0x7e
        self.calc_dewpoint()
    
    # SBM outdoor
    def _scan_rsp_tho(self, frame ):
        self._battery = frame[6] & 0x7f 

    def calc_dewpoint(self):
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
        return {
                "temperature" : self._temperature,
                "humidity" : self._humidity,
                "dew" : self._dewPoint,
                "unit" : self._unit,
                "battery" : self._battery,
                "rssi" : self._rssi,
                "MAC" : str(self._MAC),
                "device_type" : str(self._device_type)
        } if self._device_type else None
    
    @property
    def device_type(self):
        return self._device_type     

    __devices = {}

    @classmethod
    def get_devices( cls ):
        return( d.data for m, d in cls.__devices.items() )

    @classmethod  
    def bt_irq( cls, event, data):
        global device
        
        if event == _IRQ_SCAN_RESULT:
            # A single scan result.
            _, addr, _, _, _ = data
            mac = macAddress(bytes(addr))

            if mac not in cls.__devices:
                sbm = SwitchbotMeter()
                sbm.process_scan_result( data )
                if sbm.device_type:
                    cls.__devices.update( { mac : sbm })
                    cls.__devices[mac].process_scan_result( data )                  
            else:
                cls.__devices[mac].process_scan_result( data )


def bt_irq(event, data):
    SwitchbotMeter.bt_irq(event, data)


# example call

if( __name__ == '__main__'):    
    # Bluetooth
    ble = bluetooth.BLE()
    ble.irq(bt_irq)
    ble.active(True)
    ble.gap_scan( 0, 60000, 30000, True)
    while True:
        print( list(SwitchbotMeter.get_devices()) )
        time.sleep(5)
    
