import os
import logging
from flask import Flask, request
from handlers import handle_webhook_event
from services import get_supabase_client

app = Flask(__name__)
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

@app.route("/", methods=["POST"])
def webhook():
    """Handles incoming Chatwork webhook events."""
    try:
        data = request.json
        if not data:
            return "OK", 200

        webhook_event = data.get("webhook_event")
        if webhook_event:
            logging.info(f"Received webhook event: {webhook_event}")
            handle_webhook_event(webhook_event)
        
        return "OK", 200
    except Exception as e:
        logging.error(f"Error handling webhook event: {e}")
        return "Internal Server Error", 500

if __name__ == "__main__":
    # Check if required environment variables are set.
    required_vars = ["CHATWORK_API_TOKEN", "MY_ACCOUNT_ID", "SUPABASE_URL", "SUPABASE_KEY", "OPENWEATHER_API_KEY"]
    for var in required_vars:
        if not os.environ.get(var):
            logging.error(f"Environment variable '{var}' is not set.")
            # In a real-world scenario, you might want to exit or raise an exception.
    
    # Check database connection.
    supabase_client = get_supabase_client()
    if supabase_client:
        logging.info("Successfully connected to Supabase.")
    else:
        logging.warning("Could not connect to Supabase. Database-dependent features will not work.")

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
