from flask import Flask
from threading import Thread

app = Flask("")


@app.route("/")
def home():
    return "RUNNING..."