import re

def clean_message_body(body):
    """Removes Chatwork-specific tags from the message body."""
    body = re.sub(r'\[rp aid=\d+ to=\d+-\d+\]|\[piconname:\d+\].*?さん|\[To:\d+\]', '', body)
    return body.strip()
