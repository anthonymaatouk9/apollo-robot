import logging
logging.basicConfig(level=logging.INFO)

from app import create_app

app = create_app()

if __name__ == "__main__":
    from waitress import serve
    print("Apollo server starting...")
    print("Dashboard: http://127.0.0.1:5000")
    print("Network:   http://0.0.0.0:5000")
    serve(app, host="0.0.0.0", port=5000, threads=16)
