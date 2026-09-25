"""WSGI entrypoint for RaportProdukcyjny production deployment."""
from app.core.factory import create_app

app = create_app()
application = app

if __name__ == '__main__':
    app.run()
