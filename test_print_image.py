import win32print
import win32ui
from PIL import Image, ImageWin
import time

def print_image(file_name, printer_name):
    print(f"Printing {file_name} to {printer_name}...")
    hDC = win32ui.CreateDC()
    hDC.CreatePrinterDC(printer_name)
    
    printable_area = hDC.GetDeviceCaps(8), hDC.GetDeviceCaps(10)
    printer_size = hDC.GetDeviceCaps(110), hDC.GetDeviceCaps(111)
    printer_margins = hDC.GetDeviceCaps(112), hDC.GetDeviceCaps(113)
    
    bmp = Image.open(file_name)
    if bmp.size[0] > bmp.size[1]:
        bmp = bmp.rotate(90, expand=True)
        
    ratios = [1.0 * printable_area[0] / bmp.size[0], 1.0 * printable_area[1] / bmp.size[1]]
    scale = min(ratios)
    
    hDC.StartDoc(file_name)
    hDC.StartPage()
    
    dib = ImageWin.Dib(bmp)
    scaled_width, scaled_height = [int(scale * i) for i in bmp.size]
    x1 = int((printable_area[0] - scaled_width) / 2)
    y1 = int((printable_area[1] - scaled_height) / 2)
    x2 = x1 + scaled_width
    y2 = y1 + scaled_height
    dib.draw(hDC.GetHandleOutput(), (x1, y1, x2, y2))
    
    hDC.EndPage()
    hDC.EndDoc()
    hDC.DeleteDC()
    print("Done")

if __name__ == '__main__':
    img = Image.new('RGB', (1000, 1000), color = 'red')
    img.save('test.png')
    print_image('test.png', win32print.GetDefaultPrinter())
