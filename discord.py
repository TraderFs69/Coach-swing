import requests

def send_discord(webhook, message):
    payload = {"content": message}
    requests.post(webhook, json=payload)
