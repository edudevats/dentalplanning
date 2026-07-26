import os
import time

# Forzar zona horaria de México en todo el proceso.
# Servidores en la nube corren en UTC; sin esto, cualquier librería
# (satcfdi, etc.) que llame datetime.now() obtendría hora UTC.
os.environ['TZ'] = 'America/Mexico_City'
try:
    time.tzset()
except AttributeError:
    pass  # time.tzset() solo disponible en Unix

from dotenv import load_dotenv
load_dotenv()

from app import create_app


app = create_app()

if __name__ == "__main__":
    debug = os.getenv("FLASK_ENV", "development") != "production"
    app.run(debug=debug, port=5000)
