"""Durable, idempotent office PDF jobs with a real Windows spool identifier."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from uuid import UUID, uuid4
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

try:
    from printer_server.office_config import office_printers
    from printer_server.office_ipp import device_job_status
except ModuleNotFoundError:
    from office_config import office_printers
    from office_ipp import device_job_status

EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix='tracked-office')
INSTANCE = str(uuid4())
TERMINAL = {'DEVICE_COMPLETED','DEVICE_WARNING','FAILED','CANCELLED'}


def windows_status(info):
    status = int(info.get('Status') or 0)
    if status & (0x100 | 0x4):
        return 'UNKNOWN', 'Windows zgłosił usunięcie zadania; nie wiadomo, czy wcześniej je wydrukowano.'
    if status & (0x2 | 0x20 | 0x40 | 0x200 | 0x400):
        return 'ATTENTION', 'Kolejka zgłasza błąd, brak papieru, offline lub potrzebę interwencji.'
    if status & (0x80 | 0x1000):
        return 'SENT_TO_PRINTER', 'Windows zakończył obsługę zadania; fizyczny wydruk niepotwierdzony.'
    if status & 0x10:
        return 'PRINTING', 'Windows zgłasza drukowanie.'
    return 'QUEUED', 'Zadanie jest w kolejce Windows.'


def render_windows_pdf(path, printer, document_name, started):
    """Rasterize via the installed Windows driver; StartDoc returns the exact job ID."""
    import ctypes
    import struct
    import pymupdf
    import win32ui
    pdf = pymupdf.open(path)
    dc = None
    job_started = False
    try:
        if pdf.needs_pass or not 1 <= len(pdf) <= 100:
            raise ValueError('PDF musi mieć od 1 do 100 stron i nie może być zaszyfrowany.')
        dc = win32ui.CreateDC()
        dc.CreatePrinterDC(printer)
        job_id = dc.StartDoc(document_name)
        if job_id <= 0:
            raise RuntimeError('Windows nie zwrócił numeru zadania druku.')
        job_started = True
        started(job_id)
        stretch = ctypes.windll.gdi32.StretchDIBits
        stretch.argtypes = [ctypes.c_void_p] + [ctypes.c_int]*8 + [ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint,ctypes.c_ulong]
        stretch.restype = ctypes.c_int
        for page in pdf:
            pix = page.get_pixmap(dpi=200, colorspace=pymupdf.csRGB, alpha=False)
            rgb = bytearray(pix.samples)
            rgb[0::3], rgb[2::3] = rgb[2::3], rgb[0::3]
            stride = (pix.width*3+3)//4*4
            pixels = bytearray(stride*pix.height)
            for y in range(pix.height):
                pixels[y*stride:y*stride+pix.width*3] = rgb[y*pix.width*3:(y+1)*pix.width*3]
            info = struct.pack('<IiiHHIIiiII',40,pix.width,-pix.height,1,24,0,len(pixels),0,0,0,0)
            width, height = dc.GetDeviceCaps(8), dc.GetDeviceCaps(10)
            factor = min(width/pix.width, height/pix.height)
            dw, dh = int(pix.width*factor), int(pix.height*factor)
            dc.StartPage()
            bits, bitmap = ctypes.create_string_buffer(bytes(pixels)), ctypes.create_string_buffer(info)
            drawn = stretch(dc.GetHandleOutput(),(width-dw)//2,(height-dh)//2,dw,dh,0,0,pix.width,pix.height,bits,bitmap,0,0x00CC0020)
            if drawn in (0,-1):
                raise RuntimeError('Sterownik nie przyjął obrazu strony PDF.')
            dc.EndPage()
        dc.EndDoc()
        job_started = False
    finally:
        if dc:
            if job_started:
                dc.AbortDoc()
            dc.DeleteDC()
        pdf.close()


class OfficeJobs:
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get('OFFICE_PRINT_JOB_DB') or Path(__file__).parent/'runtime'/'office_jobs.sqlite3')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS office_jobs (
                request_id TEXT PRIMARY KEY, printer_key TEXT NOT NULL, printer_json TEXT NOT NULL,
                digest TEXT NOT NULL, status TEXT NOT NULL, note TEXT NOT NULL, spool_id INTEGER,
                created_at REAL NOT NULL, updated_at REAL NOT NULL, instance TEXT NOT NULL)""")

    @contextmanager
    def connect(self):
        c = sqlite3.connect(str(self.path), timeout=10)
        c.row_factory = sqlite3.Row
        try:
            with c:
                yield c
        finally:
            c.close()

    def get(self, request_id):
        with self.connect() as c:
            row = c.execute('SELECT * FROM office_jobs WHERE request_id=?',(request_id,)).fetchone()
            return dict(row) if row else None

    def update(self, request_id, status, note, spool_id=None):
        with self.connect() as c:
            c.execute("UPDATE office_jobs SET status=?,note=?,updated_at=?,spool_id=COALESCE(?,spool_id) WHERE request_id=? AND status NOT IN ('DEVICE_COMPLETED','DEVICE_WARNING','FAILED','CANCELLED')",
                      (status,str(note)[:500],time.time(),spool_id,request_id))

    def submit(self, request_id, printer_key, data):
        request_id = str(UUID(request_id))
        printers = office_printers()
        if printer_key not in printers:
            raise ValueError('Drukarka A4 nie jest skonfigurowana lub włączona.')
        if not data.startswith(b'%PDF-') or len(data) > 20*1024*1024:
            raise ValueError('Wymagany jest PDF do 20 MB.')
        digest = hashlib.sha256(data).hexdigest()
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            old = c.execute('SELECT * FROM office_jobs WHERE request_id=?',(request_id,)).fetchone()
            if old:
                if old['digest'] != digest or old['printer_key'] != printer_key:
                    raise ValueError('Ten identyfikator należy do innego wydruku.')
                return dict(old)
            if c.execute("SELECT COUNT(*) FROM office_jobs WHERE status IN ('BRIDGE_QUEUED','SUBMITTING') AND instance=?",(INSTANCE,)).fetchone()[0] >= 20:
                raise ValueError('Kolejka A4 pełna. Poczekaj na zakończenie zadań.')
            now = time.time()
            c.execute('INSERT INTO office_jobs VALUES (?,?,?,?,?,?,NULL,?,?,?)',
                      (request_id,printer_key,json.dumps(printers[printer_key]),digest,'BRIDGE_QUEUED','Przyjęto przez mostek; oczekiwanie na kolejkę Windows.',now,now,INSTANCE))
        pdf_path = self.path.parent/(request_id+'.pdf')
        try:
            pdf_path.write_bytes(data)
            EXECUTOR.submit(self._print, request_id, pdf_path)
        except Exception:
            self.update(request_id,'FAILED','Nie przygotowano zadania w mostku.')
            pdf_path.unlink(missing_ok=True)
            raise
        return self.get(request_id)

    def _print(self, request_id, path):
        try:
            job = self.get(request_id)
            config = json.loads(job['printer_json'])
            self.update(request_id,'SUBMITTING','Przygotowanie stron dla sterownika Windows.')
            render_windows_pdf(path,config['windows_name'],'RP-'+request_id,
                               lambda spool_id:self.update(request_id,'QUEUED','Przyjęto do kolejki Windows.',spool_id))
        except Exception as error:
            job = self.get(request_id)
            self.update(request_id,'UNKNOWN' if job and job['spool_id'] else 'FAILED',
                        'Niepewny wynik; nie ponawiaj bez sprawdzenia kolejki. '+str(error))
        finally:
            path.unlink(missing_ok=True)

    def refresh(self, request_id):
        job = self.get(str(UUID(request_id)))
        if not job or job['status'] in TERMINAL:
            return job
        if job['status'] in ('BRIDGE_QUEUED','SUBMITTING') and job['instance'] != INSTANCE:
            self.update(request_id,'UNKNOWN','Mostek został uruchomiony ponownie. Sprawdź kolejkę; brak automatycznego ponowienia.')
            return self.get(request_id)
        if not job['spool_id']:
            return job
        config = json.loads(job['printer_json'])
        state, note = 'UNKNOWN','Brak zadania w kolejce nie potwierdza wydrukowania. Sprawdź urządzenie.'
        try:
            import win32print
            handle = win32print.OpenPrinter(config['windows_name'])
            try:
                info = win32print.GetJob(handle, job['spool_id'], 2)
                if info.get('pDocument') == 'RP-'+request_id:
                    state, note = windows_status(info)
            finally:
                win32print.ClosePrinter(handle)
        except Exception:
            pass
        if config.get('ipp_uri'):
            try:
                device = device_job_status(config['ipp_uri'],'RP-'+request_id)
                if device:
                    state, note = device
            except Exception:
                note += ' Brak odczytu IPP z urządzenia.'
        self.update(request_id,state,note)
        return self.get(request_id)


def public_job(job):
    if not job:
        return None
    return {key:job[key] for key in ('request_id','printer_key','status','note','spool_id','updated_at')}
