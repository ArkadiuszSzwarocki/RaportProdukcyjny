"""Offline image checks: native libraries, reports, TLS trust and encryption."""
from io import BytesIO
import json
import ssl
from zoneinfo import ZoneInfo
from cryptography.fernet import Fernet
from flask import Flask, jsonify
from fpdf import FPDF
import mysql.connector
import OpenSSL
import pandas as pd
import psutil


def main():
    frame = pd.DataFrame({"weight": [1000, 45], "pallet": [1, 1]})
    assert frame.groupby("pallet")["weight"].sum().iloc[0] == 1045
    excel = BytesIO()
    frame.to_excel(excel, index=False, engine="openpyxl")
    excel.seek(0)
    assert pd.read_excel(excel, engine="openpyxl").equals(frame)
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(40, 10, "Runtime report")
    assert pdf.output(dest="S").startswith("%PDF")
    cipher = Fernet(Fernet.generate_key())
    assert cipher.decrypt(cipher.encrypt(b"offline test")) == b"offline test"
    assert ssl.create_default_context().cert_store_stats()["x509_ca"] > 0
    assert ZoneInfo("Europe/Warsaw").key == "Europe/Warsaw"
    assert psutil.Process().pid > 0
    assert mysql.connector.connection.MySQLConnection().is_connected() is False
    assert OpenSSL.SSL.TLS_METHOD
    app = Flask(__name__)
    app.add_url_rule("/health", view_func=lambda: jsonify(success=True))
    assert app.test_client().get("/health").json == {"success": True}
    print(json.dumps({"offline_runtime_smoke_passed": True,
                      "checks": ["pandas", "excel", "pdf", "encryption",
                                 "tls_ca", "timezone", "process_metrics",
                                 "mysql_import", "openssl", "flask"],
                      "database_connections": 0, "labels_sent": 0}))


if __name__ == "__main__":
    main()
