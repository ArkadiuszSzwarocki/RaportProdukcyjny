import paho.mqtt.client as mqtt
import json
import time

data = []
def on_message(client, userdata, msg):
    try:
        data.append((msg.topic, json.loads(msg.payload.decode().strip('\x00'))))
    except:
        pass

client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
client.username_pw_set('Lstech', 'Lstech123')
client.tls_set()
client.on_message = on_message

client.connect('4a85c6c2e2d343e8b6798f1124ffe230.s1.eu.hivemq.cloud', 8883, 60)
client.subscribe('iot-2/type/cMT2108X2/id/agroPaletyzator')
client.loop_start()
time.sleep(3)
client.loop_stop()
print(data)
