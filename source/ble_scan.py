# https://github.com/hilch/micropython-switchbot-thermometer-hygrometer

import bluetooth
from micropython import const, schedule
import math

_IRQ_SCAN_RESULT = const(5)
_IRQ_SCAN_DONE = const(6)

_ADV_IND = const(0x00)
_ADV_DIRECT_IND = const(0x01)
_ADV_SCAN_IND = const(0x02)
_ADV_NONCONN_IND = const(0x03)
_SCAN_RSP = const(0x4)


# the scan will output the MAC of unknown devices. Enter them here afterwards.

devices = {
    const('F3:50:26:00:00:00') : const('Office'),
    const('FF:A4:02:00:00:00') : const('Hobby'),
    const('E5:12:17:00:00:00') : const('Bath'),
    const('D5:75:04:00:00:00') : const('Dining room'),
    const('F9:4D:09:00:00:00') : const('Outdoor'),
    const('D2:68:6B:00:00:00') : const('Living room')
}

def celsius2fahrenheit(celsius):
    return  celsius * 1.8 + 32.0


def switchBotMeter( data : bytes ):
    temperature = 0.0
    humidity = 0
    batteryLevel = 0
    dewPoint = 0.0
    unit = ''          
    #rssi = int(adv_data.rssi) 
           
    # Absolute value of temp
    temperature = (data[4] & 0b01111111) + ((data[3] & 0b00001111) / 10 )  
    if not (data[4] & 0b10000000):  # Is temp negative?
            temperature = -temperature
    # unit set by user
    unit = 'F' if data[5] & 0b10000000 else 'C'               
    # relative humidity in %
    humidity = data[5] & 0b01111111
    # battery health in %
    battery = bool(data[2] & 0b01111111)  
    # Fahrenheit ?
    if unit == 'F':
        temperature = celsius2fahrenheit(temperature)
    # dew point in degree
    # https://en.wikipedia.org/wiki/Dew_point
    a = 6.1121 # millibars
    b = 17.368 if temperature >= 0.0 else 17.966
    c = 238.88 if temperature >= 0.0 else 247.15 # °C;
    ps = a * math.exp(b * temperature/(c + temperature)) # saturated water vapor pressure [millibars]
    pa = humidity/100.0 * ps # actual vapor pressure [millibars]
    dp = c * math.log(pa/a) / ( b - math.log(pa/a) )
    if unit == 'C':
        dewPoint = round( dp, 1)
    else:
        dewPoint =  round( self.celsius2fahrenheit(dp), 1)  # Convert to F
    return {
            "temperature" : temperature,
            "humidity" : humidity,
            "dew" : dewPoint,
            "unit" : unit,
            "battery" : battery,
        }


def macAddress( b : bytes ):
    return ':'.join(["%02x" % int(x) for x in b]).upper()


def bt_irq(event, data):

    if event == _IRQ_SCAN_RESULT:
        # A single scan result.
        addr_type, addr, adv_type, rssi, adv_data = data
        mac = macAddress(bytes(addr))  
        _adv_data = bytes(adv_data)
        if adv_type == _SCAN_RSP and len(_adv_data) >= 5:
            if _adv_data[4] == 0x54 and mac not in devices:
                devices.update({ mac : 'unnamed_'+mac })       
        if mac in devices:
            location = devices[mac]
            if adv_type == _ADV_IND and _adv_data[:7] == b'\x02\x01\x06\x0e\xffi\t':
                result = switchBotMeter( _adv_data[-6:])
                result.update({ "rssi" : rssi })
                print( location, result )
            
    elif event == _IRQ_SCAN_DONE:
        # Scan duration finished or manually stopped.
        print('scan done')


if( __name__ == '__main__'):
    ble = bluetooth.BLE()
    ble.irq(bt_irq)
    ble.active(True)
    ble.gap_scan( 0, 60000, 30000, True)
    while(True):pass


