from flask import Flask, jsonify
import subprocess
import threading
import os

app = Flask(__name__)

def executar_bot():
    script_path = os.path.join(os.getcwd(), "acessar_pagina.py")
    subprocess.run(["python", script_path])

@app.route("/webhook", methods=["POST", "GET"])
def webhook():
    thread = threading.Thread(target=executar_bot)
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "status": "success",
        "message": "Bot iniciado com sucesso",
        "pid": os.getpid()
    }), 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "service": "aracruz-bot"
    }), 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
