import urllib.request
url = 'https://agronetzwerk.de/wp-content/uploads/2021/04/Agronetzwerk-Logo.png'
out = 'static/logo.png'
print('Downloading', url)
urllib.request.urlretrieve(url, out)
print('Saved to', out)
