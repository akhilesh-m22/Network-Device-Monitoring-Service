"""Entry point: run the web app with `python run.py`."""

from app import create_app

app = create_app()

if __name__ == "__main__":
    # use_reloader=False so the background monitor thread is not started
    # twice (once per reloader process).
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)
