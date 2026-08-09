import os

from ledger_lite import create_app

app = create_app()

if __name__ == "__main__":
    # Port 5050, not 5000: on macOS 5000 is often taken by AirPlay Receiver.
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=int(os.environ.get("PORT", 5050)))
