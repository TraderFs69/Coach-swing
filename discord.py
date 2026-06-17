import requests

def send_discord(webhook, message):
    requests.post(
        webhook,
        json={"content": message},
        timeout=30
    )
