from gtts import gTTS
import os
text = 'Laboratorium zwolniło mieszalnik do wysypu na linii AGRO'
out = os.path.join(os.path.dirname(__file__), '..', 'static', 'sounds', 'zwolnienie_agro.mp3')
out = os.path.abspath(out)
try:
    os.makedirs(os.path.dirname(out), exist_ok=True)
    print('starting gTTS')
    tts = gTTS(text=text, lang='pl')
    print('gTTS created, saving...')
    tts.save(out)
    print('saved', out)
except Exception as e:
    import traceback; traceback.print_exc()
    print('error:', str(e))
