from flask import Flask
app = Flask(__name__)

@app.route('/')
def hello_world():
    return '⚡Your App is Running⚡'


if __name__ == "__main__":
    app.run()
